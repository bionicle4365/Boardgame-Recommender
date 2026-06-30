import os
import json
import boto3
import urllib.request
import urllib.error
import time
from datetime import datetime, timezone, timedelta

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
        
    current_date = datetime.now(timezone.utc).date()
    
    # Classify existing conventions
    active_convs = []
    passed_convs = []
    
    for conv in conventions:
        date_str = conv.get("date")
        is_past = False
        try:
            conv_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            if conv_date < current_date:
                is_past = True
        except Exception as date_err:
            print(f"Warning: Failed to parse date '{date_str}' for {conv.get('convention_id')}: {date_err}")
            
        if is_past:
            passed_convs.append(conv)
        else:
            active_convs.append(conv)
            
    # Find max preview ID across all loaded conventions
    max_preview_id = 0
    if conventions:
        max_preview_id = max(conv.get("previewid", 0) for conv in conventions)
        
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    bgg_api_token = os.environ.get('BGG_API_TOKEN')
    if bgg_api_token:
        headers["Authorization"] = f"Bearer {bgg_api_token}"
        
    # Auto-discover new active previews
    next_id = max_preview_id + 1
    discovered_convs = []
    print(f"Checking for new active previews starting from ID {next_id}...")
    
    while True:
        url = f"https://boardgamegeek.com/api/geekpreview/{next_id}"
        print(f"Checking if preview ID {next_id} is active: {url}")
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                status = response.getcode()
                if status != 200:
                    print(f"  Received status code {status} for ID {next_id}. Stopping search.")
                    break
                raw_text = response.read().decode('utf-8')
                
            data = json.loads(raw_text)
            
            if isinstance(data, dict) and "previewid" in data:
                title = data.get("title", f"Preview {next_id}")
                end_date = data.get("end_date")
                linkname = data.get("linkname", f"preview_{next_id}")
                
                # Format a convention_id: e.g. gen-con-2026-preview -> gencon2026
                conv_id = linkname.replace("-preview", "").replace("-", "")
                
                # If end_date is missing or invalid, default to start_date or 90 days out
                if not end_date:
                    end_date = data.get("start_date")
                if not end_date:
                    end_date = (current_date + timedelta(days=90)).strftime("%Y-%m-%d")
                    
                print(f"  Found active preview ID {next_id}: {title} (Ends: {end_date})")
                new_conv = {
                    "convention_id": conv_id,
                    "name": title,
                    "date": end_date,
                    "previewid": next_id
                }
                discovered_convs.append(new_conv)
                next_id += 1
                time.sleep(0.5)  # Throttle requests slightly
            else:
                print(f"  Preview ID {next_id} is not active. Stopping search.")
                break
        except urllib.error.HTTPError as he:
            if he.code == 404:
                print(f"  Preview ID {next_id} not found (404). Stopping search.")
            else:
                print(f"  HTTP Error {he.code} checking ID {next_id}. Stopping search.")
            break
        except Exception as e:
            print(f"  Error checking ID {next_id}: {e}. Stopping search.")
            break
            
    # Add newly discovered conventions to active list
    if discovered_convs:
        active_convs.extend(discovered_convs)
        
    # Construct final conventions list to save
    conventions_to_save = []
    if active_convs:
        conventions_to_save = active_convs
    elif passed_convs:
        # If no active conventions (original or discovered) exist, we must keep
        # exactly one passed convention as a seed ID to start searching from next time.
        # We pick the one with the highest previewid.
        seed_conv = max(passed_convs, key=lambda c: c.get("previewid", 0))
        conventions_to_save = [seed_conv]
        print(f"No active conventions found. Keeping {seed_conv.get('convention_id')} as seed.")
        
    # Check if the active_previews.json file should be updated on S3
    original_ids = sorted(conv.get("previewid") for conv in conventions)
    to_save_ids = sorted(conv.get("previewid") for conv in conventions_to_save)
    
    config_updated = (original_ids != to_save_ids)
    
    # We will fetch items ONLY for conventions in conventions_to_save that are NOT passed (stale)
    passed_ids = {c.get("convention_id") for c in passed_convs}
    
    games_map_updated = False
    
    # Process each convention we need to save
    for conv in conventions_to_save:
        conv_id = conv.get("convention_id")
        preview_id = conv.get("previewid")
        
        # If it is in passed_convs, it shouldn't pull items
        if conv_id in passed_ids:
            if conv_id in games_map:
                print(f"Removing games for passed convention {conv_id} from games map.")
                del games_map[conv_id]
                games_map_updated = True
            continue
            
        # Otherwise, retrieve or update games for this active/discovered convention
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
            if games_map.get(conv_id) != game_ids:
                games_map[conv_id] = game_ids
                games_map_updated = True
                print(f"  Updated games map for {conv_id} to {len(game_ids)} items.")
            else:
                print(f"  Games map for {conv_id} is already up to date ({len(game_ids)} items).")
        else:
            print(f"  No games found for {conv_id}. Keeping existing list of {len(games_map.get(conv_id, []))} items.")
            
    # Also clean up any other key in games_map that is not in conventions_to_save
    active_saved_ids = {c.get("convention_id") for c in conventions_to_save}
    for gid in list(games_map.keys()):
        if gid not in active_saved_ids:
            print(f"Cleaning up untracked convention {gid} from games map.")
            del games_map[gid]
            games_map_updated = True
            
    # Upload updated configuration back to S3
    if config_updated:
        print(f"Uploading updated configuration back to S3 bucket {bucket} at {config_key}...")
        with open(local_config_path, 'w', encoding='utf-8') as f:
            json.dump(conventions_to_save, f, indent=2, ensure_ascii=False)
        s3.upload_file(local_config_path, bucket, config_key)
        print("Configuration upload completed successfully.")
        
    # Upload updated games map back to S3
    if games_map_updated:
        print(f"Uploading updated games map back to S3 bucket {bucket} at {games_key}...")
        with open(local_games_path, 'w', encoding='utf-8') as f:
            json.dump(games_map, f, indent=2, ensure_ascii=False)
        s3.upload_file(local_games_path, bucket, games_key)
        print("Games map upload completed successfully.")
    else:
        print("No changes in active games map. S3 games map file remains unchanged.")
        
    return {
        'statusCode': 200,
        'body': json.dumps("Refresh run finished successfully.")
    }
