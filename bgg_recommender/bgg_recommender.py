"""
BGG Recommender Lambda Handler — Thin Router.

Routes incoming API Gateway requests to the appropriate module:
- /profile      → serves pre-computed taste profiles from S3
- /conventions  → serves active convention metadata
- /recommendations → two-phase scoring + optional narration pipeline
"""
import os
import json
import math

import pandas as pd
import numpy as np

# Define global caches at module level for backwards compatibility with tests
CATALOG_CACHE = None
PREVIEWS_CACHE = None
PREVIEWS_CACHE_TIME = None
PREVIEWS_GAMES_CACHE = None
PREVIEWS_GAMES_CACHE_TIME = None

from cache_utils import (
    logger, bucket,
    safe_list, get_catalog, get_active_previews, get_active_previews_games,
    get_bgg_hotness, get_user_profile_status, trigger_background_scrape,
    get_cached_recommendations, save_recommendations_to_cache,
    build_game_metadata, validate_username, parse_weights,
)
from scoring import compute_taste_profile_inline, score_candidates, diversify_candidates
from narration import narrate_recommendations, build_fallback_recommendations, build_weight_context

from botocore.exceptions import ClientError



import sys
bgg_rec = sys.modules[__name__]


def _cors_headers(content_type='application/json'):
    return {
        'Content-Type': content_type
    }


def _handle_profile(query_params):
    """Serves pre-computed taste profiles from S3."""
    username = query_params.get('username')
    if not username:
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'username query parameter is required'})
        }

    if not validate_username(username):
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'Invalid username format'})
        }

    refresh = query_params.get('refresh', 'false').lower() == 'true'

    if refresh:
        logger.info(f"Forced refresh requested for user {username}. Triggering background scrape.")
        bgg_rec.trigger_background_scrape(username)
        return {
            'statusCode': 202,
            'headers': _cors_headers(),
            'body': json.dumps({'status': 'scraping'})
        }

    # Check profile status
    try:
        exists, is_stale, u_modified = bgg_rec.get_user_profile_status(username, ttl_hours=24)
        if not exists:
            logger.info(f"User profile for '{username}' not found. Queueing scrape job.")
            bgg_rec.trigger_background_scrape(username)
            return {
                'statusCode': 202,
                'headers': _cors_headers(),
                'body': json.dumps({'status': 'scraping'})
            }
        elif is_stale:
            logger.info(f"User profile for '{username}' is stale. Queueing background update scrape job.")
            bgg_rec.trigger_background_scrape(username)
    except Exception as s3_check_err:
        logger.error(f"S3 checks failed for {username}: {s3_check_err}")

    profile_key = f"data/users/{username}_taste_profile.json"
    local_profile_path = f"/tmp/{username}_taste_profile_api.json"
    try:
        logger.info(f"Downloading taste profile from S3 for endpoint: {profile_key}")
        bgg_rec.s3.download_file(bgg_rec.bucket, profile_key, local_profile_path)
        with open(local_profile_path, 'r', encoding='utf-8') as f:
            profile_data = json.load(f)
        return {
            'statusCode': 200,
            'headers': _cors_headers(),
            'body': json.dumps(profile_data)
        }
    except ClientError as ce:
        if ce.response['Error']['Code'] == '404':
            logger.info(f"Taste profile not found for user {username}. Triggering background scrape.")
            bgg_rec.trigger_background_scrape(username)
            return {
                'statusCode': 202,
                'headers': _cors_headers(),
                'body': json.dumps({'status': 'scraping'})
            }
        else:
            logger.error(f"S3 error loading taste profile for endpoint: {ce}")
            return {
                'statusCode': 500,
                'headers': _cors_headers(),
                'body': json.dumps({'error': f'S3 error loading taste profile for {username}'})
            }
    except Exception as e:
        logger.error(f"Error loading taste profile for endpoint: {e}")
        return {
            'statusCode': 500,
            'headers': _cors_headers(),
            'body': json.dumps({'error': str(e)})
        }


def _handle_conventions():
    """Serves active convention metadata."""
    active_previews = bgg_rec.get_active_previews()
    active_games = bgg_rec.get_active_previews_games()
    conventions_meta = []
    for conv in active_previews:
        conv_id = conv.get("convention_id")
        games_list = active_games.get(conv_id, [])
        conventions_meta.append({
            "convention_id": conv_id,
            "name": conv.get("name"),
            "date": conv.get("date"),
            "game_count": len(games_list)
        })
    return {
        'statusCode': 200,
        'headers': _cors_headers(),
        'body': json.dumps(conventions_meta)
    }


def _handle_recommendations(query_params):
    """
    Two-phase recommendation pipeline.

    Phase 1 (default): Returns scored candidates immediately with generic reasons.
    Phase 2 (narrate=true): Calls Bedrock to generate personalized AI reasons.
    """
    username = query_params.get('username')
    if not username:
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'username query parameter is required'})
        }

    # Split and validate usernames
    usernames = [u.strip() for u in username.split(',') if u.strip()]
    if not usernames:
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'username query parameter is required'})
        }

    for u in usernames:
        if not validate_username(u):
            return {
                'statusCode': 400,
                'headers': _cors_headers(),
                'body': json.dumps({'error': f'Invalid username format: {u}'})
            }

    own_status = query_params.get('own_status', 'unowned').lower()
    year_start = query_params.get('year_start')
    year_end = query_params.get('year_end')
    player_count = query_params.get('player_count')
    refresh = query_params.get('refresh', 'false').lower() == 'true'
    narrate = query_params.get('narrate', 'true').lower() == 'true'

    # Parse list of BGG usernames (support groups)
    sorted_usernames = sorted([u.lower() for u in usernames])
    username_key = "_".join(sorted_usernames)

    # Extract and clamp dynamic weights
    weights = parse_weights(query_params)
    w_mech = weights['w_mech']
    w_cat = weights['w_cat']
    w_pop = weights['w_pop']
    w_hot = weights['w_hot']
    w_comp = weights['w_comp']
    w_des = weights['w_des']
    w_pub = weights['w_pub']

    duration_pref = query_params.get('duration_pref', 'any').lower()
    complexity_pref = query_params.get('complexity_pref', 'any').lower()
    convention_id_cache = query_params.get('convention_id', 'any')

    # 1. Check if user profiles are scraped and if any are stale
    scraping_users = []
    profile_last_modified = None
    user_parquet_modified = {}

    for u in usernames:
        try:
            exists, is_stale, u_modified = bgg_rec.get_user_profile_status(u, ttl_hours=0 if refresh else 24)
            if u_modified:
                user_parquet_modified[u] = u_modified
        except Exception as s3_check_err:
            logger.error(f"S3 checks failed for {u}: {s3_check_err}")
            return {
                'statusCode': 500,
                'headers': _cors_headers(),
                'body': json.dumps({'error': f'Failed checking user profile status for {u}'})
            }

        if not exists:
            logger.info(f"User profile for '{u}' not found. Queueing scrape job.")
            bgg_rec.trigger_background_scrape(u)
            scraping_users.append(u)
        elif is_stale:
            logger.info(f"User profile for '{u}' is stale. Queueing background update scrape job.")
            bgg_rec.trigger_background_scrape(u)

        if u_modified:
            if profile_last_modified is None or u_modified > profile_last_modified:
                profile_last_modified = u_modified

    if scraping_users:
        return {
            'statusCode': 200,
            'headers': _cors_headers(),
            'body': json.dumps({
                'status': 'scraping',
                'scraping_users': scraping_users
            })
        }

    # 2. Check S3 recommendation cache (TTL = 7 days / 168 hours)
    cache_key = f"data/recommendation_cache/{username_key}_{own_status}_{year_start or 'any'}_{year_end or 'any'}_{player_count or 'any'}_{duration_pref}_{complexity_pref}_{convention_id_cache}_{w_mech:.2f}_{w_cat:.2f}_{w_pop:.2f}_{w_hot:.2f}_{w_comp:.2f}_{w_des:.2f}_{w_pub:.2f}.json"

    if not refresh:
        cached_recs = bgg_rec.get_cached_recommendations(cache_key, profile_last_modified, ttl_hours=168)
        if cached_recs is not None:
            return {
                'statusCode': 200,
                'headers': _cors_headers(),
                'body': json.dumps({
                    'status': 'ready',
                    'narration_status': 'complete',
                    'recommendations': cached_recs
                })
            }

    # 3. Download and load all user profiles
    user_dfs = []
    owned_ids = set()
    for u in usernames:
        user_key = f"data/users/{u}.parquet"
        local_user_path = f"/tmp/{u}.parquet"
        try:
            logger.info(f"Downloading user profile from S3: {user_key}")
            bgg_rec.s3.download_file(bgg_rec.bucket, user_key, local_user_path)
            u_df = pd.read_parquet(local_user_path)
            u_df['id'] = u_df['id'].astype(str)
            u_df['username'] = u
            user_dfs.append(u_df)
            owned_ids.update(u_df[u_df['own']]['id'].tolist())
        except Exception as user_load_err:
            logger.error(f"Error loading user profile {u}: {user_load_err}")
            return {
                'statusCode': 500,
                'headers': _cors_headers(),
                'body': json.dumps({'error': f'Failed reading user profile for {u}'})
            }

    user_df = pd.concat(user_dfs, ignore_index=True)

    # 4. Fetch catalog database
    catalog_df = bgg_rec.get_catalog()
    if catalog_df is None or catalog_df.empty:
        logger.warning("Catalog database empty or unavailable. Returning empty recommendations.")
        return {
            'statusCode': 200,
            'headers': _cors_headers(),
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

    user_df['id'] = user_df['id'].astype(str)
    catalog_df['id'] = catalog_df['id'].astype(str)

    liked_games = user_df[user_df['rating'] >= 7.0]
    if liked_games.empty:
        liked_games = user_df[user_df['own']]
    if liked_games.empty:
        liked_games = user_df.sort_values(by='rating', ascending=False).head(10)

    liked_joined = liked_games.merge(catalog_df, on='id', how='inner', suffixes=('_user', '_catalog'))

    # Build liked games string for potential Bedrock prompt
    liked_games_profile = []
    for _, row in liked_joined.head(20).iterrows():
        cats = ", ".join(bgg_rec.safe_list(row.get('categories')))
        mechs = ", ".join(bgg_rec.safe_list(row.get('mechanics')))
        liked_games_profile.append(f"- {row['name']} (User Rating: {row['rating_user'] if pd.notna(row['rating_user']) else 'Owned'}, Categories: {cats}, Mechanics: {mechs})")
    liked_games_str = "\n".join(liked_games_profile)

    # 5. Filter candidates
    candidates = catalog_df.copy()

    # Convention filter
    convention_id = query_params.get('convention_id')
    if convention_id:
        active_previews = bgg_rec.get_active_previews()
        matched_conv = next((c for c in active_previews if c.get('convention_id') == convention_id), None)
        if matched_conv:
            active_games = bgg_rec.get_active_previews_games()
            conv_game_ids = {str(g_id) for g_id in active_games.get(convention_id, []) if g_id}
            logger.info(f"Filtering candidates by convention '{convention_id}' ({len(conv_game_ids)} games)")
            candidates = candidates[candidates['id'].isin(conv_game_ids)]
        else:
            logger.warning(f"Convention '{convention_id}' not found in active previews config. Fetching full catalog instead.")

    # Ownership filter
    if own_status == 'owned':
        candidates = candidates[candidates['id'].isin(owned_ids)]
    elif own_status == 'unowned':
        candidates = candidates[~candidates['id'].isin(owned_ids)]

    # Filter out already rated games
    if own_status != 'owned':
        rated_ids = set(user_df['id'].tolist())
        candidates = candidates[~candidates['id'].isin(rated_ids)]

    # Year range filter
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

    # Player count filter
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

    # Pre-filter by rating for unowned recommendations
    if own_status != 'owned' and len(candidates) > 100:
        candidates = candidates[candidates['rating'] >= 5.0]
        logger.info(f"Pre-filtered candidates by rating >= 5.0. Candidates left: {len(candidates)}")

    # 6. Compute taste profiles and score candidates
    mech_weights, cat_weights, user_designers, user_publishers, complexity_weights = compute_taste_profile_inline(
        user_df, catalog_df, usernames, user_parquet_modified
    )

    hot_games = bgg_rec.get_bgg_hotness(ttl_hours=2)
    hotness_scores = {}
    for game in hot_games:
        g_id = str(game.get("id"))
        rank = game.get("rank", 50)
        score = 1.0 - ((rank - 1) / 50.0)
        hotness_scores[g_id] = max(0.0, min(1.0, score))

    top_candidates = score_candidates(
        candidates, mech_weights, cat_weights, user_designers, user_publishers,
        complexity_weights, hotness_scores, catalog_df, query_params, weights
    )

    # 7. Apply diversity guard to candidates
    top_candidates = diversify_candidates(top_candidates)

    # 8. Call Bedrock for personalized narration
    weight_context = build_weight_context(query_params, weights)
    narrated_recs = narrate_recommendations(top_candidates[:25], liked_games_str, weight_context, query_params)

    if narrated_recs is not None:
        recs_list = narrated_recs
    else:
        # Bedrock failed, return fallback
        recs_list = build_fallback_recommendations(top_candidates)

    # Save narrated recommendations to cache
    if recs_list:
        bgg_rec.save_recommendations_to_cache(cache_key, recs_list)

    return {
        'statusCode': 200,
        'headers': _cors_headers(),
        'body': json.dumps({
            'status': 'ready',
            'narration_status': 'complete',
            'recommendations': recs_list
        })
    }


def _compress_response(event, response):
    import gzip
    import base64

    if not isinstance(response, dict):
        return response
    headers = event.get('headers') or {}
    accept_encoding = ""
    for k, v in headers.items():
        if k.lower() == 'accept-encoding':
            accept_encoding = v
            break
    if 'gzip' not in accept_encoding.lower():
        return response
    body = response.get('body')
    if body is None or response.get('isBase64Encoded', False):
        return response
    if isinstance(body, str):
        body_bytes = body.encode('utf-8')
    elif isinstance(body, (bytes, bytearray)):
        body_bytes = body
    else:
        return response
    compressed = gzip.compress(body_bytes)
    encoded = base64.b64encode(compressed).decode('utf-8')
    resp_headers = response.get('headers') or {}
    content_encoding_key = 'Content-Encoding'
    for k in list(resp_headers.keys()):
        if k.lower() == 'content-encoding':
            content_encoding_key = k
            break
    resp_headers[content_encoding_key] = 'gzip'
    response['body'] = encoded
    response['isBase64Encoded'] = True
    response['headers'] = resp_headers
    return response


@logger.inject_lambda_context
def lambda_handler(event, context):
    logger.info("Received event", extra={"event": event})

    query_params = event.get('queryStringParameters') or {}
    path = event.get('rawPath', '') or event.get('requestContext', {}).get('http', {}).get('path', '')

    if '/profile' in path:
        response = _handle_profile(query_params)
    elif '/conventions' in path:
        response = _handle_conventions()
    else:
        response = _handle_recommendations(query_params)

    return _compress_response(event, response)


def __getattr__(name):
    """
    Dynamic attribute loader for S3, SQS, and Bedrock.
    Provides backwards compatibility with test mock patching.
    """
    if name == 's3':
        import cache_utils
        return cache_utils.s3
    if name == 'sqs':
        import cache_utils
        return cache_utils.sqs
    if name == 'bedrock':
        import narration
        return narration.bedrock
    raise AttributeError(f"module {__name__} has no attribute {name}")
