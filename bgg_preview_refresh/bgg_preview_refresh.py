import os
import json
import boto3
import urllib.request
import urllib.error
import time
from datetime import datetime, timezone

s3 = boto3.client('s3')

def lambda_handler(event, context):
    bucket = os.environ.get('S3_BUCKET_NAME', 'boardgame-app')
    config_key = "data/active_previews.json"
    games_key = "data/active_previews_games.json"
    
    local_config_path = "/tmp/active_previews.json"
    local_games_path = "/tmp/active_previews_games.json"
    
    print(f"Downloading {config_key} from S3 bucket {bucket}...")
    try:
        s3.download_file(bucket, config_key, local_config_path)
    except Exception as e:
        print(f"Error downloading config: {e}. active_previews.json metadata configuration must exist in S3.")
        return {
            'statusCode': 500,
            'body': json.dumps(f"Failed to download config: {str(e)}")
        }
        
    with open(local_config_path, 'r', encoding='utf-8') as f:
        conventions = json.load(f)
        
    # Download existing games map or initialize empty
    games_map = {}
    try:
        print(f"Downloading existing games map {games_key}...")
        s3.download_file(bucket, games_key, local_games_path)
        with open(local_games_path, 'r', encoding='utf-8') as f:
            games_map = json.load(f)
    except Exception as e:
        print(f"No existing games map found or error downloading it: {e}. Starting fresh.")
        
    updated = False
    current_date = datetime.now(timezone.utc).date()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    bgg_api_token = os.environ.get('BGG_API_TOKEN')
    if bgg_api_token:
        headers["Authorization"] = f"Bearer {bgg_api_token}"

    for conv in conventions:
        conv_id = conv.get("convention_id")
        preview_id = conv.get("previewid")
        date_str = conv.get("date")
        
        # Check if convention is in the past
        try:
            conv_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            if conv_date < current_date:
                print(f"Skipping stale convention: {conv.get('name')} (Date: {date_str} is in the past)")
                # Clean up games map if it exists
                if conv_id in games_map:
                    del games_map[conv_id]
                    updated = True
                continue
        except Exception as date_err:
            print(f"Warning: Failed to parse date '{date_str}' for {conv_id}: {date_err}")
            
        print(f"Refreshing games for {conv.get('name')} (ID: {conv_id}, Preview: {preview_id})...")
        game_ids = []
        page = 1
        
        while True:
            url = f"https://boardgamegeek.com/api/geekpreviewitems?previewid={preview_id}&pageid={page}"
            print(f"  Fetching page {page}: {url}")
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    status = response.getcode()
                    if status != 200:
                        print(f"  Error: BGG API status code {status}. Stopping fetch.")
                        break
                    raw_text = response.read().decode('utf-8')
                    
                # Clean malformed JSON fields (e.g. '"dynamicinfo":}')
                cleaned_text = raw_text.replace('"dynamicinfo":}', '"dynamicinfo":null}')
                data = json.loads(cleaned_text)
                
                if not isinstance(data, list) or len(data) == 0:
                    print(f"  Reached end of list. Total pages fetched: {page - 1}")
                    break
                    
                for item in data:
                    g_id = str(item.get("objectid"))
                    if g_id and g_id not in game_ids:
                        game_ids.append(g_id)
                        
                time.sleep(0.1)
                page += 1
            except urllib.error.HTTPError as he:
                print(f"  HTTP Error fetching page {page}: {he.code} - {he.reason}. Stopping fetch.")
                break
            except Exception as e:
                print(f"  Error fetching page {page}: {e}. Stopping fetch.")
                break
                
        if len(game_ids) > 0:
            games_map[conv_id] = game_ids
            updated = True
            print(f"  Updated games map for {conv_id} to {len(game_ids)} items.")
        else:
            print(f"  No games found for {conv_id}. Keeping existing list of {len(games_map.get(conv_id, []))} items.")

    if updated:
        print(f"Uploading updated games map back to S3 bucket {bucket} at {games_key}...")
        with open(local_games_path, 'w', encoding='utf-8') as f:
            json.dump(games_map, f, indent=2, ensure_ascii=False)
        s3.upload_file(local_games_path, bucket, games_key)
        print("Upload completed successfully.")
    else:
        print("No active conventions updated. S3 games map file remains unchanged.")

    return {
        'statusCode': 200,
        'body': json.dumps("Refresh run finished successfully.")
    }
