import os
import json
import boto3
import requests
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

S3_BUCKET = os.environ.get("S3_OUTPUT_BUCKET_NAME", "boardgame-app")
S3_KEY = "data/active_previews.json"

s3 = boto3.client('s3')

def lambda_handler(event, context):
    logger.info("Starting BGG preview refresh...")
    
    # 1. Read existing active_previews.json
    try:
        response = s3.get_object(Bucket=S3_BUCKET, Key=S3_KEY)
        previews = json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Could not load {S3_KEY} from S3. Are there active previews? Error: {e}")
        return {"statusCode": 200, "body": "No active previews file found."}
    
    if not previews:
        logger.info("No active previews to refresh.")
        return {"statusCode": 200, "body": "No active previews."}
    
    # 2. For each preview, hit the API to get all objectids
    updated_previews = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    for preview in previews:
        preview_id = preview.get("preview_id")
        if not preview_id:
            updated_previews.append(preview)
            continue
            
        logger.info(f"Refreshing preview: {preview.get('name')} (ID: {preview_id})")
        url = f"https://api.geekdo.com/api/geekpreviewitems?previewid={preview_id}&showcount=5000"
        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            
            game_ids = []
            for item in data:
                try:
                    obj_type = item.get('objecttype')
                    obj_id = item.get('objectid')
                    if obj_type == 'thing' and obj_id:
                        game_ids.append(int(obj_id))
                except Exception as ex:
                    continue
            
            logger.info(f"Found {len(game_ids)} games for preview {preview_id}")
            
            # Update the preview object
            preview['game_ids'] = list(set(game_ids))
            updated_previews.append(preview)
            
        except Exception as e:
            logger.error(f"Failed to refresh preview {preview_id}: {e}")
            updated_previews.append(preview)
            
    # 3. Save back to S3
    try:
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=S3_KEY,
            Body=json.dumps(updated_previews),
            ContentType='application/json'
        )
        logger.info("Successfully updated active_previews.json")
    except Exception as e:
        logger.error(f"Failed to write to S3: {e}")
        return {"statusCode": 500, "body": "Failed to write to S3."}
        
    return {"statusCode": 200, "body": json.dumps({"status": "success", "previews_refreshed": len(updated_previews)})}
