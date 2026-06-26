import os
import json
import math
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError
import pandas as pd
import numpy as np

# Initialize Structured Logging with AWS Lambda Powertools or Fallback
try:
    from aws_lambda_powertools import Logger
    logger = Logger(service="bgg-taste-analytics")
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    class FallbackLogger:
        def __init__(self):
            self.log = logging.getLogger("bgg-taste-analytics")
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

# Initialize AWS Client
s3 = boto3.client('s3')
bucket = os.environ.get('S3_OUTPUT_BUCKET_NAME', 'boardgame-app')

# In-memory cache for catalog
CATALOG_CACHE = None

def get_catalog():
    """Downloads catalog.parquet from S3 and caches it in memory."""
    global CATALOG_CACHE
    if CATALOG_CACHE is not None:
        logger.info("Loading catalog from in-memory cache.")
        return CATALOG_CACHE

    logger.info("Fetching game catalog from S3...")
    key = "data/boardgames_combined/catalog.parquet"
    local_path = "/tmp/catalog.parquet"
    logger.info(f"Downloading catalog file: {key}")
    s3.download_file(bucket, key, local_path)
    CATALOG_CACHE = pd.read_parquet(local_path)
    logger.info(f"Successfully loaded and cached catalog with {len(CATALOG_CACHE)} games.")
    return CATALOG_CACHE

def extract_usernames_from_body(body_str):
    """
    Extracts username(s) from SQS message body.
    Supports S3 Event Notification schema, JSON with username key, or raw string username.
    """
    try:
        data = json.loads(body_str)
        if isinstance(data, dict):
            # 1. S3 Event Notification format
            if "Records" in data:
                usernames = []
                for rec in data["Records"]:
                    if "s3" in rec and "object" in rec["s3"] and "key" in rec["s3"]["object"]:
                        key = rec["s3"]["object"]["key"]
                        # key format: 'data/users/{username}.parquet'
                        if key.startswith("data/users/") and key.endswith(".parquet") and not key.endswith("_taste_profile.json"):
                            filename = os.path.basename(key)
                            username = filename[:-8] # strip '.parquet'
                            usernames.append(username)
                if usernames:
                    return usernames
            # 2. JSON dict with 'username' key
            if "username" in data:
                return [str(data["username"])]
    except Exception:
        pass

    # 3. Fallback: treat raw message body string as username
    u = body_str.strip()
    if u:
        return [u]
    return []

def process_taste_profile(username):
    """Calculates and uploads the taste profile JSON for a single user."""
    logger.info(f"Generating taste profile for user: {username}")

    user_key = f"data/users/{username}.parquet"
    local_user_path = f"/tmp/{username}.parquet"
    
    logger.info(f"Downloading user collection file: {user_key}")
    s3.download_file(bucket, user_key, local_user_path)

    user_df = pd.read_parquet(local_user_path)
    user_df['id'] = user_df['id'].astype(str)

    catalog_df = get_catalog()
    catalog_df['id'] = catalog_df['id'].astype(str)

    # Replicate inline profile selection logic from bgg_recommender.py
    liked_games = user_df[user_df['rating'] >= 7.0]
    if liked_games.empty:
        liked_games = user_df[user_df['own'] == True]
    if liked_games.empty:
        liked_games = user_df.sort_values(by='rating', ascending=False).head(10)

    liked_joined = liked_games.merge(catalog_df, on='id', how='inner', suffixes=('_user', '_catalog'))

    mech_weights = {}
    cat_weights = {}
    designer_weights = {}
    publisher_weights = {}
    complexity_weights = {
        "Light": 0.0,
        "Medium-Light": 0.0,
        "Medium-Heavy": 0.0,
        "Heavy": 0.0
    }

    if not liked_joined.empty:
        # Default complexity fallback if none of the games have complexity data
        complexity_weights["Medium-Light"] = 1.0

        # Derive rating-weighted affinities
        has_publishers = 'publishers' in liked_joined.columns
        has_complexity = 'complexity' in liked_joined.columns
        
        complexity_count = 0
        for _, row in liked_joined.iterrows():
            u_rating = row.get('rating_user')
            try:
                u_rating = float(u_rating)
                if math.isnan(u_rating) or u_rating <= 0:
                    u_rating = 7.0
            except (ValueError, TypeError):
                u_rating = 7.0
            
            weight = max(1.0, u_rating - 5.0)

            cats = row.get('categories')
            mechs = row.get('mechanics')
            cats = list(cats) if isinstance(cats, (list, np.ndarray)) else []
            mechs = list(mechs) if isinstance(mechs, (list, np.ndarray)) else []
            
            for c in set(cats):
                cat_weights[c] = cat_weights.get(c, 0.0) + weight
            for m in set(mechs):
                mech_weights[m] = mech_weights.get(m, 0.0) + weight

            des = row.get('designers')
            des = list(des) if isinstance(des, (list, np.ndarray)) else []
            for d in des:
                designer_weights[d] = designer_weights.get(d, 0.0) + weight

            if has_publishers:
                pubs = row.get('publishers')
                pubs = list(pubs) if isinstance(pubs, (list, np.ndarray)) else []
                for p in pubs:
                    publisher_weights[p] = publisher_weights.get(p, 0.0) + weight

            if has_complexity:
                comp = row.get('complexity')
                if comp is not None and not math.isnan(float(comp)):
                    comp = float(comp)
                    # Reset the default fallback on first valid complexity game
                    if complexity_count == 0:
                        complexity_weights = {
                            "Light": 0.0,
                            "Medium-Light": 0.0,
                            "Medium-Heavy": 0.0,
                            "Heavy": 0.0
                        }
                    complexity_count += 1
                    if comp < 2.0:
                        complexity_weights["Light"] += weight
                    elif comp <= 2.8:
                        complexity_weights["Medium-Light"] += weight
                    elif comp <= 3.5:
                        complexity_weights["Medium-Heavy"] += weight
                    else:
                        complexity_weights["Heavy"] += weight

    # Write profile JSON
    profile = {
        "mech_weights": mech_weights,
        "cat_weights": cat_weights,
        "complexity_weights": complexity_weights,
        "designer_weights": designer_weights,
        "publisher_weights": publisher_weights,
        "generated_at": datetime.now(timezone.utc).isoformat()
    }

    local_profile_path = f"/tmp/{username}_taste_profile.json"
    with open(local_profile_path, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False)

    dest_key = f"data/users/{username}_taste_profile.json"
    logger.info(f"Uploading taste profile to S3: {dest_key}")
    s3.upload_file(local_profile_path, bucket, dest_key)
    logger.info(f"Successfully generated and uploaded taste profile for {username}")

@logger.inject_lambda_context
def lambda_handler(event, context):
    logger.info("Received event", extra={"event": event})
    
    batch_item_failures = []
    
    for record in event.get('Records', []):
        body = record.get('body', '')
        message_id = record.get('messageId')
        try:
            usernames = extract_usernames_from_body(body)
            if not usernames:
                logger.warning(f"No usernames extracted from message body: {body}")
                continue
            
            for username in usernames:
                process_taste_profile(username)
                
        except Exception as e:
            logger.error(f"Error processing record {message_id}: {e}")
            if message_id:
                batch_item_failures.append({"itemIdentifier": message_id})
                
    return {"batchItemFailures": batch_item_failures}
