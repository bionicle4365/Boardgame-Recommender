"""
S3 cache utilities, data loading helpers, and shared functions for the BGG Recommender.
"""
import os
import json
import time
import math
import re
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError
import pandas as pd
import numpy as np

# Initialize Structured Logging with AWS Lambda Powertools or Fallback
try:
    from aws_lambda_powertools import Logger
    logger = Logger(service="bgg-recommender")
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    class FallbackLogger:
        def __init__(self):
            self.log = logging.getLogger("bgg-recommender")
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

# Initialize AWS Clients
_default_s3 = boto3.client('s3')
_default_sqs = boto3.client('sqs')

def _s3():
    try:
        import bgg_recommender
        val = getattr(bgg_recommender, 's3', _default_s3)
        if isinstance(val, S3Delegate):
            return _default_s3
        return val
    except ImportError:
        return _default_s3

def _sqs():
    try:
        import bgg_recommender
        val = getattr(bgg_recommender, 'sqs', _default_sqs)
        if isinstance(val, SQSDelegate):
            return _default_sqs
        return val
    except ImportError:
        return _default_sqs

class S3Delegate:
    def __getattr__(self, name):
        return getattr(_s3(), name)

class SQSDelegate:
    def __getattr__(self, name):
        return getattr(_sqs(), name)

s3 = S3Delegate()
sqs = SQSDelegate()

# Read environment variables
bucket = os.environ.get('S3_OUTPUT_BUCKET_NAME', 'boardgame-app')
user_sqs_queue_url = os.environ.get('USER_SQS_QUEUE_URL')

# In-memory global caches for warm starts
CATALOG_CACHE = None
PREVIEWS_CACHE = None
PREVIEWS_CACHE_TIME = None
PREVIEWS_GAMES_CACHE = None
PREVIEWS_GAMES_CACHE_TIME = None


def safe_list(val):
    """Helper to safely convert array/list/nullable to a Python list without triggering array truth value errors."""
    if isinstance(val, (list, np.ndarray)):
        return list(val)
    return []


def build_game_metadata(row):
    """
    Builds the rich metadata dict for a game recommendation from a candidate row.

    Accepts both a pandas Series and a plain dict.
    """
    return {
        'id': str(row['id']),
        'name': row['name'],
        'year_published': int(row['year_published']) if pd.notna(row.get('year_published')) else None,
        'min_players': int(row['min_players']) if pd.notna(row.get('min_players')) else None,
        'max_players': int(row['max_players']) if pd.notna(row.get('max_players')) else None,
        'playing_time': int(row['playing_time']) if pd.notna(row.get('playing_time')) else None,
        'min_playtime': int(row['min_playtime']) if pd.notna(row.get('min_playtime')) else None,
        'max_playtime': int(row['max_playtime']) if pd.notna(row.get('max_playtime')) else None,
        'min_age': int(row['min_age']) if pd.notna(row.get('min_age')) else None,
        'rating': float(row['rating']) if pd.notna(row.get('rating')) else None,
        'complexity': float(row['complexity']) if pd.notna(row.get('complexity')) else None,
        'thumbnail': str(row['thumbnail']) if pd.notna(row.get('thumbnail')) else None,
        'image': str(row['image']) if pd.notna(row.get('image')) else None,
    }


def get_active_previews_games(ttl_seconds=3600):
    """Downloads active_previews_games.json from S3 and caches it in memory."""
    import bgg_recommender
    now = time.time()
    if getattr(bgg_recommender, 'PREVIEWS_GAMES_CACHE', None) is not None and getattr(bgg_recommender, 'PREVIEWS_GAMES_CACHE_TIME', None) is not None and (now - bgg_recommender.PREVIEWS_GAMES_CACHE_TIME) < ttl_seconds:
        logger.info("Loading active previews games map from in-memory cache.")
        return bgg_recommender.PREVIEWS_GAMES_CACHE

    logger.info("Fetching active previews games map from S3...")
    try:
        key = "data/active_previews_games.json"
        local_path = "/tmp/active_previews_games.json"
        _s3().download_file(bucket, key, local_path)
        with open(local_path, 'r', encoding='utf-8') as f:
            bgg_recommender.PREVIEWS_GAMES_CACHE = json.load(f)
        bgg_recommender.PREVIEWS_GAMES_CACHE_TIME = now
        logger.info(f"Successfully loaded and cached active previews games map with {len(bgg_recommender.PREVIEWS_GAMES_CACHE)} conventions.")
        return bgg_recommender.PREVIEWS_GAMES_CACHE
    except Exception as e:
        logger.error(f"Error loading active previews games map: {e}")
        return getattr(bgg_recommender, 'PREVIEWS_GAMES_CACHE', None) if getattr(bgg_recommender, 'PREVIEWS_GAMES_CACHE', None) is not None else {}


def get_active_previews(ttl_seconds=3600):
    """Downloads active_previews.json from S3 and caches it in memory."""
    import bgg_recommender
    now = time.time()
    if getattr(bgg_recommender, 'PREVIEWS_CACHE', None) is not None and getattr(bgg_recommender, 'PREVIEWS_CACHE_TIME', None) is not None and (now - bgg_recommender.PREVIEWS_CACHE_TIME) < ttl_seconds:
        logger.info("Loading active previews from in-memory cache.")
        return bgg_recommender.PREVIEWS_CACHE

    logger.info("Fetching active previews config from S3...")
    try:
        key = "data/active_previews.json"
        local_path = "/tmp/active_previews.json"
        _s3().download_file(bucket, key, local_path)
        with open(local_path, 'r', encoding='utf-8') as f:
            bgg_recommender.PREVIEWS_CACHE = json.load(f)
        bgg_recommender.PREVIEWS_CACHE_TIME = now
        logger.info(f"Successfully loaded and cached {len(bgg_recommender.PREVIEWS_CACHE)} active previews.")
        return bgg_recommender.PREVIEWS_CACHE
    except Exception as e:
        logger.error(f"Error loading active previews config: {e}")
        return getattr(bgg_recommender, 'PREVIEWS_CACHE', None) if getattr(bgg_recommender, 'PREVIEWS_CACHE', None) is not None else []


def get_catalog():
    """
    Downloads the single combined catalog parquet file from S3.
    Caches the combined catalog in memory for warm starts.
    """
    import bgg_recommender
    if getattr(bgg_recommender, 'CATALOG_CACHE', None) is not None:
        logger.info("Loading catalog from in-memory cache.")
        return bgg_recommender.CATALOG_CACHE

    logger.info("Fetching game catalog from S3...")
    try:
        key = "data/boardgames_combined/catalog.parquet"
        local_path = "/tmp/catalog.parquet"
        logger.info(f"Downloading catalog file: {key}")
        _s3().download_file(bucket, key, local_path)
        bgg_recommender.CATALOG_CACHE = pd.read_parquet(local_path)
        logger.info(f"Successfully loaded and cached catalog with {len(bgg_recommender.CATALOG_CACHE)} games.")
        return bgg_recommender.CATALOG_CACHE
    except Exception as e:
        logger.error(f"Error loading catalog database: {e}")
        return None


def get_user_profile_status(username, ttl_hours=24):
    """
    Checks if the user's parquet file exists on S3, and if it is stale.
    Returns (exists, is_stale, last_modified)
    """
    key = f"data/users/{username}.parquet"
    try:
        response = _s3().head_object(Bucket=bucket, Key=key)
        last_modified = response['LastModified']
        age_hours = (datetime.now(timezone.utc) - last_modified).total_seconds() / 3600.0
        return True, age_hours >= ttl_hours, last_modified
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False, False, None
        raise e


def trigger_background_scrape(username):
    """Sends username to SQS queue to trigger a profile scrape/update."""
    if user_sqs_queue_url:
        try:
            _sqs().send_message(QueueUrl=user_sqs_queue_url, MessageBody=username)
            logger.info(f"Successfully sent username update request to queue: {user_sqs_queue_url}")
        except Exception as sqs_err:
            logger.error(f"Error sending message to SQS: {sqs_err}")
    else:
        logger.error("Error: USER_SQS_QUEUE_URL environment variable is not defined.")


def get_cached_recommendations(cache_key, profile_last_modified, ttl_hours=168):
    """
    Checks if cached recommendations exist on S3 and are within TTL.
    Also ensures the cache file is newer than the user's profile parquet file (smart invalidation).
    Returns recommendations list if fresh, else None.
    """
    try:
        logger.info(f"Checking S3 recommendations cache: {cache_key}")
        response = _s3().head_object(Bucket=bucket, Key=cache_key)
        cache_last_modified = response['LastModified']

        # 1. Check expiration TTL
        age_hours = (datetime.now(timezone.utc) - cache_last_modified).total_seconds() / 3600.0
        if age_hours >= ttl_hours:
            logger.info(f"Cache stale: recommendations are {age_hours:.2f} hours old (TTL = {ttl_hours} hours).")
            return None

        # 2. Check smart invalidation (profile updated since recommendations were cached)
        if profile_last_modified and profile_last_modified > cache_last_modified:
            logger.info(f"Cache invalidated: user profile was updated ({profile_last_modified}) since recommendations were cached ({cache_last_modified}).")
            return None

        # 3. Cache is valid. Download and return it
        logger.info(f"Cache hit: recommendations are fresh ({age_hours:.2f} hours old). Downloading.")
        local_path = f"/tmp/{os.path.basename(cache_key)}"
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        s3.download_file(bucket, cache_key, local_path)
        with open(local_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.info("Cache miss: recommendations not found in S3.")
            return None
        raise e
    except Exception as e:
        logger.error(f"Error checking recommendations cache: {e}")
        return None


def save_recommendations_to_cache(cache_key, recommendations):
    """Saves generated recommendations as JSON file in S3 cache."""
    try:
        logger.info(f"Saving generated recommendations to S3 cache: {cache_key}")
        local_path = f"/tmp/{os.path.basename(cache_key)}"
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'w', encoding='utf-8') as f:
            json.dump(recommendations, f, ensure_ascii=False)
        _s3().upload_file(local_path, bucket, cache_key)
        logger.info("Successfully uploaded recommendations to S3 cache.")
    except Exception as e:
        logger.error(f"Error saving recommendations to cache: {e}")


def get_bgg_hotness(ttl_hours=2):
    """
    Retrieves the list of trending board game IDs from the BGG Hotness API.
    Uses S3 caching (data/hotness_cache.json) to limit API hits to BGG.
    """
    import requests
    import xml.etree.ElementTree as ET

    cache_key = "data/hotness_cache.json"
    local_path = "/tmp/hotness_cache.json"

    # 1. Try reading from S3 cache
    try:
        response = _s3().head_object(Bucket=bucket, Key=cache_key)
        last_modified = response['LastModified']
        age_hours = (datetime.now(timezone.utc) - last_modified).total_seconds() / 3600.0
        if age_hours < ttl_hours:
            logger.info(f"Hotness cache hit: file is {age_hours:.2f} hours old. Downloading from S3.")
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            s3.download_file(bucket, cache_key, local_path)
            with open(local_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except ClientError as e:
        if e.response['Error']['Code'] != '404':
            logger.error(f"S3 error checking hotness cache: {e}")
    except Exception as e:
        logger.error(f"Error loading hotness cache from S3: {e}")

    # 2. Fetch from BGG XMLAPI2
    url = "https://boardgamegeek.com/xmlapi2/hot?type=boardgame"
    bgg_api_token = os.environ.get('BGG_API_TOKEN')
    headers = {}
    if bgg_api_token:
        headers["Authorization"] = f"Bearer {bgg_api_token}"

    logger.info(f"Fetching hotness from BGG XMLAPI2: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            hot_games = []
            for item in root.findall('item'):
                game_id = item.get('id')
                rank = int(item.get('rank', '50'))
                name_val = item.find('name').get('value') if item.find('name') is not None else ""
                hot_games.append({
                    "id": str(game_id),
                    "rank": rank,
                    "name": name_val
                })
            # Save to S3 cache
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(hot_games, f, ensure_ascii=False)
            _s3().upload_file(local_path, bucket, cache_key)
            logger.info(f"Successfully cached {len(hot_games)} hot games to S3.")
            return hot_games
        else:
            logger.error(f"Failed to fetch hotness from BGG: status code {response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching hotness from BGG: {e}")

    # 3. Fallback: if BGG call failed but we have an old S3 cache, return it
    try:
        logger.info("BGG fetch failed. Attempting stale cache fallback.")
        _s3().download_file(bucket, cache_key, local_path)
        with open(local_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as fallback_e:
        logger.error(f"Stale hotness cache fallback failed: {fallback_e}")
        return []


def validate_username(username):
    """
    Validates BGG username query parameter using regular expressions.
    Ensures the username is between 1 and 25 characters and alphanumeric plus underscores only.
    """
    if not username:
        return False
    return bool(re.match(r'^[a-zA-Z0-9_]{1,25}$', username))
