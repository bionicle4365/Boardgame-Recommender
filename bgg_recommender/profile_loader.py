"""
User profile loading, cold-start checking, and liked games extraction for BGG Recommender.
"""
import os
import json
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from cache_utils import logger, safe_list


def _get_recommender_attr(name):
    import sys
    rec = sys.modules.get('bgg_recommender')
    if rec and hasattr(rec, name):
        return getattr(rec, name)
    import cache_utils
    return getattr(cache_utils, name, None)


def load_user_profiles(usernames, is_inline=False, inline_profile=None, is_cafe_patron=False):
    """
    Loads user profile DataFrames either from inline profile JSON or from S3 Parquets concurrently.

    Returns (user_df, owned_ids, has_user_profiles, error)
    """
    user_dfs = []
    owned_ids = set()

    if is_inline:
        inline_rows = []
        if inline_profile:
            username = usernames[0] if usernames else "manual_profile"
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
                s3_client = _get_recommender_attr('s3')
                bucket_name = _get_recommender_attr('bucket')
                s3_client.download_file(bucket_name, user_key, local_user_path)
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
                return None, None, False, f"Failed reading user profile for {u}"
            if u_df is not None:
                user_dfs.append(u_df)
                if not u_df.empty:
                    owned_ids.update(u_df[u_df['own']]['id'].tolist())

        user_df = pd.concat(user_dfs, ignore_index=True) if user_dfs else pd.DataFrame(columns=['id', 'username', 'rating', 'own'])

    user_df['id'] = user_df['id'].astype(str)
    has_user_profiles = bool(user_dfs)
    return user_df, owned_ids, has_user_profiles, None


def check_cold_start(user_df, cafe_id, query_params):
    """
    Checks if a user has sufficient ratings/owned games (<5 triggers wizard).
    Returns (is_cold_start, reason, total_items)
    """
    total_items = len(user_df)
    is_testing = os.environ.get('BGG_TESTING') == 'true'
    if not cafe_id and total_items < 5 and not (is_testing and query_params.get('test_cold_start') != 'true'):
        reason = "no_profile" if total_items == 0 else "insufficient_data"
        return True, reason, total_items
    return False, None, total_items


def build_liked_games_profile(user_df, catalog_df):
    """
    Extracts liked games from the user collection joined with catalog metadata,
    and returns (liked_joined, liked_games_str) for LLM prompt context.
    """
    user_df['id'] = user_df['id'].astype(str)
    if 'id' in catalog_df.columns and not pd.api.types.is_string_dtype(catalog_df['id']):
        catalog_df['id'] = catalog_df['id'].astype(str)

    liked_games = user_df[user_df['rating'] >= 7.0]
    if liked_games.empty:
        liked_games = user_df[user_df['own']]
    if liked_games.empty:
        liked_games = user_df[user_df['rating'] >= 6.5].sort_values(by='rating', ascending=False).head(10)

    liked_joined = liked_games.merge(catalog_df, on='id', how='inner', suffixes=('_user', '_catalog'))
    if 'rating_user' in liked_joined.columns:
        liked_joined = liked_joined.sort_values(by=['rating_user', 'rating_catalog'], ascending=[False, False])
    elif 'rating' in liked_joined.columns:
        liked_joined = liked_joined.sort_values(by='rating', ascending=False)

    liked_games_profile = []
    for _, row in liked_joined.head(20).iterrows():
        cats = ", ".join(safe_list(row.get('categories')))
        mechs = ", ".join(safe_list(row.get('mechanics')))
        liked_games_profile.append(
            f"- {row['name']} (User Rating: {row['rating_user'] if pd.notna(row['rating_user']) else 'Owned'}, "
            f"Categories: {cats}, Mechanics: {mechs})"
        )
    liked_games_str = "\n".join(liked_games_profile)
    return liked_joined, liked_games_str
