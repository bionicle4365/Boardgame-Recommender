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
from concurrent.futures import ThreadPoolExecutor

# Define global caches at module level for backwards compatibility with tests
CATALOG_CACHE = None
PREVIEWS_CACHE = None
PREVIEWS_CACHE_TIME = None
PREVIEWS_GAMES_CACHE = None
PREVIEWS_GAMES_CACHE_TIME = None
FEATURE_FREQUENCIES_CACHE = None
FEATURE_FREQUENCIES_CACHE_TIME = None
CAFE_INVENTORY_CACHE = {}

from cache_utils import (
    logger, bucket,
    safe_list, get_catalog, get_active_previews, get_active_previews_games,
    get_feature_frequencies,
    get_bgg_hotness, get_user_profile_status, trigger_background_scrape,
    get_cached_recommendations, save_recommendations_to_cache,
    build_game_metadata, validate_username, parse_weights,
    get_cafe_inventory, get_cafe_status, trigger_background_cafe_scrape,
)
from scoring import (
    compute_taste_profile_inline, score_candidates, diversify_candidates,
    calculate_game_score, filter_dislike_exclusions,
    deduplicate_candidate_variants, attach_candidate_linkages,
    get_vibe_weights,
)
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
        if not games_list:
            continue
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


from session_handlers import (
    _handle_create_session,
    _handle_cafe_vote_start,
    _handle_get_session,
    _handle_vote_session,
    _handle_close_session,
    _handle_delete_session,
    _handle_list_sessions,
)



def _handle_recommendations(query_params):
    """
    Two-phase recommendation pipeline.

    Phase 1 (default): Returns scored candidates immediately with generic reasons.
    Phase 2 (narrate=true): Calls Bedrock to generate personalized AI reasons.
    """
    username = query_params.get('username')
    inline_profile = query_params.get('inline_profile')
    inline_weights = query_params.get('inline_weights')

    if isinstance(inline_profile, str):
        try:
            inline_profile = json.loads(inline_profile)
        except Exception:
            pass
    if isinstance(inline_weights, str):
        try:
            inline_weights = json.loads(inline_weights)
        except Exception:
            pass

    cafe_id_raw = query_params.get('cafe_id') or query_params.get('cafe_username')
    cafe_id = str(cafe_id_raw).strip() if cafe_id_raw else None
    vibe = query_params.get('vibe')
    table = query_params.get('table')

    is_inline = (inline_profile is not None) or (inline_weights is not None)
    is_cafe_patron = False

    if not username:
        if is_inline:
            username = "manual_profile"
        elif cafe_id:
            username = "cafe_guest"
            is_cafe_patron = True
        else:
            return {
                'statusCode': 400,
                'headers': _cors_headers(),
                'body': json.dumps({'error': 'username query parameter is required'})
            }

    # Split and validate usernames
    usernames = [u.strip() for u in username.split(',') if u.strip()]
    if not usernames:
        if cafe_id:
            usernames = ["cafe_guest"]
            is_cafe_patron = True
        else:
            return {
                'statusCode': 400,
                'headers': _cors_headers(),
                'body': json.dumps({'error': 'username query parameter is required'})
            }

    for u in usernames:
        if not is_cafe_patron and not validate_username(u):
            return {
                'statusCode': 400,
                'headers': _cors_headers(),
                'body': json.dumps({'error': f'Invalid username format: {u}'})
            }

    own_status_val = query_params.get('own_status', 'unowned')
    own_status = own_status_val.lower() if isinstance(own_status_val, str) else 'unowned'
    
    year_start = query_params.get('year_start')
    year_end = query_params.get('year_end')
    player_count = query_params.get('player_count')
    
    refresh_val = query_params.get('refresh', 'false')
    refresh = refresh_val if isinstance(refresh_val, bool) else str(refresh_val).lower() == 'true'
    
    narrate_val = query_params.get('narrate', 'true')
    narrate = narrate_val if isinstance(narrate_val, bool) else str(narrate_val).lower() == 'true'

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

    # 1. Check if user or cafe profiles are scraped and if any are stale
    scraping_users = []
    profile_last_modified = None
    user_parquet_modified = {}

    if cafe_id and not is_inline:
        exists, is_stale, c_modified = bgg_rec.get_cafe_status(cafe_id, ttl_hours=0 if refresh else 24)
        if not exists:
            logger.info(f"Cafe collection for '{cafe_id}' not found. Queueing scrape job.")
            bgg_rec.trigger_background_cafe_scrape(cafe_id)
            return {
                'statusCode': 200,
                'headers': _cors_headers(),
                'body': json.dumps({
                    'status': 'scraping',
                    'scraping_cafes': [cafe_id],
                    'message': f"Retrieving library collection for cafe '{cafe_id}'."
                })
            }
        elif is_stale:
            logger.info(f"Cafe collection for '{cafe_id}' is stale. Queueing background update scrape job.")
            bgg_rec.trigger_background_cafe_scrape(cafe_id)
        if c_modified:
            profile_last_modified = c_modified

    if not is_inline and not is_cafe_patron:
        def _check_user_status(u):
            try:
                exists, is_stale, u_modified = bgg_rec.get_user_profile_status(u, ttl_hours=0 if refresh else 24)
                return (u, exists, is_stale, u_modified, None)
            except Exception as s3_check_err:
                return (u, False, False, None, s3_check_err)

        if len(usernames) > 1:
            with ThreadPoolExecutor(max_workers=min(10, len(usernames))) as executor:
                status_results = list(executor.map(_check_user_status, usernames))
        else:
            status_results = [_check_user_status(usernames[0])]

        for u, exists, is_stale, u_modified, err in status_results:
            if err:
                logger.error(f"S3 checks failed for {u}: {err}")
                return {
                    'statusCode': 500,
                    'headers': _cors_headers(),
                    'body': json.dumps({'error': f'Failed checking user profile status for {u}'})
                }

            if u_modified:
                user_parquet_modified[u] = u_modified
                if profile_last_modified is None or u_modified > profile_last_modified:
                    profile_last_modified = u_modified

            if not exists:
                logger.info(f"User profile for '{u}' not found. Queueing scrape job.")
                bgg_rec.trigger_background_scrape(u)
                scraping_users.append(u)
            elif is_stale:
                logger.info(f"User profile for '{u}' is stale. Queueing background update scrape job.")
                bgg_rec.trigger_background_scrape(u)

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
    if cafe_id:
        cache_key = f"data/recommendation_cache/cafe_{cafe_id}_{vibe or 'any'}_{player_count or 'any'}_{duration_pref}.json"
    else:
        cache_key = f"data/recommendation_cache/{username_key}_{own_status}_{year_start or 'any'}_{year_end or 'any'}_{player_count or 'any'}_{duration_pref}_{complexity_pref}_{convention_id_cache}_{w_mech:.2f}_{w_cat:.2f}_{w_pop:.2f}_{w_hot:.2f}_{w_comp:.2f}_{w_des:.2f}_{w_pub:.2f}.json"

    if not refresh and not is_inline:
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
    
    if is_inline:
        inline_rows = []
        if inline_profile:
            for item in inline_profile:
                g_id = str(item.get('id'))
                rating = item.get('rating')
                try:
                    rating = float(rating)
                except (ValueError, TypeError):
                    rating = None
                
                own = (rating is not None and rating >= 7.0)
                inline_rows.append({
                    'id': g_id,
                    'username': username,
                    'rating': rating,
                    'own': own
                })
        user_df = pd.DataFrame(inline_rows, columns=['id', 'username', 'rating', 'own'])
        if not user_df.empty:
            owned_ids = set(user_df[user_df['own']]['id'].tolist())
        else:
            owned_ids = set()
    elif is_cafe_patron:
        user_df = pd.DataFrame(columns=['id', 'username', 'rating', 'own'])
    else:
        def _fetch_user_parquet(u):
            user_key = f"data/users/{u}.parquet"
            local_user_path = f"/tmp/{u}.parquet"
            try:
                logger.info(f"Downloading user profile from S3: {user_key}")
                bgg_rec.s3.download_file(bgg_rec.bucket, user_key, local_user_path)
                u_df = pd.read_parquet(local_user_path)
                u_df['id'] = u_df['id'].astype(str)
                u_df['username'] = u
                return (u, u_df, None)
            except Exception as user_load_err:
                return (u, None, user_load_err)

        if len(usernames) > 1:
            with ThreadPoolExecutor(max_workers=min(10, len(usernames))) as executor:
                parquet_results = list(executor.map(_fetch_user_parquet, usernames))
        else:
            parquet_results = [_fetch_user_parquet(usernames[0])]

        for u, u_df, err in parquet_results:
            if err:
                logger.error(f"Error loading user profile {u}: {err}")
                return {
                    'statusCode': 500,
                    'headers': _cors_headers(),
                    'body': json.dumps({'error': f'Failed reading user profile for {u}'})
                }
            if u_df is not None:
                user_dfs.append(u_df)
                if not u_df.empty:
                    owned_ids.update(u_df[u_df['own']]['id'].tolist())

        user_df = pd.concat(user_dfs, ignore_index=True) if user_dfs else pd.DataFrame(columns=['id', 'username', 'rating', 'own'])
        
        # Check for empty or sparse BGG user profile (under 5 ratings/owned games triggers wizard)
        total_items = len(user_df)
        is_testing = os.environ.get('BGG_TESTING') == 'true'
        if not cafe_id and total_items < 5 and not (is_testing and query_params.get('test_cold_start') != 'true'):
            reason = "no_profile" if total_items == 0 else "insufficient_data"
            return {
                'statusCode': 200,
                'headers': _cors_headers(),
                'body': json.dumps({
                    'status': 'cold_start_required',
                    'reason': reason,
                    'ratings_count': total_items
                })
            }

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

    # Clean catalog types if needed
    if 'year_published' in catalog_df.columns and not pd.api.types.is_numeric_dtype(catalog_df['year_published']):
        catalog_df['year_published'] = pd.to_numeric(catalog_df['year_published'], errors='coerce')
    if 'rating' in catalog_df.columns and not pd.api.types.is_numeric_dtype(catalog_df['rating']):
        catalog_df['rating'] = pd.to_numeric(catalog_df['rating'], errors='coerce')
    if 'complexity' in catalog_df.columns and not pd.api.types.is_numeric_dtype(catalog_df['complexity']):
        catalog_df['complexity'] = pd.to_numeric(catalog_df['complexity'], errors='coerce')

    user_df['id'] = user_df['id'].astype(str)
    if 'id' in catalog_df.columns and not pd.api.types.is_string_dtype(catalog_df['id']):
        catalog_df['id'] = catalog_df['id'].astype(str)

    liked_games = user_df[user_df['rating'] >= 7.0]
    if liked_games.empty:
        liked_games = user_df[user_df['own']]
    if liked_games.empty:
        liked_games = user_df.sort_values(by='rating', ascending=False).head(10)

    liked_joined = liked_games.merge(catalog_df, on='id', how='inner', suffixes=('_user', '_catalog'))
    if 'rating_user' in liked_joined.columns:
        liked_joined = liked_joined.sort_values(by=['rating_user', 'rating_catalog'], ascending=[False, False])
    elif 'rating' in liked_joined.columns:
        liked_joined = liked_joined.sort_values(by='rating', ascending=False)

    # Build liked games string for potential Bedrock prompt
    liked_games_profile = []
    for _, row in liked_joined.head(20).iterrows():
        cats = ", ".join(bgg_rec.safe_list(row.get('categories')))
        mechs = ", ".join(bgg_rec.safe_list(row.get('mechanics')))
        liked_games_profile.append(f"- {row['name']} (User Rating: {row['rating_user'] if pd.notna(row['rating_user']) else 'Owned'}, Categories: {cats}, Mechanics: {mechs})")
    liked_games_str = "\n".join(liked_games_profile)

    # 5. Filter candidates
    candidates = catalog_df

    # Cafe inventory filter (Hard Candidate Boundary)
    if cafe_id:
        cafe_df = bgg_rec.get_cafe_inventory(cafe_id)
        if cafe_df is None or cafe_df.empty:
            logger.warning(f"Cafe inventory for '{cafe_id}' is empty or unavailable.")
            return {
                'statusCode': 200,
                'headers': _cors_headers(),
                'body': json.dumps({
                    'status': 'ready',
                    'recommendations': [],
                    'warning': f"No games found in {cafe_id}'s library."
                })
            }
        cafe_owned_ids = set(cafe_df['id'].astype(str).tolist())
        candidates = candidates[candidates['id'].isin(cafe_owned_ids)].copy()
        logger.info(f"Restricted candidate pool to {len(candidates)} games from cafe '{cafe_id}'.")
        for shelf_col in ['shelf_location', 'shelf']:
            if shelf_col in cafe_df.columns:
                shelf_map = dict(zip(cafe_df['id'].astype(str), cafe_df[shelf_col]))
                candidates['shelf_location'] = candidates['id'].map(shelf_map)
                break
        if 'shelf_location' not in candidates.columns:
            candidates['shelf_location'] = None

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

    # Ownership filter (inverted in cafe mode: patrons play from cafe shelves)
    if not cafe_id:
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

    # Complexity level filter
    if complexity_pref and complexity_pref != 'any' and 'complexity' in candidates.columns:
        filtered_candidates = candidates
        if complexity_pref in ('low', 'light'):
            filtered_candidates = candidates[candidates['complexity'].notna() & (candidates['complexity'] <= 2.0)]
        elif complexity_pref in ('high', 'heavy'):
            filtered_candidates = candidates[candidates['complexity'].notna() & (candidates['complexity'] >= 3.5)]
        elif complexity_pref == 'medium':
            filtered_candidates = candidates[candidates['complexity'].notna() & (candidates['complexity'] >= 2.0) & (candidates['complexity'] <= 3.5)]

        if not filtered_candidates.empty:
            candidates = filtered_candidates
            logger.info(f"Filtered catalog by complexity_pref '{complexity_pref}'. Candidates left: {len(candidates)}")
        else:
            logger.warning(
                f"Complexity filter '{complexity_pref}' matched 0 games in candidate pool; "
                f"falling back to full candidate pool ({len(candidates)} games) so scoring can rank nearest matches."
            )

    # Pre-filter by rating for unowned recommendations
    if not cafe_id and own_status != 'owned' and len(candidates) > 100:
        candidates = candidates[candidates['rating'] >= 5.0]
        logger.info(f"Pre-filtered candidates by rating >= 5.0. Candidates left: {len(candidates)}")

    # 6. Compute taste profiles and score candidates
    individual_profiles = {}
    if inline_weights:
        # Bypassing taste profile computation, use direct weights
        mech_weights = inline_weights.get('mech_weights', {})
        cat_weights = inline_weights.get('cat_weights', {})
        complexity_weights = inline_weights.get('complexity_weights', {
            "Light": 0.0, "Medium-Light": 0.0, "Medium-Heavy": 0.0, "Heavy": 0.0
        })
        user_designers = inline_weights.get('designer_weights', {})
        user_publishers = inline_weights.get('publisher_weights', {})
    elif vibe and (is_cafe_patron or not user_dfs):
        vibe_profile = get_vibe_weights(vibe)
        mech_weights = vibe_profile['mech_weights']
        cat_weights = vibe_profile['cat_weights']
        complexity_weights = vibe_profile['complexity_weights']
        user_designers = vibe_profile['user_designers']
        user_publishers = vibe_profile['user_publishers']
    elif vibe and user_dfs:
        u_mech, u_cat, user_designers, user_publishers, u_comp = compute_taste_profile_inline(
            user_df, catalog_df, usernames, user_parquet_modified, individual_profiles=individual_profiles
        )
        vibe_profile = get_vibe_weights(vibe)
        v_mech = vibe_profile['mech_weights']
        v_cat = vibe_profile['cat_weights']
        mech_weights = {m: u_mech.get(m, 0.0) * 0.5 + v_mech.get(m, 0.0) * 0.5 for m in set(u_mech) | set(v_mech)}
        cat_weights = {c: u_cat.get(c, 0.0) * 0.5 + v_cat.get(c, 0.0) * 0.5 for c in set(u_cat) | set(v_cat)}
        complexity_weights = vibe_profile['complexity_weights']
    else:
        mech_weights, cat_weights, user_designers, user_publishers, complexity_weights = compute_taste_profile_inline(
            user_df, catalog_df, usernames, user_parquet_modified, individual_profiles=individual_profiles
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

    # 7. Apply dislike hard exclusions
    top_candidates = filter_dislike_exclusions(top_candidates, user_df, catalog_df)

    # 8. Apply diversity guard to candidates
    top_candidates = diversify_candidates(top_candidates)

    # 9. Deduplicate candidate variants (bypassed if convention filter is active) and attach linkages
    if not convention_id:
        top_candidates = deduplicate_candidate_variants(top_candidates, target_count=12)
    else:
        top_candidates = top_candidates[:12]
    top_candidates = attach_candidate_linkages(top_candidates, liked_joined)

    # 10. Call Bedrock for personalized narration
    weight_context = build_weight_context(query_params, weights)
    narrated_recs = narrate_recommendations(
        top_candidates, liked_games_str, weight_context, query_params,
        is_inline=is_inline, inline_weights=inline_weights, inline_profile=inline_profile,
        cafe_id=cafe_id, vibe=vibe, table=table
    )

    if narrated_recs is not None:
        recs_list = narrated_recs
    else:
        # Bedrock failed, return fallback
        recs_list = build_fallback_recommendations(top_candidates, is_cafe=bool(cafe_id))

    # 10. Compute individual playgroup member affinities if a group request
    if len(usernames) > 1 and recs_list and not inline_weights and not is_cafe_patron:
        logger.info(f"Computing individual playgroup member affinities for {len(usernames)} attendees.")
        has_complexity = 'complexity' in catalog_df.columns
        has_publishers = 'publishers' in catalog_df.columns
        
        # Member taste alignment should evaluate pure, intrinsic taste against the game,
        # invariant to session/situational query filters (complexity, duration, player count).
        member_query_params = {
            'complexity_pref': 'any',
            'duration_pref': 'any',
            'player_count': None
        }
        
        for rec in recs_list:
            game_id = str(rec['id'])
            matching_rows = catalog_df[catalog_df['id'] == game_id]
            if matching_rows.empty:
                continue
            game_row = matching_rows.iloc[0].to_dict()
            
            affinities = {}
            for u in usernames:
                u_prof = individual_profiles.get(u)
                if u_prof:
                    u_mech, u_cat, u_des, u_pub, u_comp = u_prof
                    
                    # Pre-calculate totals for u
                    u_total_mech = sum(u_mech.values()) or 1.0
                    u_total_cat = sum(u_cat.values()) or 1.0
                    u_total_comp = sum(v for k, v in u_comp.items() if k != 'user_mean_complexity') or 1.0
                    u_total_des = sum(u_des.values()) or 1.0
                    u_total_pub = sum(u_pub.values()) or 1.0
                    
                    u_score = calculate_game_score(
                        game_row, u_mech, u_cat, u_des, u_pub, u_comp,
                        hotness_scores, member_query_params, weights,
                        u_total_mech, u_total_cat, u_total_comp, u_total_des, u_total_pub,
                        has_complexity, has_publishers
                    )
                    affinities[u] = round(u_score, 3)
            rec['member_affinities'] = affinities

    # Save narrated recommendations to cache
    if recs_list and not is_inline:
        bgg_rec.save_recommendations_to_cache(cache_key, recs_list)

    return {
        'statusCode': 200,
        'headers': _cors_headers(),
        'body': json.dumps({
            'status': 'ready',
            'narration_status': 'complete',
            'recommendations': recs_list,
            'ratings_count': len(user_df)
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
    try:
        logger.info("Received event", extra={"event": event})

        query_params = event.get('queryStringParameters') or {}
        
        # Handle POST JSON body
        body_params = {}
        body = event.get('body')
        if body:
            try:
                if event.get('isBase64Encoded', False):
                    import base64
                    body = base64.b64decode(body).decode('utf-8')
                body_params = json.loads(body)
            except Exception as e:
                logger.error(f"Error parsing event body: {e}")
                
        # Combine query params and body params, prioritizing body params
        combined_params = {**query_params, **body_params}

        path = event.get('rawPath', '') or event.get('requestContext', {}).get('http', {}).get('path', '')
        http_method = event.get('requestContext', {}).get('http', {}).get('method', '').upper() or event.get('httpMethod', '').upper()

        if '/profile' in path:
            response = _handle_profile(query_params)
        elif '/conventions' in path:
            response = _handle_conventions()
        elif path.rstrip('/') == '/sessions':
            response = _handle_list_sessions(query_params, event)
        elif '/session/close' in path or (path.startswith('/session') and http_method == 'PUT'):
            response = _handle_close_session(combined_params)
        elif '/session/cancel' in path or '/session/delete' in path or (path.startswith('/session') and http_method == 'DELETE'):
            stripped = path.strip('/')
            parts = stripped.split('/')
            if len(parts) > 1 and parts[0] == 'session' and parts[1] not in ('cancel', 'close', 'vote', 'delete'):
                combined_params['session_id'] = parts[1]
            response = _handle_delete_session(combined_params)
        elif '/session/vote' in path or (path.startswith('/session') and http_method == 'POST' and ('vote' in path or 'participant_name' in body_params)):
            response = _handle_vote_session(combined_params)
        elif '/cafe/vote/start' in path or (path.startswith('/cafe/vote') and http_method == 'POST'):
            response = _handle_cafe_vote_start(body_params, event)
        elif path.startswith('/session') and http_method == 'POST':
            response = _handle_create_session(body_params, event)
        elif path.startswith('/session') and (http_method == 'GET' or not http_method):
            # Extract session_id if in path: /session/{session_id}
            stripped = path.strip('/')
            parts = stripped.split('/')
            if len(parts) > 1 and parts[0] == 'session' and parts[1] not in ('cancel', 'close', 'vote', 'delete'):
                combined_params['session_id'] = parts[1]
            response = _handle_get_session(combined_params)
        else:
            response = _handle_recommendations(combined_params)

        return _compress_response(event, response)
    except Exception as e:
        logger.error(f"Unhandled exception in lambda_handler: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': _cors_headers(),
            'body': json.dumps({
                'error': 'Internal Server Error',
                'details': str(e)
            })
        }


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
    if name == 'sessions':
        import sessions
        return sessions
    raise AttributeError(f"module {__name__} has no attribute {name}")
