import boto3
import requests
import xml.etree.ElementTree as ET
import os
import sys
import time # New import

def main():
    """
    Main function to scrape BoardGameGeek API.
    Reads a starting ID from S3, queries BGG API, and checks if it's a boardgame.
    Loops, increments ID, and updates S3.
    """
    s3_bucket_name = os.environ.get('S3_BUCKET_NAME', 'boardgame-app')
    s3_key = os.environ.get('S3_KEY', 'bgg-scraper/bgg_start_id.txt')
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')
    bgg_api_base_url = "https://boardgamegeek.com/xmlapi2/thing"
    request_delay_seconds = 1 # Delay between requests to respect API limits (e.g., 1 second)
    s3_update_interval = 100 # Update S3 every 100 IDs
    batch_size = 20 # Number of IDs to query at a time
    retry_delay_seconds = 1 # Delay before retrying a failed batch
    sqs_queue_name = os.environ.get('SQS_QUEUE_NAME', 'bgg_game_data_scraper_queue') # New: SQS Queue Name

    s3 = boto3.client('s3', region_name=aws_region)
    sqs = boto3.client('sqs', region_name=aws_region) 
    start_id = None
    update_counter = 0 # Initialize counter for S3 updates

    try:
        # 1. Read starting ID from S3
        print(f"Attempting to read ID from s3://{s3_bucket_name}/{s3_key}")
        response = s3.get_object(Bucket=s3_bucket_name, Key=s3_key)
        start_id_str = response['Body'].read().decode('utf-8').strip()
        start_id = int(start_id_str)
        print(f"Successfully read starting ID: {start_id}")

    except s3.exceptions.NoSuchKey:
        print(f"Error: S3 key '{s3_key}' not found in bucket '{s3_bucket_name}'. Exiting.")
        sys.exit(1) # Exit with an error code
    except Exception as e:
        print(f"Error reading from S3: {e}. Exiting.")
        sys.exit(1) # Exit with an error code

    if start_id is None:
        print("Failed to retrieve a valid starting ID. Exiting.")
        sys.exit(1) # Exit with an error code

    # New: Get SQS queue URL
    try:
        sqs_queue_url = sqs.get_queue_url(QueueName=sqs_queue_name)['QueueUrl']
        print(f"Successfully retrieved SQS queue URL: {sqs_queue_url}")
    except Exception as e:
        print(f"Error getting SQS queue URL for '{sqs_queue_name}': {e}. Exiting.")
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
            print(f"Querying BGG API for IDs: {ids_param} (Attempt {retry_count + 1})")
            try:
                response = requests.get(api_url)
                response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
                xml_data = response.content
                print(f"Successfully received response for IDs {ids_param} from BGG API.")

                # 3. Parse XML response
                root = ET.fromstring(xml_data)

                # 4. Check if items exist and are of type 'boardgame'
                items_found = False
                for item in root.findall('item'): # Iterate through all 'item' elements
                    items_found = True
                    item_id = item.get('id')
                    item_type = item.get('type')
                    item_name_element = item.find("./name[@type='primary']")
                    item_name = item_name_element.get('value') if item_name_element is not None else "N/A"

                    print(f"Processing item ID: {item_id}, Type: {item_type}, Name: {item_name}")

                    if item_type == 'boardgame':
                        result_message = f"ID {item_id} is a boardgame: {item_name}"
                        print(result_message)
                        # New: Send message to SQS
                        try:
                            sqs.send_message(
                                QueueUrl=sqs_queue_url,
                                MessageBody=str(item_id)
                            )
                            print(f"Successfully sent ID {item_id} to SQS queue '{sqs_queue_name}'.")
                        except Exception as sqs_e:
                            print(f"Error sending ID {item_id} to SQS: {sqs_e}")
                            # This error is logged but does not stop the scraper,
                            # as the main goal is to continue scraping IDs.
                            # SQS messages can be retried by the Lambda consumer.
                    else:
                        result_message = f"ID {item_id} exists but is not a boardgame (Type: {item_type}). Name: {item_name}"
                        print(result_message)
                
                if not items_found and current_ids_batch[0] > 452300:
                    print(f"No items found in BGG API response for IDs: {ids_param}. Exiting.")
                    sys.exit(1) # Exit if no items are found in the response

                batch_succeeded = True # Mark success to break the retry loop

            except requests.exceptions.RequestException as e:
                print(f"Error querying BGG API for IDs {ids_param}: {e}. Retrying in {retry_delay_seconds} seconds.")
                retry_count += 1
                time.sleep(retry_delay_seconds)
            except ET.ParseError as e:
                print(f"Error parsing XML from BGG API for IDs {ids_param}: {e}. Retrying in {retry_delay_seconds} seconds.")
                retry_count += 1
                time.sleep(retry_delay_seconds)
            except Exception as e:
                print(f"An unexpected error occurred for IDs {ids_param}: {e}. Retrying in {retry_delay_seconds} seconds.")
                retry_count += 1
                time.sleep(retry_delay_seconds)

        if not batch_succeeded:
            print(f"Failed to process batch {ids_param}. Exiting.")
            sys.exit(1) # Exit if a batch consistently fails

        # If batch succeeded, update state and prepare for next batch
        start_id += batch_size
        update_counter += batch_size # Increment the counter by the batch size

        # 5. Update starting ID in S3 for persistence, only if counter reaches interval
        if update_counter >= s3_update_interval:
            print(f"Update interval reached. Attempting to update S3 with ID: {start_id}.")
            try:
                s3.put_object(Bucket=s3_bucket_name, Key=s3_key, Body=str(start_id).encode('utf-8'))
                print(f"Successfully updated S3 with new starting ID: {start_id}")
                update_counter = 0 # Reset counter after successful update
            except Exception as e:
                print(f"CRITICAL ERROR: Failed to update S3 with ID {start_id}: {e}. Exiting to prevent data loss.")
                sys.exit(1) # Exit if we can't persist the state
        else:
            print(f"Incremented ID to {start_id}. S3 update skipped (next update in {s3_update_interval - update_counter} IDs).")

        # Wait before the next request to respect API rate limits
        time.sleep(request_delay_seconds)

if __name__ == '__main__':
    # When running in an ECR container, this script will be executed directly.
    # Environment variables for S3_BUCKET_NAME and S3_KEY should be set in the container definition.
    main()
