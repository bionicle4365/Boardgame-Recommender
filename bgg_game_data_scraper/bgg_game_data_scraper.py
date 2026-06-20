import json
import requests
import xml.etree.ElementTree as ET
import os # Re-added for os.environ.get
import random
import time

import pandas as pd # New import for DataFrame operations
import pyarrow # Required by pandas for Parquet engine
import pyarrow.parquet as pq # Explicit import for clarity
import boto3 # Already imported, ensuring it's available for S3 client

# BGG API base URL
BGG_API_BASE_URL = "https://boardgamegeek.com/xmlapi2/thing"

# S3 output bucket name (get from environment variable)
# IMPORTANT: Ensure S3_OUTPUT_BUCKET_NAME environment variable is set in your Lambda configuration.
S3_OUTPUT_BUCKET_NAME = os.environ.get('S3_OUTPUT_BUCKET_NAME', 'boardgame-app')

# Initialize S3 client is not strictly needed here as pandas handles S3 paths directly with fsspec/s3fs.
# s3_client = boto3.client('s3') # Removed as it's not directly used for pandas S3 operations

def _get_element_value(element, xpath, attribute='value', default=None):
    """Helper to safely get an attribute value from an XML element."""
    found_element = element.find(xpath)
    if found_element is not None:
        return found_element.get(attribute, default)
    return default

def _get_element_text(element, xpath, default=None):
    """Helper to safely get text from an XML element."""
    found_element = element.find(xpath)
    if found_element is not None and found_element.text is not None:
        # Replace &#10; (HTML entity for newline) with a space
        return found_element.text.strip().replace('&#10;', ' ')
    return default

def _get_links(item_element, link_type):
    """Helper to get a list of values for a specific link type."""
    links = []
    for link in item_element.findall(f"./link[@type='{link_type}']"):
        value = link.get('value')
        if value:
            links.append(value)
    return links

# Sentinel to distinguish "fetch failed" from "not found"
GAME_FETCH_FAILED = object()

def get_game_data(game_id, max_retries=5, base_delay=2):
    """
    Queries the BoardGameGeek API for a given game ID and extracts relevant data.

    Returns:
        dict  - game data on success
        None  - game not found on BGG (graceful, don't DLQ)
        GAME_FETCH_FAILED sentinel - API/network error after all retries (should DLQ)
    """
    api_url = f"{BGG_API_BASE_URL}?id={game_id}&stats=1"

    bgg_api_token = os.environ.get('BGG_API_TOKEN')
    headers = {}
    if bgg_api_token:
        headers["Authorization"] = f"Bearer {bgg_api_token}"

    for attempt in range(max_retries):
        print(f"Querying BGG API for ID: {game_id} at {api_url} (Attempt {attempt + 1}/{max_retries})")
        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
            xml_data = response.content
            print(f"Successfully received response for ID {game_id}.")

            root = ET.fromstring(xml_data)
            item = root.find('item')

            if item is None:
                print(f"No item found for ID {game_id} in BGG API response. Game may not exist or has been removed.")
                return None  # Graceful: not a failure, just not found

            # Helper to convert string to int/float safely
            def safe_int(val):
                try:
                    return int(val) if val is not None else None
                except (ValueError, TypeError):
                    return None

            def safe_float(val):
                try:
                    return float(val) if val is not None else None
                except (ValueError, TypeError):
                    return None

            # Parse suggested player counts
            best_players = []
            rec_players = []
            poll = item.find(".//poll[@name='suggested_numplayers']")
            if poll is not None:
                for results in poll.findall('results'):
                    num_players = results.get('numplayers')
                    best_votes = 0
                    rec_votes = 0
                    not_rec_votes = 0
                    for result in results.findall('result'):
                        val = result.get('value')
                        votes = safe_int(result.get('numvotes', 0)) or 0
                        if val == 'Best':
                            best_votes = votes
                        elif val == 'Recommended':
                            rec_votes = votes
                        elif val == 'Not Recommended':
                            not_rec_votes = votes
                    
                    total_votes = best_votes + rec_votes + not_rec_votes
                    if total_votes > 0:
                        if best_votes > rec_votes and best_votes > not_rec_votes:
                            best_players.append(num_players)
                        if (best_votes + rec_votes) > not_rec_votes:
                            rec_players.append(num_players)

            game_data = {
                'id': item.get('id'),
                'type': item.get('type'),
                'name': _get_element_value(item, "./name[@type='primary']"),
                'year_published': safe_int(_get_element_value(item, 'yearpublished', attribute='value')),
                'min_players': safe_int(_get_element_value(item, 'minplayers', attribute='value')),
                'max_players': safe_int(_get_element_value(item, 'maxplayers', attribute='value')),
                'playing_time': safe_int(_get_element_value(item, 'playingtime', attribute='value')),
                'min_playtime': safe_int(_get_element_value(item, 'minplaytime', attribute='value')),
                'max_playtime': safe_int(_get_element_value(item, 'maxplaytime', attribute='value')),
                'min_age': safe_int(_get_element_value(item, 'minage', attribute='value')),
                'rating': safe_float(_get_element_value(item, ".//statistics/ratings/bayesaverage", attribute='value')),
                'complexity': safe_float(_get_element_value(item, ".//statistics/ratings/averageweight", attribute='value')),
                'thumbnail': _get_element_text(item, 'thumbnail'),
                'image': _get_element_text(item, 'image'),
                'categories': _get_links(item, 'boardgamecategory'),
                'mechanics': _get_links(item, 'boardgamemechanic'),
                'designers': _get_links(item, 'boardgamedesigner'),
                'publishers': _get_links(item, 'boardgamepublisher'),
                'suggested_players_best': best_players,
                'suggested_players_recommended': rec_players,
            }
            print(f"Extracted game data for ID {game_id}: {json.dumps(game_data, ensure_ascii=True)}")
            return game_data

        except (requests.exceptions.RequestException, ET.ParseError, Exception) as e:
            print(f"Error querying BGG API for ID {game_id}: {e}")
            if attempt < max_retries - 1:
                # Exponential backoff with random jitter (base of 2 seconds, max of 60 seconds)
                delay = min(60, base_delay * (2 ** attempt))
                jittered_delay = delay / 2.0 + random.uniform(0, delay / 2.0)
                print(f"Retrying in {jittered_delay:.2f} seconds...")
                time.sleep(jittered_delay)
            else:
                print(f"Max retries reached for ID {game_id}. Marking as fetch failure for DLQ.")
                return GAME_FETCH_FAILED  # Real failure: should be retried via DLQ

def lambda_handler(event, context):
    """
    AWS Lambda handler function.
    Processes SQS events, extracts board game IDs, queries BGG API,
    and retrieves game information.
    """
    print(f"Received event: {json.dumps(event)}")

    if 'Records' not in event:
        print("No records found in the SQS event.")
        return {
            'statusCode': 400,
            'body': json.dumps('No SQS records found.')
        }

    processed_ids = []
    failed_ids = [] # Keep for logging/debugging purposes if needed
    batch_item_failures = [] # List to store messageIds of failed records

    for record in event['Records']:
        try:
            # SQS message body is expected to be a string representation of an integer ID
            game_id_str = record['body']
            game_id = int(game_id_str)
            print(f"Processing game ID from SQS: {game_id}")

            game_data = get_game_data(game_id)

            if game_data is GAME_FETCH_FAILED:
                # Real API/network failure after all retries — route to DLQ for retry
                print(f"Fetch failed for ID {game_id} after all retries. Routing to DLQ.")
                failed_ids.append(game_id)
                batch_item_failures.append({"itemIdentifier": record['messageId']})
            elif game_data is None:
                # Game doesn't exist on BGG (deleted, gap in ID space, accessory, etc.)
                # This is NOT a failure — treat as successfully processed (message deleted from queue).
                print(f"Game ID {game_id} not found on BGG. Skipping gracefully (no DLQ).")
                processed_ids.append(game_id)
            else:
                print(f"Successfully retrieved data for ID {game_id}: {repr(game_data.get('name', 'N/A'))}")

                # Convert game_data to pandas DataFrame
                df = pd.DataFrame([game_data])

                s3_output_key = f"boardgames/{game_id}.parquet"
                s3_full_path = f"s3://{S3_OUTPUT_BUCKET_NAME}/data/{s3_output_key}"

                try:
                    # Enforce strict PyArrow schema to prevent type mismatches on empty lists
                    schema = pyarrow.schema([
                        ('id', pyarrow.string()),
                        ('type', pyarrow.string()),
                        ('name', pyarrow.string()),
                        ('year_published', pyarrow.int32()),
                        ('min_players', pyarrow.int32()),
                        ('max_players', pyarrow.int32()),
                        ('playing_time', pyarrow.int32()),
                        ('min_playtime', pyarrow.int32()),
                        ('max_playtime', pyarrow.int32()),
                        ('min_age', pyarrow.int32()),
                        ('rating', pyarrow.float64()),
                        ('complexity', pyarrow.float64()),
                        ('thumbnail', pyarrow.string()),
                        ('image', pyarrow.string()),
                        ('categories', pyarrow.list_(pyarrow.string())),
                        ('mechanics', pyarrow.list_(pyarrow.string())),
                        ('designers', pyarrow.list_(pyarrow.string())),
                        ('publishers', pyarrow.list_(pyarrow.string())),
                        ('suggested_players_best', pyarrow.list_(pyarrow.string())),
                        ('suggested_players_recommended', pyarrow.list_(pyarrow.string()))
                    ])
                    # Save DataFrame to S3 in Parquet format with explicit schema
                    df.to_parquet(s3_full_path, index=False, engine='pyarrow', schema=schema)
                    print(f"Successfully saved data for ID {game_id} to S3: {s3_full_path}")
                    processed_ids.append(game_id)
                except Exception as s3_e:
                    print(f"Error saving data for ID {game_id} to S3 ({s3_full_path}): {s3_e}")
                    failed_ids.append(game_id)
                    batch_item_failures.append({"itemIdentifier": record['messageId']})

        except ValueError:
            print(f"Error: SQS message body '{record.get('body')}' is not a valid integer ID. MessageId: {record.get('messageId')}")
            failed_ids.append(record.get('body'))
            batch_item_failures.append({"itemIdentifier": record['messageId']})
        except Exception as e:
            print(f"An error occurred while processing record: {record.get('messageId')}, Error: {e}")
            failed_ids.append(record.get('body'))
            batch_item_failures.append({"itemIdentifier": record['messageId']})

    if batch_item_failures:
        print(f"Finished processing. Successfully processed: {len(processed_ids)} IDs. Failed to process: {len(batch_item_failures)} records.")
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
        print(f"Finished processing. Successfully processed all {len(processed_ids)} IDs.")
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'All IDs processed successfully.',
                'processed_ids': processed_ids
            })
        }

# Example of how to run locally for testing (this block is not executed in Lambda)
if __name__ == '__main__':
    # Mock SQS event for local testing
    mock_event = {
        "Records": [
            {
                "messageId": "msg1",
                "body": "13", # Catan
                "attributes": {}, "messageAttributes": {}, "md5OfBody": "", "eventSource": "aws:sqs", "eventSourceARN": "", "awsRegion": ""
            },
            {
                "messageId": "msg2",
                "body": "174430", # Gloomhaven
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
