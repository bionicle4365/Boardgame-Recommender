import os
import json
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError
import pandas as pd
import numpy as np
import requests
import xml.etree.ElementTree as ET

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
            # Map extra args if present to conform to powertools Logger.info
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
s3 = boto3.client('s3')
sqs = boto3.client('sqs')
bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

# Read environment variables
bucket = os.environ.get('S3_OUTPUT_BUCKET_NAME', 'boardgame-app')
user_sqs_queue_url = os.environ.get('USER_SQS_QUEUE_URL')
bedrock_model_id = os.environ.get('BEDROCK_MODEL_ID', 'amazon.nova-micro-v1:0')

# In-memory global cache for catalog to reuse across container warm starts
CATALOG_CACHE = None

def safe_list(val):
    """Helper to safely convert array/list/nullable to a Python list without triggering array truth value errors."""
    if isinstance(val, (list, np.ndarray)):
        return list(val)
    return []

def get_catalog():
    """
    Downloads the single combined catalog parquet file from S3.
    Caches the combined catalog in memory for warm starts.
    """
    global CATALOG_CACHE
    if CATALOG_CACHE is not None:
        logger.info("Loading catalog from in-memory cache.")
        return CATALOG_CACHE

    logger.info("Fetching game catalog from S3...")
    try:
        key = "data/boardgames_combined/catalog.parquet"
        local_path = "/tmp/catalog.parquet"
        logger.info(f"Downloading catalog file: {key}")
        s3.download_file(bucket, key, local_path)
        CATALOG_CACHE = pd.read_parquet(local_path)
        logger.info(f"Successfully loaded and cached catalog with {len(CATALOG_CACHE)} games.")
        return CATALOG_CACHE
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
        response = s3.head_object(Bucket=bucket, Key=key)
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
            sqs.send_message(QueueUrl=user_sqs_queue_url, MessageBody=username)
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
        response = s3.head_object(Bucket=bucket, Key=cache_key)
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
        s3.upload_file(local_path, bucket, cache_key)
        logger.info("Successfully uploaded recommendations to S3 cache.")
    except Exception as e:
        logger.error(f"Error saving recommendations to cache: {e}")

def get_bgg_hotness(ttl_hours=2):
    """
    Retrieves the list of trending board game IDs from the BGG Hotness API.
    Uses S3 caching (data/hotness_cache.json) to limit API hits to BGG.
    """
    cache_key = "data/hotness_cache.json"
    local_path = "/tmp/hotness_cache.json"
    
    # 1. Try reading from S3 cache
    try:
        response = s3.head_object(Bucket=bucket, Key=cache_key)
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
        # 5 seconds timeout to protect Lambda execution time
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
            s3.upload_file(local_path, bucket, cache_key)
            logger.info(f"Successfully cached {len(hot_games)} hot games to S3.")
            return hot_games
        else:
            logger.error(f"Failed to fetch hotness from BGG: status code {response.status_code}")
    except Exception as e:
        logger.error(f"Error fetching hotness from BGG: {e}")

    # 3. Fallback: if BGG call failed but we have an old S3 cache, return it
    try:
        logger.info("BGG fetch failed. Attempting stale cache fallback.")
        s3.download_file(bucket, cache_key, local_path)
        with open(local_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as fallback_e:
        logger.error(f"Stale hotness cache fallback failed: {fallback_e}")
        return []

@logger.inject_lambda_context
def lambda_handler(event, context):
    logger.info("Received event", extra={"event": event})
    
    # Extract query parameters
    query_params = event.get('queryStringParameters') or {}
    username = query_params.get('username')
    
    if not username:
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'username query parameter is required'})
        }
    
    own_status = query_params.get('own_status', 'unowned').lower()
    year_start = query_params.get('year_start')
    year_end = query_params.get('year_end')
    player_count = query_params.get('player_count')

    # Extract dynamic weights
    try:
        w_mech = float(query_params.get('w_mech', '0.5'))
        w_cat = float(query_params.get('w_cat', '0.5'))
        w_pop = float(query_params.get('w_pop', '0.5'))
        w_hot = float(query_params.get('w_hot', '0.0'))
    except ValueError:
        w_mech, w_cat, w_pop, w_hot = 0.5, 0.5, 0.5, 0.0

    # Clamp weights
    w_mech = max(0.0, min(1.0, w_mech))
    w_cat = max(0.0, min(1.0, w_cat))
    w_pop = max(0.0, min(1.0, w_pop))
    w_hot = max(0.0, min(1.0, w_hot))

    # Parse list of BGG usernames (support groups)
    usernames = [u.strip() for u in username.split(',') if u.strip()]
    sorted_usernames = sorted([u.lower() for u in usernames])
    username_key = "_".join(sorted_usernames)
    
    # 1. Check if user profiles are scraped and if any are stale (stale TTL = 24 hours)
    scraping_users = []
    profile_last_modified = None
    
    for u in usernames:
        try:
            exists, is_stale, u_modified = get_user_profile_status(u, ttl_hours=24)
        except Exception as s3_check_err:
            logger.error(f"S3 checks failed for {u}: {s3_check_err}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f'Failed checking user profile status for {u}'})
            }
            
        if not exists:
            logger.info(f"User profile for '{u}' not found. Queueing scrape job.")
            trigger_background_scrape(u)
            scraping_users.append(u)
        elif is_stale:
            logger.info(f"User profile for '{u}' is stale. Queueing background update scrape job.")
            trigger_background_scrape(u)
            
        if u_modified:
            if profile_last_modified is None or u_modified > profile_last_modified:
                profile_last_modified = u_modified
                
    if scraping_users:
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'scraping',
                'scraping_users': scraping_users
            })
        }

    # 2. Check S3 recommendation cache (TTL = 7 days / 168 hours)
    cache_key = f"data/recommendation_cache/{username_key}_{own_status}_{year_start or 'any'}_{year_end or 'any'}_{player_count or 'any'}_{w_mech:.2f}_{w_cat:.2f}_{w_pop:.2f}_{w_hot:.2f}.json"
    cached_recs = get_cached_recommendations(cache_key, profile_last_modified, ttl_hours=168)
    if cached_recs is not None:
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'ready',
                'recommendations': cached_recs
            })
        }
        
    # 3. User data exists. Download and load all profiles
    user_dfs = []
    owned_ids = set()
    for u in usernames:
        user_key = f"data/users/{u}.parquet"
        local_user_path = f"/tmp/{u}.parquet"
        try:
            logger.info(f"Downloading user profile from S3: {user_key}")
            s3.download_file(bucket, user_key, local_user_path)
            u_df = pd.read_parquet(local_user_path)
            u_df['id'] = u_df['id'].astype(str)
            user_dfs.append(u_df)
            
            # Aggregate owned games
            owned_ids.update(u_df[u_df['own'] == True]['id'].tolist())
        except Exception as user_load_err:
            logger.error(f"Error loading user profile {u}: {user_load_err}")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': f'Failed reading user profile for {u}'})
            }
            
    user_df = pd.concat(user_dfs, ignore_index=True)

    # 3. Fetch catalog database
    catalog_df = get_catalog()
    if catalog_df is None or catalog_df.empty:
        logger.warning("Catalog database empty or unavailable. Returning empty recommendations.")
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'status': 'ready',
                'recommendations': [],
                'warning': 'Catalog database currently unavailable.'
            })
        }

    # Clean catalog types
    catalog_df['year_published'] = pd.to_numeric(catalog_df['year_published'], errors='coerce')
    catalog_df['rating'] = pd.to_numeric(catalog_df['rating'], errors='coerce')
    if 'complexity' in catalog_df.columns:
        catalog_df['complexity'] = pd.to_numeric(catalog_df['complexity'], errors='coerce')

    # Join user profile with catalog to map user rated game IDs to their metadata (names, features)
    # The user table ID and catalog ID should be matched as strings
    user_df['id'] = user_df['id'].astype(str)
    catalog_df['id'] = catalog_df['id'].astype(str)

    liked_games = user_df[user_df['rating'] >= 7.0]
    if liked_games.empty:
        liked_games = user_df[user_df['own'] == True]
    if liked_games.empty:
        liked_games = user_df.sort_values(by='rating', ascending=False).head(10)

    liked_joined = liked_games.merge(catalog_df, on='id', how='inner', suffixes=('_user', '_catalog'))

    # Construct list of liked games for the Bedrock prompt
    liked_games_profile = []
    for _, row in liked_joined.head(20).iterrows():
        liked_games_profile.append(f"- {row['name']} (User Rating: {row['rating_user'] if pd.notna(row['rating_user']) else 'Owned'})")
    liked_games_str = "\n".join(liked_games_profile)

    # 4. Filter Candidates based on user preferences
    candidates = catalog_df.copy()
    
    # filter out games already owned or not owned based on own_status
    if own_status == 'owned':
        candidates = candidates[candidates['id'].isin(owned_ids)]
    elif own_status == 'unowned':
        candidates = candidates[~candidates['id'].isin(owned_ids)]
        
    # filter out other games already rated to avoid repeating reviews
    if own_status != 'owned':
        rated_ids = set(user_df['id'].tolist())
        candidates = candidates[~candidates['id'].isin(rated_ids)]

    # filter by publishing year range
    if year_start:
        try:
            candidates = candidates[candidates['year_published'] >= int(year_start)]
        except ValueError:
            pass
    if year_end:
        try:
            candidates = candidates[candidates['year_published'] <= int(year_end)]
        except ValueError:
            pass

    # filter by exact player count support
    if player_count:
        try:
            p_count = int(player_count)
            if 'min_players' in candidates.columns:
                candidates = candidates[(candidates['min_players'] <= p_count) & (candidates['max_players'] >= p_count)]
            else:
                candidates = candidates[candidates['max_players'] >= p_count]
            logger.info(f"Filtered catalog by player_count {p_count}. Candidates left: {len(candidates)}")
        except ValueError:
            pass

    # 5. Feature similarity selection weighted by user rating
    # Gather user's preferred categories & mechanics, weighted by the user's rating of each game
    import math
    mech_weights = {}
    cat_weights = {}
    for _, row in liked_joined.iterrows():
        # Get user's rating. If 'N/A' or missing, treat as 7.0 (since it's a liked or owned game)
        u_rating = row.get('rating_user')
        try:
            u_rating = float(u_rating)
            if math.isnan(u_rating) or u_rating <= 0:
                u_rating = 7.0
        except (ValueError, TypeError):
            u_rating = 7.0
            
        # Give higher weight to games the user rated higher (e.g. weight = rating - 5.0, so 10/10 has weight 5.0, 7/10 has 2.0)
        # Baseline of 5.0 emphasizes differences between good and great games.
        weight = max(1.0, u_rating - 5.0)

        cats = row.get('categories')
        mechs = row.get('mechanics')
        cats = list(cats) if isinstance(cats, (list, np.ndarray)) else []
        mechs = list(mechs) if isinstance(mechs, (list, np.ndarray)) else []
        
        for c in set(cats):
            cat_weights[c] = cat_weights.get(c, 0.0) + weight
        for m in set(mechs):
            mech_weights[m] = mech_weights.get(m, 0.0) + weight

    # Total sum of feature weights in user profile
    total_cat_weight = sum(cat_weights.values()) or 1.0
    total_mech_weight = sum(mech_weights.values()) or 1.0

    # Fetch BGG Hotness list
    hot_games = get_bgg_hotness(ttl_hours=2)
    hotness_scores = {}
    for game in hot_games:
        g_id = str(game.get("id"))
        rank = game.get("rank", 50)
        # linear mapping: rank 1 -> 1.0, rank 50 -> 0.02
        score = 1.0 - ((rank - 1) / 50.0)
        hotness_scores[g_id] = max(0.0, min(1.0, score))

    # Convert candidates dataframe to a list of dictionaries to bypass slow Pandas row iteration (which takes 30+ seconds)
    possible_columns = [
        'id', 'name', 'categories', 'mechanics', 'rating', 'year_published', 
        'min_players', 'max_players', 'playing_time', 'min_playtime', 'max_playtime', 
        'complexity', 'min_age', 'thumbnail', 'image', 'designers', 'publishers',
        'suggested_players_best', 'suggested_players_recommended'
    ]
    columns_to_keep = [col for col in possible_columns if col in candidates.columns]
    candidate_records = candidates[columns_to_keep].to_dict('records')

    # Gather user's preferred designers & publishers, and average complexity
    user_designers = {}
    user_publishers = {}
    user_avg_complexity = 2.5
    has_complexity = 'complexity' in liked_joined.columns
    has_publishers = 'publishers' in liked_joined.columns
    
    if not liked_joined.empty:
        # 1. Complexity preference
        if has_complexity:
            liked_complexities = liked_joined['complexity'].dropna()
            if not liked_complexities.empty:
                user_avg_complexity = liked_complexities.mean()
        
        # 2. Designers & Publishers preference
        for _, row in liked_joined.iterrows():
            u_rating = row.get('rating_user')
            try:
                u_rating = float(u_rating)
                if math.isnan(u_rating) or u_rating <= 0:
                    u_rating = 7.0
            except (ValueError, TypeError):
                u_rating = 7.0
            weight = max(1.0, u_rating - 5.0)

            des = row.get('designers')
            des = list(des) if isinstance(des, (list, np.ndarray)) else []
            for d in des:
                user_designers[d] = user_designers.get(d, 0.0) + weight
                
            if has_publishers:
                pubs = row.get('publishers')
                pubs = list(pubs) if isinstance(pubs, (list, np.ndarray)) else []
                for p in pubs:
                    user_publishers[p] = user_publishers.get(p, 0.0) + weight

    total_des_weight = sum(user_designers.values()) or 1.0
    total_pub_weight = sum(user_publishers.values()) or 1.0

    candidate_scores = []
    for row in candidate_records:
        g_id = str(row['id'])
        # Clean candidates lists
        cand_cats = row.get('categories')
        cand_mechs = row.get('mechanics')
        
        # Parse arrays if stored as numpy arrays or list
        cand_cats = list(cand_cats) if isinstance(cand_cats, (list, np.ndarray)) else []
        cand_mechs = list(cand_mechs) if isinstance(cand_mechs, (list, np.ndarray)) else []
        
        # Calculate individual score components
        shared_cats = set(cand_cats).intersection(cat_weights.keys())
        shared_mechs = set(cand_mechs).intersection(mech_weights.keys())
        
        cat_sim = sum(cat_weights[c] for c in shared_cats) / total_cat_weight
        mech_sim = sum(mech_weights[m] for m in shared_mechs) / total_mech_weight
        
        rating = row.get('rating')
        if rating is None or not isinstance(rating, (int, float)) or math.isnan(rating):
            rating = 5.5
        pop_score = max(0.0, min(1.0, (float(rating) - 5.0) / 4.0)) # map BGG bayesaverage 5.0-9.0 to 0.0-1.0
        
        hot_score = hotness_scores.get(g_id, 0.0)
        
        # Compute composite score weighted by dynamic user choices
        denominator = w_mech + w_cat + w_pop + w_hot
        if denominator > 0:
            comp_score = (w_mech * mech_sim + w_cat * cat_sim + w_pop * pop_score + w_hot * hot_score) / denominator
        else:
            comp_score = 0.0

        # A. Apply community suggested player count soft penalty
        if player_count and 'suggested_players_recommended' in row:
            rec_list = safe_list(row.get('suggested_players_recommended'))
            if rec_list and str(player_count) not in rec_list:
                comp_score *= 0.5

        # B. Apply complexity preference soft scaling (up to 50% penalty if completely mismatched)
        if has_complexity:
            cand_complexity = row.get('complexity')
            if cand_complexity is not None and isinstance(cand_complexity, (int, float)) and not math.isnan(cand_complexity):
                complexity_delta = abs(cand_complexity - user_avg_complexity)
                complexity_sim = max(0.0, 1.0 - (complexity_delta / 2.5))
                comp_score *= (0.5 + 0.5 * complexity_sim)

        # C. Apply designer/publisher affinity booster (up to 15% bonus)
        des_sim = 0.0
        pub_sim = 0.0
        cand_des = row.get('designers')
        cand_des = list(cand_des) if isinstance(cand_des, (list, np.ndarray)) else []
        if cand_des and user_designers:
            des_sim = sum(user_designers[d] for d in set(cand_des) if d in user_designers) / total_des_weight

        if has_publishers:
            cand_pubs = row.get('publishers')
            cand_pubs = list(cand_pubs) if isinstance(cand_pubs, (list, np.ndarray)) else []
            if cand_pubs and user_publishers:
                pub_sim = sum(user_publishers[p] for p in set(cand_pubs) if p in user_publishers) / total_pub_weight

        affinity_score = 0.7 * des_sim + 0.3 * pub_sim
        comp_score *= (1.0 + 0.15 * affinity_score)
            
        candidate_scores.append((comp_score, row))

    candidate_scores.sort(key=lambda x: x[0], reverse=True)
    top_candidates = [item[1] for item in candidate_scores[:25]]

    # 6. Build Bedrock Prompt & Invoke
    candidates_str = ""
    if top_candidates:
        cand_list = []
        for row in top_candidates:
            cats = ", ".join(safe_list(row.get('categories')))
            mechs = ", ".join(safe_list(row.get('mechanics')))
            
            # Formulate additional details for prompt
            players_str = f"Players: {row['min_players']}-{row['max_players']}" if 'min_players' in row and 'max_players' in row and pd.notna(row['min_players']) else f"Max Players: {row.get('max_players', 'N/A')}"
            playtime_str = f", Playtime: {row['playing_time']}m" if 'playing_time' in row and pd.notna(row['playing_time']) else ""
            complexity_str = f", Complexity: {row['complexity']:.1f}/5" if 'complexity' in row and pd.notna(row['complexity']) else ""
            designers_list = safe_list(row.get('designers'))
            designers_str = f", Designers: {', '.join(designers_list)}" if 'designers' in row and designers_list else ""
            
            cand_list.append(
                f"- {row['name']} (Year: {row.get('year_published', 'N/A')}, Rating: {row.get('rating', 'N/A')}, "
                f"{players_str}{playtime_str}{complexity_str}{designers_str}, Categories: {cats}, Mechanics: {mechs})"
            )
        candidates_str = "\n".join(cand_list)

    # Incorporate user weights into prompt context
    weight_context = f"""
The user has tuned their preference weights for similarity scoring as follows:
- Mechanics Similarity Weight: {w_mech * 100:.0f}%
- Categories Similarity Weight: {w_cat * 100:.0f}%
- Popularity/Community Rating Weight: {w_pop * 100:.0f}%
- Hotness/Trending Weight: {w_hot * 100:.0f}%
"""
    if player_count:
        weight_context += f"- Target Session Player Count: {player_count} players (all candidate games support this player count)\n"
    if w_hot > 0.4:
        weight_context += "The user is highly interested in currently trending or hot releases.\n"
    if w_mech > 0.7:
        weight_context += "The user places strong emphasis on games sharing similar play styles and mechanics.\n"
    if w_cat > 0.7:
        weight_context += "The user places strong emphasis on games sharing similar themes and categories.\n"

    user_prompt = f"""You are a board game recommendation expert.
     
The user has the following board games in their collection with their ratings (where higher is better):
{liked_games_str if liked_games_str else "- No games rated/owned yet."}
{weight_context}
Please recommend 10 board games for the user.
"""

    if candidates_str:
        user_prompt += f"""
Here is a list of candidate board games from our catalog that match the user's preferences:
{candidates_str}

Please select the best 10 games from the candidates list above. Do NOT select games that are not in the candidates list.
"""
    else:
        user_prompt += f"""
Please recommend 10 great board games from your general knowledge.
"""

    user_prompt += """
For each recommended game:
1. Provide the exact name of the game.
2. Provide a compelling, personalized 1-sentence explanation of why they would enjoy it. This explanation must directly relate the recommended game to 1 or 2 specific board games they already like or own from their list above, referencing shared mechanics or thematic elements (for example: "If you enjoyed Gloomhaven and Mage Knight, you will love this game's use of card-driven hand management.").

Format your response as a JSON object with a single key "recommendations", which is a list of objects containing "name" and "reason".
Do not include any introductory or concluding text (e.g. do not say "Here are your recommendations:" or use markdown code blocks). Output only raw, valid JSON.
"""

    result_json = None
    try:
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "text": user_prompt
                    }
                ]
            }
        ]
        
        logger.info(f"Calling Bedrock Converse API with model {bedrock_model_id}...")
        response = bedrock.converse(
            modelId=bedrock_model_id,
            messages=messages,
            inferenceConfig={
                "maxTokens": 2048,
                "temperature": 0.3
            }
        )
        
        response_text = response['output']['message']['content'][0]['text'].strip()
        logger.info(f"Received Bedrock response: {response_text}")
        
        # Clean up response text if wrapped in markdown blocks
        if response_text.startswith("```"):
            lines = response_text.splitlines()
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                lines = lines[1:-1]
            response_text = "\n".join(lines).strip()
            
        result_json = json.loads(response_text)
        
        # Map names back to IDs from the candidates/catalog so the UI can link directly to the game page
        candidate_map = {row['name'].lower(): row for row in top_candidates}
        for rec in result_json.get('recommendations', []):
            rec_name = rec.get('name', '')
            game_meta = candidate_map.get(rec_name.lower())
            if not game_meta:
                match = catalog_df[catalog_df['name'].str.lower() == rec_name.lower()]
                if not match.empty:
                    game_meta = match.iloc[0].to_dict()
            if game_meta:
                rec['id'] = str(game_meta['id'])
                # Append rich metadata for the frontend
                rec['year_published'] = int(game_meta['year_published']) if pd.notna(game_meta.get('year_published')) else None
                rec['min_players'] = int(game_meta['min_players']) if pd.notna(game_meta.get('min_players')) else None
                rec['max_players'] = int(game_meta['max_players']) if pd.notna(game_meta.get('max_players')) else None
                rec['playing_time'] = int(game_meta['playing_time']) if pd.notna(game_meta.get('playing_time')) else None
                rec['min_playtime'] = int(game_meta['min_playtime']) if pd.notna(game_meta.get('min_playtime')) else None
                rec['max_playtime'] = int(game_meta['max_playtime']) if pd.notna(game_meta.get('max_playtime')) else None
                rec['min_age'] = int(game_meta['min_age']) if pd.notna(game_meta.get('min_age')) else None
                rec['rating'] = float(game_meta['rating']) if pd.notna(game_meta.get('rating')) else None
                rec['complexity'] = float(game_meta['complexity']) if pd.notna(game_meta.get('complexity')) else None
                rec['thumbnail'] = str(game_meta['thumbnail']) if pd.notna(game_meta.get('thumbnail')) else None
                rec['image'] = str(game_meta['image']) if pd.notna(game_meta.get('image')) else None

    except Exception as bedrock_e:
        logger.error(f"Bedrock invocation or parsing failed: {bedrock_e}")
        # Fallback to returning candidates list directly if AI call fails
        if top_candidates:
            logger.warning("Returning candidates directly as a fallback.")
            result_json = {
                "recommendations": [
                    {
                        "id": str(row['id']),
                        "name": row['name'],
                        "reason": f"Highly recommended match sharing mechanics: {', '.join(safe_list(row.get('mechanics'))[:3])}.",
                        "year_published": int(row['year_published']) if pd.notna(row.get('year_published')) else None,
                        "min_players": int(row['min_players']) if pd.notna(row.get('min_players')) else None,
                        "max_players": int(row['max_players']) if pd.notna(row.get('max_players')) else None,
                        "playing_time": int(row['playing_time']) if pd.notna(row.get('playing_time')) else None,
                        "min_playtime": int(row['min_playtime']) if pd.notna(row.get('min_playtime')) else None,
                        "max_playtime": int(row['max_playtime']) if pd.notna(row.get('max_playtime')) else None,
                        "min_age": int(row['min_age']) if pd.notna(row.get('min_age')) else None,
                        "rating": float(row['rating']) if pd.notna(row.get('rating')) else None,
                        "complexity": float(row['complexity']) if pd.notna(row.get('complexity')) else None,
                        "thumbnail": str(row['thumbnail']) if pd.notna(row.get('thumbnail')) else None,
                        "image": str(row['image']) if pd.notna(row.get('image')) else None,
                    }
                    for row in top_candidates[:10]
                ]
            }
        else:
            result_json = {"recommendations": [], "error": "AI recommendation currently unavailable"}

    # Save successfully generated recommendations to cache
    recs_list = result_json.get('recommendations', [])
    if recs_list:
        save_recommendations_to_cache(cache_key, recs_list)

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'status': 'ready',
            'recommendations': recs_list
        })
    }
