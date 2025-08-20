import json
import requests
import xml.etree.ElementTree as ET
import os # Re-added for os.environ.get

import pandas as pd # New import for DataFrame operations
import pyarrow # Required by pandas for Parquet engine
import pyarrow.parquet as pq # Explicit import for clarity
import boto3 # Already imported, ensuring it's available for S3 client

S3_OUTPUT_BUCKET_NAME = os.environ.get('S3_OUTPUT_BUCKET_NAME', 'boardgame-app')

def _get_element_value(element, xpath, attribute='value', default=None):
    """Helper to safely get an attribute value from an XML element."""
    found_element = element.find(xpath)
    if found_element is not None:
        return found_element.get(attribute, default)
    return default

def get_user_data(username):
    """
    Queries the BoardGameGeek API for a user's collection data.
    Returns a dictionary with user collection information.
    """
    api_url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&subtype=boardgame&excludesubtype=boardgameexpansion&stats=1"
    print(f"Querying BGG API for user: {username} at {api_url}")

    try:
        response = requests.get(api_url)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        xml_data = response.content
        print(f"Successfully received response for user {username}.")

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")

        if items is None:
            print(f"No collection items found for user {username}.")
            return None

        user_data = []
        for item in items:
            
            def safe_float(val):
                try:
                    return float(val) if val is not None else None
                except (ValueError, TypeError):
                    return None
            rating = safe_float(_get_element_value(item, ".//stats/rating", attribute='value'))
            own = True if _get_element_value(item, ".//status", attribute='own') == '1' else False
            if rating or own:
                user_data.append({
                    'id': item.get('objectid'),
                    'username': username,
                    'rating': rating,
                    'own': own
                })
        return user_data

    except requests.RequestException as e:
        print(f"Error querying BGG API for user {username}: {e}")
        return None

def lambda_handler(event, context):
    """
    AWS Lambda handler function.
    Processes SQS events, extracts user IDs, queries BGG API,
    and retrieves user collection information.
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
            # SQS message body is expected to be a string
            user_id = record['body']
            print(f"Processing user ID from SQS: {user_id}")

            user_data = get_user_data(user_id)

            if user_data:
                print(f"Successfully retrieved data for user {user_id}.")

                # Convert user_data to pandas DataFrame
                df = pd.DataFrame(user_data)

                # Define S3 path for the Parquet file
                # Recommended: Write each game to a unique Parquet file, potentially partitioned.
                # Example: s3://your-boardgame-data-bucket/boardgames/year_published=YYYY/game_id.parquet
                # For this example, we'll use a simple key based on user_id.
                s3_output_key = f"users/{user_id}.parquet"
                s3_full_path = f"s3://{S3_OUTPUT_BUCKET_NAME}/data/{s3_output_key}"

                try:
                    # Save DataFrame to S3 in Parquet format
                    df.to_parquet(s3_full_path, index=False, engine='pyarrow')
                    print(f"Successfully saved data for user {user_id} to S3: {s3_full_path}")
                    processed_ids.append(user_id)
                except Exception as s3_e:
                    print(f"Error saving data for user {user_id} to S3 ({s3_full_path}): {s3_e}")
                    failed_ids.append(user_id)
                    batch_item_failures.append({"itemIdentifier": record['messageId']})
            else:
                print(f"Failed to retrieve data for user {user_id}.")
                failed_ids.append(user_id)
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

if __name__ == '__main__':
    # Mock SQS event for local testing
    mock_event = {
        "Records": [
            {
                "messageId": "msg1",
                "body": "bionicle4365",
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