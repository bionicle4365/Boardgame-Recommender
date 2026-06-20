import os
import json
from datetime import datetime, timezone
import boto3
from botocore.exceptions import ClientError
import pandas as pd
import numpy as np

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
        print("Loading catalog from in-memory cache.")
        return CATALOG_CACHE

    print("Fetching game catalog from S3...")
    try:
        key = "data/boardgames_combined/catalog.parquet"
        local_path = "/tmp/catalog.parquet"
        print(f"Downloading catalog file: {key}")
        s3.download_file(bucket, key, local_path)
        CATALOG_CACHE = pd.read_parquet(local_path)
        print(f"Successfully loaded and cached catalog with {len(CATALOG_CACHE)} games.")
        return CATALOG_CACHE
    except Exception as e:
        print(f"Error loading catalog database: {e}")
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
            print(f"Successfully sent username update request to queue: {user_sqs_queue_url}")
        except Exception as sqs_err:
            print(f"Error sending message to SQS: {sqs_err}")
    else:
        print("Error: USER_SQS_QUEUE_URL environment variable is not defined.")

def get_cached_recommendations(cache_key, profile_last_modified, ttl_hours=24):
    """
    Checks if cached recommendations exist on S3 and are within TTL.
    Also ensures the cache file is newer than the user's profile parquet file (smart invalidation).
    Returns recommendations list if fresh, else None.
    """
    try:
        print(f"Checking S3 recommendations cache: {cache_key}")
        response = s3.head_object(Bucket=bucket, Key=cache_key)
        cache_last_modified = response['LastModified']
        
        # 1. Check expiration TTL
        age_hours = (datetime.now(timezone.utc) - cache_last_modified).total_seconds() / 3600.0
        if age_hours >= ttl_hours:
            print(f"Cache stale: recommendations are {age_hours:.2f} hours old (TTL = {ttl_hours} hours).")
            return None
            
        # 2. Check smart invalidation (profile updated since recommendations were cached)
        if profile_last_modified and profile_last_modified > cache_last_modified:
            print(f"Cache invalidated: user profile was updated ({profile_last_modified}) since recommendations were cached ({cache_last_modified}).")
            return None
            
        # 3. Cache is valid. Download and return it
        print(f"Cache hit: recommendations are fresh ({age_hours:.2f} hours old). Downloading.")
        local_path = f"/tmp/{os.path.basename(cache_key)}"
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        s3.download_file(bucket, cache_key, local_path)
        with open(local_path, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            print("Cache miss: recommendations not found in S3.")
            return None
        raise e
    except Exception as e:
        print(f"Error checking recommendations cache: {e}")
        return None

def save_recommendations_to_cache(cache_key, recommendations):
    """Saves generated recommendations as JSON file in S3 cache."""
    try:
        print(f"Saving generated recommendations to S3 cache: {cache_key}")
        local_path = f"/tmp/{os.path.basename(cache_key)}"
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'w', encoding='utf-8') as f:
            json.dump(recommendations, f, ensure_ascii=False)
        s3.upload_file(local_path, bucket, cache_key)
        print("Successfully uploaded recommendations to S3 cache.")
    except Exception as e:
        print(f"Error saving recommendations to cache: {e}")

def lambda_handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    
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
    
    # 1. Check if user's profile is scraped and if it is stale (stale TTL = 24 hours)
    try:
        exists, is_stale, profile_last_modified = get_user_profile_status(username, ttl_hours=24)
    except Exception as s3_check_err:
        print(f"S3 checks failed: {s3_check_err}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Failed checking user profile status'})
        }
        
    if not exists:
        print(f"User profile for '{username}' not found. Queueing scrape job.")
        trigger_background_scrape(username)
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'status': 'scraping'})
        }

    if is_stale:
        print(f"User profile for '{username}' is stale. Queueing background update scrape job.")
        trigger_background_scrape(username)

    # 2. Check S3 recommendation cache (TTL = 24 hours)
    cache_key = f"data/recommendation_cache/{username}_{own_status}_{year_start or 'any'}_{year_end or 'any'}.json"
    cached_recs = get_cached_recommendations(cache_key, profile_last_modified, ttl_hours=24)
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
        
    # 3. User data exists. Download and load it
    user_key = f"data/users/{username}.parquet"
    local_user_path = f"/tmp/{username}.parquet"
    try:
        print(f"Downloading user profile from S3: {user_key}")
        s3.download_file(bucket, user_key, local_user_path)
        user_df = pd.read_parquet(local_user_path)
    except Exception as user_load_err:
        print(f"Error loading user profile: {user_load_err}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'Failed reading user profile'})
        }

    # 3. Fetch catalog database
    catalog_df = get_catalog()
    if catalog_df is None or catalog_df.empty:
        print("Catalog database empty or unavailable. Returning empty recommendations.")
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
    owned_ids = set(user_df[user_df['own'] == True]['id'].tolist())
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

    # 5. Feature similarity selection weighted by user rating
    # Gather user's preferred categories & mechanics, weighted by the user's rating of each game
    import math
    feature_weights = {}
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
        
        for f in set(cats + mechs):
            feature_weights[f] = feature_weights.get(f, 0.0) + weight

    # Total sum of feature weights in user profile
    total_user_weight = sum(feature_weights.values()) or 1.0

    # Convert candidates dataframe to a list of dictionaries to bypass slow Pandas row iteration (which takes 30+ seconds)
    columns_to_keep = ['id', 'name', 'categories', 'mechanics', 'rating', 'year_published']
    candidate_records = candidates[columns_to_keep].to_dict('records')

    candidate_scores = []
    for row in candidate_records:
        # Clean candidates lists
        cand_cats = row.get('categories')
        cand_mechs = row.get('mechanics')
        
        # Parse arrays if stored as numpy arrays or list
        cand_cats = list(cand_cats) if isinstance(cand_cats, (list, np.ndarray)) else []
        cand_mechs = list(cand_mechs) if isinstance(cand_mechs, (list, np.ndarray)) else []
        
        cand_features = set(cand_cats + cand_mechs)
        
        # Calculate similarity score: sum of shared feature weights / total user weight
        shared_features = cand_features.intersection(feature_weights.keys())
        sim_score = sum(feature_weights[f] for f in shared_features) / total_user_weight
            
        candidate_scores.append((sim_score, row))

    # Sort candidates by composite score (similarity_score * rating), safely defaulting NaN ratings to 5.5
    def composite_score(sim, row_dict):
        r_val = row_dict.get('rating')
        if r_val is None or not isinstance(r_val, (int, float)) or math.isnan(r_val):
            r_val = 5.5  # Neutral default prior for unrated/new games
        return sim * float(r_val)

    candidate_scores.sort(key=lambda x: composite_score(x[0], x[1]), reverse=True)
    top_candidates = [item[1] for item in candidate_scores[:25]]

    # 6. Build Bedrock Prompt & Invoke
    candidates_str = ""
    if top_candidates:
        cand_list = []
        for row in top_candidates:
            cats = ", ".join(safe_list(row.get('categories')))
            mechs = ", ".join(safe_list(row.get('mechanics')))
            cand_list.append(f"- {row['name']} (Year: {row.get('year_published', 'N/A')}, Rating: {row.get('rating', 'N/A')}, Categories: {cats}, Mechanics: {mechs})")
        candidates_str = "\n".join(cand_list)

    user_prompt = f"""You are a board game recommendation expert.
     
The user has the following board games in their collection with their ratings (where higher is better):
{liked_games_str if liked_games_str else "- No games rated/owned yet."}

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
        
        print(f"Calling Bedrock Converse API with model {bedrock_model_id}...")
        response = bedrock.converse(
            modelId=bedrock_model_id,
            messages=messages,
            inferenceConfig={
                "maxTokens": 2048,
                "temperature": 0.3
            }
        )
        
        response_text = response['output']['message']['content'][0]['text'].strip()
        print(f"Received Bedrock response: {response_text}")
        
        # Clean up response text if wrapped in markdown blocks
        if response_text.startswith("```"):
            lines = response_text.splitlines()
            if lines[0].startswith("```json") or lines[0].startswith("```"):
                lines = lines[1:-1]
            response_text = "\n".join(lines).strip()
            
        result_json = json.loads(response_text)
        
        # Map names back to IDs from the candidates/catalog so the UI can link directly to the game page
        candidate_id_map = {row['name'].lower(): row['id'] for row in top_candidates}
        for rec in result_json.get('recommendations', []):
            rec_name = rec.get('name', '')
            game_id = candidate_id_map.get(rec_name.lower())
            if not game_id:
                match = catalog_df[catalog_df['name'].str.lower() == rec_name.lower()]
                if not match.empty:
                    game_id = match.iloc[0]['id']
            if game_id:
                rec['id'] = str(game_id)

    except Exception as bedrock_e:
        print(f"Bedrock invocation or parsing failed: {bedrock_e}")
        # Fallback to returning candidates list directly if AI call fails
        if top_candidates:
            print("Returning candidates directly as a fallback.")
            result_json = {
                "recommendations": [
                    {
                        "id": str(row['id']),
                        "name": row['name'],
                        "reason": f"Highly recommended match sharing mechanics: {', '.join(safe_list(row.get('mechanics'))[:3])}."
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
