import json
import requests
import xml.etree.ElementTree as ET
import os
import random
import time

import pandas as pd
import pyarrow
import pyarrow.parquet as pq
import boto3
# Initialize Structured Logging with AWS Lambda Powertools or Fallback
try:
    from aws_lambda_powertools import Logger
    logger = Logger(service="bgg-user-data-scraper")
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    class FallbackLogger:
        def __init__(self):
            self.log = logging.getLogger("bgg-user-data-scraper")
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

S3_OUTPUT_BUCKET_NAME = os.environ.get('S3_OUTPUT_BUCKET_NAME', 'boardgame-app')

def _get_element_value(element, xpath, attribute='value', default=None):
    """Helper to safely get an attribute value from an XML element."""
    found_element = element.find(xpath)
    if found_element is not None:
        return found_element.get(attribute, default)
    return default

def safe_int(val):
    try:
        return int(val) if val is not None else None
    except (ValueError, TypeError):
        return None

def get_user_data(username, is_cafe=False):
    """
    Queries the BoardGameGeek API for a user's or cafe's collection data.
    If is_cafe is True, filters strictly for owned games (own=1) and extracts
    rich catalog metadata.
    Returns a list of dictionaries with collection information.
    """
    api_url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&subtype=boardgame&excludesubtype=boardgameexpansion&stats=1"
    logger.info(f"Querying BGG API for user: {username} at {api_url} (is_cafe={is_cafe})")

    retries = 3
    for i in range(retries):
        try:
            bgg_api_token = os.environ.get('BGG_API_TOKEN')
            headers = {}
            if bgg_api_token:
                headers["Authorization"] = f"Bearer {bgg_api_token}"
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
            xml_data = response.content
            logger.info(f"Successfully received response for user {username}.")

            root = ET.fromstring(xml_data)
            
            # Check for BGG API errors (e.g., non-existent user)
            if root.tag == 'errors':
                error_msg = root.find(".//error/message")
                error_text = error_msg.text if error_msg is not None else "Invalid username specified"
                logger.error(f"BGG API returned error for user {username}: {error_text}")
                return [] # Gracefully return empty list

            items = root.findall(".//item")
            if root.text and "accepted" in root.text:
                raise ValueError(f"BGG API message for {username}: {root.text}")

            if not items:
                logger.warning(f"No collection items found for user {username}.")
                return None

            def safe_float(val):
                try:
                    return float(val) if val is not None else None
                except (ValueError, TypeError):
                    return None

            if is_cafe:
                cafe_data = []
                for item in items:
                    own = _get_element_value(item, ".//status", attribute='own') == '1'
                    if not own:
                        continue
                    name_elem = item.find('name')
                    name = name_elem.text.strip() if (name_elem is not None and name_elem.text) else ''
                    year_elem = item.find('yearpublished')
                    year_published = safe_int(year_elem.text) if (year_elem is not None and year_elem.text) else None
                    image_elem = item.find('image')
                    image = image_elem.text.strip() if (image_elem is not None and image_elem.text) else ''
                    thumb_elem = item.find('thumbnail')
                    thumbnail = thumb_elem.text.strip() if (thumb_elem is not None and thumb_elem.text) else ''

                    min_players = safe_int(_get_element_value(item, ".//stats", attribute='minplayers'))
                    max_players = safe_int(_get_element_value(item, ".//stats", attribute='maxplayers'))
                    playing_time = safe_int(_get_element_value(item, ".//stats", attribute='playingtime'))
                    min_playtime = safe_int(_get_element_value(item, ".//stats", attribute='minplaytime'))
                    max_playtime = safe_int(_get_element_value(item, ".//stats", attribute='maxplaytime'))

                    rating = safe_float(_get_element_value(item, ".//stats/rating", attribute='value'))
                    avg_rating = safe_float(_get_element_value(item, ".//stats/rating/average", attribute='value'))
                    users_rated = safe_int(_get_element_value(item, ".//stats/rating/usersrated", attribute='value'))
                    num_owned = safe_int(_get_element_value(item, ".//stats", attribute='numowned'))

                    cafe_data.append({
                        'id': str(item.get('objectid')),
                        'name': name,
                        'year_published': year_published,
                        'min_players': min_players,
                        'max_players': max_players,
                        'playing_time': playing_time,
                        'min_playtime': min_playtime,
                        'max_playtime': max_playtime,
                        'thumbnail': thumbnail,
                        'image': image,
                        'rating': rating,
                        'average_rating': avg_rating,
                        'users_rated': users_rated,
                        'num_owned': num_owned,
                        'own': True
                    })
                return cafe_data

            user_data = []
            for item in items:
                rating = safe_float(_get_element_value(item, ".//stats/rating", attribute='value'))
                own = _get_element_value(item, ".//status", attribute='own') == '1'
                # rating=0.0 is falsy; on BGG this means "not rated", so we intentionally skip it
                if rating or own:
                    user_data.append({
                        'id': item.get('objectid'),
                        'username': username,
                        'rating': rating,
                        'own': own
                    })
            return user_data

        except Exception as e:
            logger.error(f"Error querying BGG API for user {username}: {e}")
            if i < retries - 1:
                # Exponential backoff with random jitter (base = 10, max = 60)
                delay = min(60, 10 * (2 ** i))
                jittered_delay = delay / 2.0 + random.uniform(0, delay / 2.0)
                logger.info(f"Retrying in {jittered_delay:.2f} seconds...")
                time.sleep(jittered_delay)
            else:
                logger.error(f"Max retries reached for user {username}.")
                return None

@logger.inject_lambda_context
def lambda_handler(event, context):
    """
    AWS Lambda handler function.
    Processes SQS events, extracts user IDs or cafe sync payloads, queries BGG API,
    and retrieves collection information into S3 Parquet.
    """
    logger.info("Received event", extra={"event": event})

    if 'Records' not in event:
        logger.warning("No records found in the SQS event.")
        return {
            'statusCode': 400,
            'body': json.dumps('No SQS records found.')
        }

    processed_ids = []
    failed_ids = [] # Keep for logging/debugging purposes if needed
    batch_item_failures = [] # List to store messageIds of failed records

    for record in event['Records']:
        try:
            body_raw = record['body']
            is_cafe = False
            cafe_id = None
            try:
                parsed = json.loads(body_raw)
                if isinstance(parsed, dict):
                    user_id = parsed.get('username') or parsed.get('user_id')
                    is_cafe = bool(parsed.get('is_cafe', False))
                    cafe_id = parsed.get('cafe_id') or user_id
                else:
                    user_id = str(parsed)
            except (json.JSONDecodeError, TypeError):
                user_id = body_raw

            logger.info(f"Processing ID from SQS: {user_id} (is_cafe={is_cafe}, cafe_id={cafe_id})")

            collection_data = get_user_data(user_id, is_cafe=is_cafe)

            if collection_data is not None:
                logger.info(f"Successfully retrieved data for {user_id} (is_cafe={is_cafe}). Collection size: {len(collection_data)}")

                if is_cafe:
                    cols = [
                        'id', 'name', 'year_published', 'min_players', 'max_players',
                        'playing_time', 'min_playtime', 'max_playtime', 'thumbnail',
                        'image', 'rating', 'average_rating', 'users_rated', 'num_owned', 'own'
                    ]
                    df = pd.DataFrame(collection_data, columns=cols)
                    s3_output_key = f"cafes/{cafe_id}/collection.parquet"
                else:
                    cols = ['id', 'username', 'rating', 'own']
                    df = pd.DataFrame(collection_data, columns=cols)
                    s3_output_key = f"users/{user_id}.parquet"

                s3_full_path = f"s3://{S3_OUTPUT_BUCKET_NAME}/data/{s3_output_key}"

                try:
                    df.to_parquet(s3_full_path, index=False, engine='pyarrow')
                    logger.info(f"Successfully saved data for {user_id} to S3: {s3_full_path}")
                    processed_ids.append(user_id)
                except Exception as s3_e:
                    logger.error(f"Error saving data for {user_id} to S3 ({s3_full_path}): {s3_e}")
                    failed_ids.append(user_id)
                    batch_item_failures.append({"itemIdentifier": record['messageId']})
            else:
                logger.error(f"Failed to retrieve data for {user_id} (retries exhausted).")
                failed_ids.append(user_id)
                batch_item_failures.append({"itemIdentifier": record['messageId']})

        except Exception as e:
            logger.error(f"An error occurred while processing record: {record.get('messageId')}, Error: {e}")
            failed_ids.append(record.get('body'))
            batch_item_failures.append({"itemIdentifier": record['messageId']})

    if batch_item_failures:
        logger.warning(f"Finished processing with failures. Successfully processed: {len(processed_ids)} IDs. Failed to process: {len(batch_item_failures)} records.")
        return {
            'statusCode': 207, # Multi-Status
            'body': json.dumps({
                'message': 'Some IDs processed with failures.',
                'processed_ids': processed_ids,
                'failed_ids': failed_ids
            }),
            'batchItemFailures': batch_item_failures
        }
    else:
        logger.info(f"Finished processing. Successfully processed all {len(processed_ids)} IDs.")
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'All IDs processed successfully.',
                'processed_ids': processed_ids
            })
        }

if __name__ == '__main__':
    # Mock SQS event for local testing
    mock_event = {
        "Records": [
            {
                "messageId": "msg1",
                "body": "gamer_demo",
                "attributes": {}, "messageAttributes": {}, "md5OfBody": "", "eventSource": "aws:sqs", "eventSourceARN": "", "awsRegion": ""
            },
            {
                "messageId": "msg2",
                "body": "janeivy11",
                "attributes": {}, "messageAttributes": {}, "md5OfBody": "", "eventSource": "aws:sqs", "eventSourceARN": "", "awsRegion": ""
            },
            {
                "messageId": "msg3",
                "body": "999999999", # Non-existent ID
                "attributes": {}, "messageAttributes": {}, "md5OfBody": "", "eventSource": "aws:sqs", "eventSourceARN": "", "awsRegion": ""
            },
            {
                "messageId": "msg4",
                "body": "not_an_int", # Invalid ID
                "attributes": {}, "messageAttributes": {}, "md5OfBody": "", "eventSource": "aws:sqs", "eventSourceARN": "", "awsRegion": ""
            }
        ]
    }
    print("--- Running local test ---")
    lambda_handler(mock_event, None)
    print("--- Local test complete ---")

    # Test with an empty event
    print("\n--- Running local test with empty event ---")
    lambda_handler({}, None)
    print("--- Local test complete ---")

    # Test with an event with no records
    print("\n--- Running local test with no records ---")
    lambda_handler({"Records": []}, None)
    print("--- Local test complete ---")