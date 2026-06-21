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

# BGG API base URL
BGG_API_BASE_URL = "https://boardgamegeek.com/xmlapi2/thing"

# S3 output bucket name (get from environment variable)
S3_OUTPUT_BUCKET_NAME = os.environ.get('S3_OUTPUT_BUCKET_NAME', 'boardgame-app')

# Sentinel to distinguish "fetch failed" from "not found"
GAME_FETCH_FAILED = object()

# PyArrow schema — defined once at module level to avoid rebuilding per record.
_PARQUET_SCHEMA = pyarrow.schema([
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

def _parse_item(item):
    """Parse a single <item> XML element into a game data dict."""
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

    best_players = []
    rec_players = []
    poll = item.find(".//poll[@name='suggested_numplayers']")
    if poll is not None:
        for results in poll.findall('results'):
            num_players = results.get('numplayers')
            best_votes = rec_votes = not_rec_votes = 0
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

    return {
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


def get_batch_game_data(game_ids, max_retries=5, base_delay=2):
    """
    Fetch data for multiple game IDs in a SINGLE BGG API call.

    BGG supports comma-separated IDs: ?id=1,2,3&stats=1
    BGG API enforces a maximum of 20 IDs per request.

    Returns:
        dict mapping str(game_id) -> game_data dict for games that exist
        Games not found in the response are silently omitted (not DLQ'd).
        Returns GAME_FETCH_FAILED sentinel if the API call itself fails after all retries.
    """
    if len(game_ids) > 20:
        raise ValueError(f"get_batch_game_data called with {len(game_ids)} IDs, which exceeds BGG limit of 20.")
        
    ids_str = ','.join(str(gid) for gid in game_ids)
    api_url = f"{BGG_API_BASE_URL}?id={ids_str}&stats=1"

    bgg_api_token = os.environ.get('BGG_API_TOKEN')
    headers = {}
    if bgg_api_token:
        headers["Authorization"] = f"Bearer {bgg_api_token}"

    for attempt in range(max_retries):
        print(f"Querying BGG API for {len(game_ids)} IDs (batch): {ids_str[:80]}... (Attempt {attempt + 1}/{max_retries})")
        try:
            response = requests.get(api_url, headers=headers)
            response.raise_for_status()
            root = ET.fromstring(response.content)

            results = {}
            for item in root.findall('item'):
                game_data = _parse_item(item)
                item_id = item.get('id')
                results[item_id] = game_data
                print(f"Parsed game {item_id}: {game_data.get('name', '?')!r}")

            print(f"BGG batch response: {len(results)} of {len(game_ids)} IDs found.")
            return results

        except (requests.exceptions.RequestException, ET.ParseError, Exception) as e:
            print(f"Error in batch BGG API call (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                delay = min(60, base_delay * (2 ** attempt))
                jittered_delay = delay / 2.0 + random.uniform(0, delay / 2.0)
                print(f"Retrying in {jittered_delay:.2f} seconds...")
                time.sleep(jittered_delay)
            else:
                print(f"Max retries reached for batch. Marking all {len(game_ids)} as failed.")
                return GAME_FETCH_FAILED


# Keep single-ID version for backward compatibility with tests
def get_game_data(game_id, max_retries=5, base_delay=2):
    """
    Queries the BGG API for a single game ID.

    Returns:
        dict  - game data on success
        None  - game not found on BGG (graceful, don't DLQ)
        GAME_FETCH_FAILED sentinel - API/network error after all retries (should DLQ)
    """
    result = get_batch_game_data([game_id], max_retries=max_retries, base_delay=base_delay)
    if result is GAME_FETCH_FAILED:
        return GAME_FETCH_FAILED
    return result.get(str(game_id), None)  # None if not found


def lambda_handler(event, context):
    """
    AWS Lambda handler function.

    Processes incoming game IDs in chunks of at most 20 IDs to respect BGG API limits.
    For each chunk, queries the BGG API in a single request and writes the returned
    games to S3.
    """
    print(f"Received event: {json.dumps(event)}")

    if 'Records' not in event:
        print("No records found in the SQS event.")
        return {
            'statusCode': 400,
            'body': json.dumps('No SQS records found.')
        }

    records = event['Records']
    processed_ids = []
    failed_ids = []
    batch_item_failures = []

    # Build a map of game_id -> record so we can attribute results back to messageIds
    id_to_record = {}
    invalid_records = []
    valid_game_ids = []

    for record in records:
        body = record.get('body', '')
        try:
            game_id = int(body)
            id_to_record[str(game_id)] = record
            valid_game_ids.append(game_id)
        except (ValueError, TypeError):
            print(f"Invalid game ID in SQS body: {body!r} (messageId={record.get('messageId')})")
            invalid_records.append(record)
            failed_ids.append(body)
            batch_item_failures.append({'itemIdentifier': record['messageId']})

    # --- Batch process game IDs in chunks of at most 20 ---
    BGG_MAX_BATCH_SIZE = 20
    if valid_game_ids:
        for i in range(0, len(valid_game_ids), BGG_MAX_BATCH_SIZE):
            chunk_ids = valid_game_ids[i:i + BGG_MAX_BATCH_SIZE]
            print(f"Processing chunk {i // BGG_MAX_BATCH_SIZE + 1}: {len(chunk_ids)} game IDs.")

            batch_result = get_batch_game_data(chunk_ids)

            if batch_result is GAME_FETCH_FAILED:
                # Entire chunk failed (network/API error) — route all chunk IDs to DLQ
                print(f"Batch API call failed for chunk. Routing all {len(chunk_ids)} IDs to DLQ.")
                for gid in chunk_ids:
                    rec = id_to_record[str(gid)]
                    failed_ids.append(gid)
                    batch_item_failures.append({'itemIdentifier': rec['messageId']})
            else:
                for gid in chunk_ids:
                    gid_str = str(gid)
                    rec = id_to_record[gid_str]

                    if gid_str not in batch_result:
                        # Game not found on BGG — graceful skip, delete from queue
                        print(f"Game ID {gid} not found on BGG. Skipping gracefully (no DLQ).")
                        processed_ids.append(gid)
                        continue

                    game_data = batch_result[gid_str]
                    s3_path = f"s3://{S3_OUTPUT_BUCKET_NAME}/data/boardgames/{gid}.parquet"
                    try:
                        df = pd.DataFrame([game_data])
                        df.to_parquet(s3_path, index=False, engine='pyarrow', schema=_PARQUET_SCHEMA)
                        print(f"Saved game {gid} ({game_data.get('name', '?')!r}) -> {s3_path}")
                        processed_ids.append(gid)
                    except Exception as s3_e:
                        print(f"S3 write failed for ID {gid}: {s3_e}")
                        failed_ids.append(gid)
                        batch_item_failures.append({'itemIdentifier': rec['messageId']})

            # Sleep between chunks to respect BGG API rate limits
            if i + BGG_MAX_BATCH_SIZE < len(valid_game_ids):
                print("Sleeping 1.0 second before the next chunk request...")
                time.sleep(1.0)

    if batch_item_failures:
        print(f"Finished: {len(processed_ids)} succeeded, {len(batch_item_failures)} failed.")
        return {
            'statusCode': 207,
            'body': json.dumps({
                'message': 'Some IDs processed with failures.',
                'processed_ids': processed_ids,
                'failed_ids': failed_ids
            }),
            'batchItemFailures': batch_item_failures
        }
    else:
        print(f"Finished: all {len(processed_ids)} IDs processed successfully.")
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'All IDs processed successfully.',
                'processed_ids': processed_ids
            })
        }


# Example of how to run locally for testing (this block is not executed in Lambda)
if __name__ == '__main__':
    mock_event = {
        "Records": [
            {"messageId": "msg1", "body": "13",        "attributes": {}, "messageAttributes": {}, "md5OfBody": "", "eventSource": "aws:sqs", "eventSourceARN": "", "awsRegion": ""},
            {"messageId": "msg2", "body": "174430",    "attributes": {}, "messageAttributes": {}, "md5OfBody": "", "eventSource": "aws:sqs", "eventSourceARN": "", "awsRegion": ""},
            {"messageId": "msg3", "body": "999999999", "attributes": {}, "messageAttributes": {}, "md5OfBody": "", "eventSource": "aws:sqs", "eventSourceARN": "", "awsRegion": ""},
            {"messageId": "msg4", "body": "not_an_int","attributes": {}, "messageAttributes": {}, "md5OfBody": "", "eventSource": "aws:sqs", "eventSourceARN": "", "awsRegion": ""},
        ]
    }
    print("--- Running local test ---")
    lambda_handler(mock_event, None)
    print("--- Local test complete ---")
