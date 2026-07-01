import argparse
import boto3
import requests
import xml.etree.ElementTree as ET
import os
import sys
import time
import random

# Initialize Structured Logging with AWS Lambda Powertools or Fallback
try:
    from aws_lambda_powertools import Logger
    logger = Logger(service="bgg-game-scraper")
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    class FallbackLogger:
        def __init__(self):
            self.log = logging.getLogger("bgg-game-scraper")
        def info(self, msg, *args, **kwargs):
            extra = kwargs.get('extra')
            if extra:
                self.log.info(f"{msg} - Extra: {extra}")
            else:
                self.log.info(msg)
        def error(self, msg, *args, **kwargs):
            extra = kwargs.get('extra')
            if extra:
                self.log.error(f"{msg} - Extra: {extra}")
            else:
                self.log.error(msg)
        def warning(self, msg, *args, **kwargs):
            extra = kwargs.get('extra')
            if extra:
                self.log.warning(f"{msg} - Extra: {extra}")
            else:
                self.log.warning(msg)
        def inject_lambda_context(self, func):
            return func
    logger = FallbackLogger()

def get_existing_game_ids(s3, bucket_name):
    """
    Lists all existing game IDs already stored as parquets in S3.
    """
    logger.info(f"Listing existing game files from s3://{bucket_name}/data/boardgames/")
    game_ids = []
    try:
        paginator = s3.get_paginator('list_objects_v2')
        for page in paginator.paginate(Bucket=bucket_name, Prefix='data/boardgames/'):
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    if key.endswith('.parquet'):
                        filename = os.path.basename(key)
                        game_id_str = filename.replace('.parquet', '')
                        if game_id_str.isdigit():
                            game_ids.append(int(game_id_str))
        logger.info(f"Found {len(game_ids)} existing game files in S3.")
    except Exception as e:
        logger.error(f"Error listing S3 objects: {e}")
    return game_ids

def send_ids_to_sqs_batch(sqs, queue_url, game_ids, batch_size=10):
    """
    Sends a list of game IDs to SQS in batches of 10.
    """
    logger.info(f"Sending {len(game_ids)} game IDs to SQS queue...")
    for i in range(0, len(game_ids), batch_size):
        chunk = game_ids[i:i + batch_size]
        entries = []
        for idx, game_id in enumerate(chunk):
            entries.append({
                'Id': str(idx),
                'MessageBody': str(game_id)
            })
        try:
            sqs.send_message_batch(QueueUrl=queue_url, Entries=entries)
            logger.info(f"Sent batch of {len(chunk)} IDs (indices {i} to {i+len(chunk)-1})")
        except Exception as e:
            logger.error(f"Error sending SQS batch: {e}. Falling back to individual sends.")
            # Fallback to single messages if batch fails
            for game_id in chunk:
                try:
                    sqs.send_message(QueueUrl=queue_url, MessageBody=str(game_id))
                    logger.info(f"Successfully sent ID {game_id} individually.")
                except Exception as single_e:
                    logger.error(f"Failed sending ID {game_id} individually: {single_e}")
        time.sleep(0.1)

def main():
    """
    Main function to scrape BoardGameGeek API.
    Supports two modes:
    - 'new' (Default): Reads start ID from S3 and crawls sequentially.
    - 'reprocess': Re-queues all existing game IDs from S3.
    """
    parser = argparse.ArgumentParser(description="BGG Game ID Scraper/Queuer")
    parser.add_argument('--mode', choices=['new', 'reprocess'], default=os.environ.get('SCRAPE_MODE', 'new'),
                        help="Scraping mode: 'new' (scrape new IDs sequentially from checkpoint) or 'reprocess' (re-queue existing game IDs from S3)")
    args, unknown = parser.parse_known_args()
    mode = args.mode.lower()

    s3_bucket_name = os.environ.get('S3_BUCKET_NAME', 'boardgame-app')
    s3_key = os.environ.get('S3_KEY', 'bgg-scraper/bgg_start_id.txt')
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')
    bgg_api_base_url = "https://boardgamegeek.com/xmlapi2/thing"
    request_delay_seconds = 1 # Delay between requests to respect API limits
    batch_size = int(os.environ.get('BATCH_SIZE', '20')) # Number of IDs to query at a time in new mode
    s3_update_interval = int(os.environ.get('S3_UPDATE_INTERVAL', '20')) # Update S3 every 20 IDs
    retry_delay_seconds = 2 # Base delay before retrying a failed batch
    sqs_queue_name = os.environ.get('SQS_QUEUE_NAME', 'bgg_game_data_scraper_queue')

    s3 = boto3.client('s3', region_name=aws_region)
    sqs = boto3.client('sqs', region_name=aws_region)

    # Retrieve SQS Queue URL
    try:
        sqs_queue_url = sqs.get_queue_url(QueueName=sqs_queue_name)['QueueUrl']
        logger.info(f"Successfully retrieved SQS queue URL: {sqs_queue_url}")
    except Exception as e:
        logger.error(f"Error getting SQS queue URL for '{sqs_queue_name}': {e}. Exiting.")
        sys.exit(1)

    if mode == 'reprocess':
        logger.info("Starting in REPROCESS mode...")
        existing_ids = get_existing_game_ids(s3, s3_bucket_name)
        if existing_ids:
            send_ids_to_sqs_batch(sqs, sqs_queue_url, existing_ids)
            logger.info("Successfully completed reprocess queueing. Exiting.")
        else:
            logger.info("No existing game IDs found to reprocess.")
        return

    # Default 'new' mode
    logger.info("Starting in NEW mode (sequential crawler)...")
    start_id = None
    update_counter = 0

    try:
        # 1. Read starting ID from S3
        logger.info(f"Attempting to read ID from s3://{s3_bucket_name}/{s3_key}")
        response = s3.get_object(Bucket=s3_bucket_name, Key=s3_key)
        start_id_str = response['Body'].read().decode('utf-8').strip()
        start_id = int(start_id_str)
        logger.info(f"Successfully read starting ID: {start_id}")

    except s3.exceptions.NoSuchKey:
        logger.error(f"Error: S3 key '{s3_key}' not found in bucket '{s3_bucket_name}'. Exiting.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading from S3: {e}. Exiting.")
        sys.exit(1)

    if start_id is None:
        logger.error("Failed to retrieve a valid starting ID. Exiting.")
        sys.exit(1)

    # Start the continuous scraping loop
    while True:
        # Generate a batch of IDs
        current_ids_batch = list(range(start_id, start_id + batch_size))
        ids_param = ','.join(map(str, current_ids_batch))
        api_url = f"{bgg_api_base_url}?id={ids_param}"

        batch_succeeded = False
        retry_count = 0

        while not batch_succeeded:
            logger.info(f"Querying BGG API for IDs: {ids_param} (Attempt {retry_count + 1})")
            try:
                bgg_api_token = os.environ.get('BGG_API_TOKEN')
                headers = {}
                if bgg_api_token:
                    headers["Authorization"] = f"Bearer {bgg_api_token}"
                response = requests.get(api_url, headers=headers)
                response.raise_for_status()
                xml_data = response.content
                logger.info(f"Successfully received response for IDs {ids_param} from BGG API.")

                # Parse XML response
                root = ET.fromstring(xml_data)

                # Check if items exist and are of type 'boardgame'
                items_found = False
                for item in root.findall('item'):
                    items_found = True
                    item_id = item.get('id')
                    item_type = item.get('type')
                    item_name_element = item.find("./name[@type='primary']")
                    item_name = item_name_element.get('value') if item_name_element is not None else "N/A"

                    logger.info(f"Processing item ID: {item_id}, Type: {item_type}, Name: {item_name}")

                    if item_type == 'boardgame':
                        logger.info(f"ID {item_id} is a boardgame: {item_name}")
                        try:
                            sqs.send_message(
                                QueueUrl=sqs_queue_url,
                                MessageBody=str(item_id)
                            )
                            logger.info(f"Successfully sent ID {item_id} to SQS queue '{sqs_queue_name}'.")
                        except Exception as sqs_e:
                            logger.error(f"Error sending ID {item_id} to SQS: {sqs_e}")
                    else:
                        logger.info(f"ID {item_id} exists but is not a boardgame (Type: {item_type}). Name: {item_name}")
                
                if not items_found and current_ids_batch[0] > 452300:
                    logger.error(f"No items found in BGG API response for IDs: {ids_param}. Exiting.")
                    sys.exit(1)

                batch_succeeded = True

            except Exception as e:
                delay = min(60, retry_delay_seconds * (2 ** retry_count))
                jittered_delay = delay / 2.0 + random.uniform(0, delay / 2.0)
                logger.error(f"Error querying BGG API for IDs {ids_param}: {e}. Retrying in {jittered_delay:.2f} seconds.")
                retry_count += 1
                time.sleep(jittered_delay)

        # If batch succeeded, update state and prepare for next batch
        start_id += batch_size
        update_counter += batch_size

        # Update starting ID in S3 for persistence
        if update_counter >= s3_update_interval:
            logger.info(f"Update interval reached. Attempting to update S3 with ID: {start_id}.")
            try:
                s3.put_object(Bucket=s3_bucket_name, Key=s3_key, Body=str(start_id).encode('utf-8'))
                logger.info(f"Successfully updated S3 with new starting ID: {start_id}")
                update_counter = 0
            except Exception as e:
                logger.error(f"CRITICAL ERROR: Failed to update S3 with ID {start_id}: {e}. Exiting to prevent data loss.")
                sys.exit(1)
        else:
            logger.info(f"Incremented ID to {start_id}. S3 update skipped (next update in {s3_update_interval - update_counter} IDs).")

        time.sleep(request_delay_seconds)

if __name__ == '__main__':
    main()
