"""
Deterministic scoring pipeline for the BGG Recommender.

Handles candidate filtering, feature weighting, and composite scoring
to produce ranked recommendations without requiring an LLM call.
"""
import math
import os
from datetime import datetime, timezone

import pandas as pd
import numpy as np
from botocore.exceptions import ClientError

import cache_utils
from cache_utils import (
    logger, bucket,
    safe_list, get_catalog, get_active_previews, get_active_previews_games,
    get_bgg_hotness, get_user_profile_status, trigger_background_scrape,
    build_game_metadata,
)


def compute_taste_profile_inline(user_df, catalog_df, usernames, user_parquet_modified, individual_profiles=None):
    """
    Computes taste profiles for each user, loading pre-computed S3 profiles when available
    and falling back to inline computation when stale or missing.

    Returns (mech_weights, cat_weights, user_designers, user_publishers, complexity_weights).
    """
    import json

    mech_weights = {}
    cat_weights = {}
    user_designers = {}
    user_publishers = {}
    complexity_weights = {
        "Light": 0.0,
        "Medium-Light": 0.0,
        "Medium-Heavy": 0.0,
        "Heavy": 0.0
    }

    for u in usernames:
        profile_loaded = False
        profile_key = f"data/users/{u}_taste_profile.json"
        local_profile_path = f"/tmp/{u}_taste_profile.json"

        u_mech_weights = {}
        u_cat_weights = {}
        u_user_designers = {}
        u_user_publishers = {}
        u_complexity_weights = {
            "Light": 0.0,
            "Medium-Light": 0.0,
            "Medium-Heavy": 0.0,
            "Heavy": 0.0
        }

        parquet_modified = user_parquet_modified.get(u)
        try:
            cache_utils.s3.head_object(Bucket=bucket, Key=profile_key)
            cache_utils.s3.download_file(bucket, profile_key, local_profile_path)
            with open(local_profile_path, 'r', encoding='utf-8') as f:
                prof_data = json.load(f)

            generated_at_str = prof_data.get('generated_at')
            if generated_at_str and parquet_modified:
                generated_at = datetime.fromisoformat(generated_at_str)
                if generated_at.tzinfo is None:
                    generated_at = generated_at.replace(tzinfo=timezone.utc)
                if parquet_modified.tzinfo is None:
                    parquet_modified = parquet_modified.replace(tzinfo=timezone.utc)

                if generated_at >= parquet_modified:
                    logger.info(f"Loaded fresh pre-computed taste profile for {u}")
                    u_mech_weights = prof_data.get('mech_weights', {})
                    u_cat_weights = prof_data.get('cat_weights', {})
                    u_user_designers = prof_data.get('designer_weights', {})
                    u_user_publishers = prof_data.get('publisher_weights', {})
                    u_complexity_weights = prof_data.get('complexity_weights', {})
                    profile_loaded = True
                else:
                    logger.info(f"Pre-computed taste profile for {u} is stale (generated={generated_at}, parquet={parquet_modified})")
            else:
                logger.info(f"Pre-computed taste profile for {u} missing generated_at metadata or parquet modification time")
        except ClientError as ce:
            if ce.response['Error']['Code'] == '404':
                logger.info(f"Pre-computed taste profile for {u} not found in S3 (Key: {profile_key})")
            else:
                logger.error(f"S3 error loading taste profile for {u}: {ce}")
        except Exception as e:
            logger.error(f"Error loading taste profile for {u}: {e}")

        if not profile_loaded:
            logger.info(f"Computing taste profile inline for user: {u}")
            u_df = user_df[user_df['username'] == u] if 'username' in user_df.columns else user_df
            u_liked = u_df[u_df['rating'] >= 7.0]
            if u_liked.empty:
                u_liked = u_df[u_df['own']]
            if u_liked.empty:
                u_liked = u_df.sort_values(by='rating', ascending=False).head(10)

            u_joined = u_liked.merge(catalog_df, on='id', how='inner', suffixes=('_user', '_catalog'))

            u_complexity_weights = {
                "Light": 0.0,
                "Medium-Light": 0.0,
                "Medium-Heavy": 0.0,
                "Heavy": 0.0
            }
            u_complexity_counts = {
                "Light": 0,
                "Medium-Light": 0,
                "Medium-Heavy": 0,
                "Heavy": 0
            }
            u_complexity_weights["Medium-Light"] = 1.0
            complexity_count = 0

            if not u_joined.empty:
                has_publishers = 'publishers' in u_joined.columns
                has_complexity = 'complexity' in u_joined.columns
                for _, row in u_joined.iterrows():
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
                        u_cat_weights[c] = u_cat_weights.get(c, 0.0) + weight
                    for m in set(mechs):
                        u_mech_weights[m] = u_mech_weights.get(m, 0.0) + weight

                    des = row.get('designers')
                    des = list(des) if isinstance(des, (list, np.ndarray)) else []
                    for d in des:
                        u_user_designers[d] = u_user_designers.get(d, 0.0) + weight

                    if has_publishers:
                        pubs = row.get('publishers')
                        pubs = list(pubs) if isinstance(pubs, (list, np.ndarray)) else []
                        if pubs:
                            primary_pub = pubs[0]
                            u_user_publishers[primary_pub] = u_user_publishers.get(primary_pub, 0.0) + weight

                    if has_complexity:
                        comp = row.get('complexity')
                        if comp is not None and not math.isnan(float(comp)):
                            comp = float(comp)
                            if complexity_count == 0:
                                u_complexity_weights = {
                                    "Light": 0.0,
                                    "Medium-Light": 0.0,
                                    "Medium-Heavy": 0.0,
                                    "Heavy": 0.0
                                }
                                u_complexity_counts = {
                                    "Light": 0,
                                    "Medium-Light": 0,
                                    "Medium-Heavy": 0,
                                    "Heavy": 0
                                }
                            complexity_count += 1
                            if comp < 2.0:
                                comp_bucket = "Light"
                            elif comp <= 2.8:
                                comp_bucket = "Medium-Light"
                            elif comp <= 3.5:
                                comp_bucket = "Medium-Heavy"
                            else:
                                comp_bucket = "Heavy"
                            u_complexity_weights[comp_bucket] += weight
                            u_complexity_counts[comp_bucket] += 1

            if complexity_count > 0:
                for b in u_complexity_weights:
                    if u_complexity_counts[b] > 0:
                        u_complexity_weights[b] = round(u_complexity_weights[b] / u_complexity_counts[b], 2)
                    else:
                        u_complexity_weights[b] = 0.0

        # Save individual profile if requested
        if individual_profiles is not None:
            individual_profiles[u] = (
                u_mech_weights,
                u_cat_weights,
                u_user_designers,
                u_user_publishers,
                u_complexity_weights
            )

        # Merge into global blended profiles
        for m, w in u_mech_weights.items():
            mech_weights[m] = mech_weights.get(m, 0.0) + w
        for c, w in u_cat_weights.items():
            cat_weights[c] = cat_weights.get(c, 0.0) + w
        for d, w in u_user_designers.items():
            user_designers[d] = user_designers.get(d, 0.0) + w
        for p, w in u_user_publishers.items():
            user_publishers[p] = user_publishers.get(p, 0.0) + w
        for comp_bucket, w in u_complexity_weights.items():
            complexity_weights[comp_bucket] = complexity_weights.get(comp_bucket, 0.0) + w

    return mech_weights, cat_weights, user_designers, user_publishers, complexity_weights


def calculate_game_score(row, mech_weights, cat_weights, user_designers, user_publishers,
                         complexity_weights, hotness_scores, query_params, weights,
                         total_mech_weight, total_cat_weight, total_complexity_weight,
                         total_des_weight, total_pub_weight, has_complexity, has_publishers):
    """
    Computes the composite score for a single game record against a taste profile.
    """
    w_mech = weights.get('w_mech', 0.5)
    w_cat = weights.get('w_cat', 0.5)
    w_pop = weights.get('w_pop', 0.5)
    w_hot = weights.get('w_hot', 0.0)
    w_comp = weights.get('w_comp', 0.4)
    w_des = weights.get('w_des', 0.3)
    w_pub = weights.get('w_pub', 0.1)

    player_count = query_params.get('player_count')
    duration_pref = query_params.get('duration_pref', 'any').lower()
    complexity_pref = query_params.get('complexity_pref', 'any').lower()

    g_id = str(row['id'])
    cand_cats = row.get('categories')
    cand_mechs = row.get('mechanics')

    cand_cats = list(cand_cats) if cand_cats is not None else []
    cand_mechs = list(cand_mechs) if cand_mechs is not None else []

    cat_sim = sum(cat_weights.get(c, 0.0) for c in cand_cats) / total_cat_weight
    mech_sim = sum(mech_weights.get(m, 0.0) for m in cand_mechs) / total_mech_weight

    rating = row.get('rating')
    if rating is None or not isinstance(rating, (int, float)) or math.isnan(rating):
        rating = 5.5
    pop_score = max(0.0, min(1.0, (float(rating) - 5.0) / 4.0))

    hot_score = hotness_scores.get(g_id, 0.0)

    # Compute complexity similarity
    comp_sim = 0.0
    cand_complexity = row.get('complexity')
    if cand_complexity is not None and isinstance(cand_complexity, (int, float)) and not math.isnan(cand_complexity):
        cand_complexity = float(cand_complexity)
        if complexity_pref and complexity_pref != 'any':
            if complexity_pref in ('low', 'light'):
                comp_sim = 1.0 if cand_complexity <= 2.0 else max(0.0, 1.0 - ((cand_complexity - 2.0) / 2.0))
            elif complexity_pref in ('high', 'heavy'):
                comp_sim = 1.0 if cand_complexity >= 3.5 else max(0.0, 1.0 - ((3.5 - cand_complexity) / 2.5))
            elif complexity_pref == 'medium':
                if 2.0 <= cand_complexity <= 3.5:
                    comp_sim = 1.0
                elif cand_complexity < 2.0:
                    comp_sim = max(0.0, 1.0 - ((2.0 - cand_complexity) / 2.0))
                else:
                    comp_sim = max(0.0, 1.0 - ((cand_complexity - 3.5) / 1.5))
        elif has_complexity and total_complexity_weight > 0:
            if cand_complexity < 2.0:
                comp_bucket = "Light"
            elif cand_complexity <= 2.8:
                comp_bucket = "Medium-Light"
            elif cand_complexity <= 3.5:
                comp_bucket = "Medium-Heavy"
            else:
                comp_bucket = "Heavy"
            bucket_weight = complexity_weights.get(comp_bucket, 0.0)
            comp_sim = bucket_weight / total_complexity_weight

    # Compute designer/publisher similarity
    des_sim = 0.0
    cand_des = row.get('designers')
    cand_des = list(cand_des) if cand_des is not None else []
    if cand_des and user_designers and total_des_weight > 0:
        des_sim = sum(user_designers.get(d, 0.0) for d in cand_des) / total_des_weight

    pub_sim = 0.0
    if has_publishers:
        cand_pubs = row.get('publishers')
        cand_pubs = list(cand_pubs) if cand_pubs is not None else []
        if cand_pubs and user_publishers and total_pub_weight > 0:
            primary_cand_pub = cand_pubs[0]
            pub_sim = user_publishers.get(primary_cand_pub, 0.0) / total_pub_weight

    # Compute composite score
    denominator = w_mech + w_cat + w_pop + w_hot + w_comp + w_des + w_pub
    if denominator > 0:
        comp_score = (
            w_mech * mech_sim +
            w_cat * cat_sim +
            w_pop * pop_score +
            w_hot * hot_score +
            w_comp * comp_sim +
            w_des * des_sim +
            w_pub * pub_sim
        ) / denominator
    else:
        comp_score = 0.0

    # A. Apply community suggested player count penalty/booster
    if player_count:
        best_list = safe_list(row.get('suggested_players_best'))
        rec_list = safe_list(row.get('suggested_players_recommended'))
        p_str = str(player_count)

        if p_str in best_list:
            comp_score *= 1.10
        elif p_str not in rec_list:
            comp_score *= 0.75

    # B. Apply play time duration preference soft penalty
    if duration_pref and duration_pref != 'any':
        playing_time = row.get('playing_time')
        if playing_time is not None and isinstance(playing_time, (int, float)) and not math.isnan(playing_time):
            playing_time = float(playing_time)
            if duration_pref == 'short':
                dur_mult = 1.0 if playing_time <= 45 else max(0.5, 1.0 - ((playing_time - 45.0) / 90.0))
            elif duration_pref == 'long':
                dur_mult = 1.0 if playing_time >= 90 else max(0.5, 1.0 - ((90.0 - playing_time) / 90.0))
            elif duration_pref == 'medium':
                if 45 <= playing_time <= 90:
                    dur_mult = 1.0
                elif playing_time < 45:
                    dur_mult = max(0.6, 1.0 - ((45.0 - playing_time) / 45.0))
                else:
                    dur_mult = max(0.6, 1.0 - ((playing_time - 90.0) / 90.0))
            else:
                dur_mult = 1.0
            comp_score *= dur_mult

    return comp_score


def score_candidates(candidates, mech_weights, cat_weights, user_designers, user_publishers,
                     complexity_weights, hotness_scores, catalog_df, query_params, weights=None):
    """
    Scores candidate games against user taste profiles and returns top-40 ranked results.

    Returns list of dicts (each being a candidate row from the catalog).
    """
    if weights is None:
        from cache_utils import parse_weights
        weights = parse_weights(query_params)

    total_complexity_weight = sum(complexity_weights.values()) or 1.0
    total_cat_weight = sum(cat_weights.values()) or 1.0
    total_mech_weight = sum(mech_weights.values()) or 1.0
    total_des_weight = sum(user_designers.values()) or 1.0
    total_pub_weight = sum(user_publishers.values()) or 1.0
    has_complexity = 'complexity' in catalog_df.columns
    has_publishers = 'publishers' in catalog_df.columns

    # Convert candidates dataframe to a list of dicts for fast iteration
    possible_columns = [
        'id', 'name', 'categories', 'mechanics', 'rating', 'year_published',
        'min_players', 'max_players', 'playing_time', 'min_playtime', 'max_playtime',
        'complexity', 'min_age', 'thumbnail', 'image', 'designers', 'publishers',
        'suggested_players_best', 'suggested_players_recommended'
    ]
    columns_to_keep = [col for col in possible_columns if col in candidates.columns]
    candidate_records = candidates[columns_to_keep].to_dict('records')

    candidate_scores = []
    for row in candidate_records:
        comp_score = calculate_game_score(
            row, mech_weights, cat_weights, user_designers, user_publishers,
            complexity_weights, hotness_scores, query_params, weights,
            total_mech_weight, total_cat_weight, total_complexity_weight,
            total_des_weight, total_pub_weight, has_complexity, has_publishers
        )
        candidate_scores.append((comp_score, row))

    candidate_scores.sort(key=lambda x: x[0], reverse=True)
    top_candidates = [item[1] for item in candidate_scores[:40]]
    return top_candidates


def diversify_candidates(scored_candidates, max_per_mechanic=4, max_per_category=5, target_count=25):
    """
    Applies a deterministic diversification pass on scored candidates.
    Ensures that we do not cluster too many games with the same primary mechanic or category.
    The highest-scored candidate is always retained.
    
    If fewer than 25 diverse candidates can be selected, falls back to returning the original list.
    """
    from collections import defaultdict

    if not scored_candidates or len(scored_candidates) < 25:
        logger.info(
            f"Skipping diversity pass: candidate list size {len(scored_candidates) if scored_candidates else 0} "
            f"is too small (minimum 25 required)."
        )
        return scored_candidates

    selected = []
    mechanic_counts = defaultdict(int)
    category_counts = defaultdict(int)

    skipped_count = 0
    skipped_by_mechanic = 0
    skipped_by_category = 0
    skipped_by_both = 0

    caps_hit_mechanics = set()
    caps_hit_categories = set()

    for idx, row in enumerate(scored_candidates):
        if len(selected) >= target_count:
            break

        cand_mechs = row.get('mechanics')
        cand_cats = row.get('categories')

        # Convert to list if not already
        cand_mechs = list(cand_mechs) if cand_mechs is not None else []
        cand_cats = list(cand_cats) if cand_cats is not None else []

        primary_mech = cand_mechs[0] if cand_mechs else None
        primary_cat = cand_cats[0] if cand_cats else None

        # Always retain the highest-scored candidate
        if idx == 0:
            selected.append(row)
            if primary_mech:
                mechanic_counts[primary_mech] += 1
            if primary_cat:
                category_counts[primary_cat] += 1
            continue

        # Check caps
        mech_capped = False
        cat_capped = False

        if primary_mech and mechanic_counts[primary_mech] >= max_per_mechanic:
            mech_capped = True
            caps_hit_mechanics.add(primary_mech)

        if primary_cat and category_counts[primary_cat] >= max_per_category:
            cat_capped = True
            caps_hit_categories.add(primary_cat)

        if mech_capped or cat_capped:
            skipped_count += 1
            if mech_capped and cat_capped:
                skipped_by_both += 1
            elif mech_capped:
                skipped_by_mechanic += 1
            else:
                skipped_by_category += 1
            continue

        selected.append(row)
        if primary_mech:
            mechanic_counts[primary_mech] += 1
        if primary_cat:
            category_counts[primary_cat] += 1

    # Fallback check
    if len(selected) < 25:
        logger.warning(
            f"Diversity pass failed: only {len(selected)} diverse candidates could be selected "
            f"(target: {target_count}). Falling back to original unmodified candidates list."
        )
        return scored_candidates

    logger.info(
        f"Diversity pass complete. Selected {len(selected)} candidates. "
        f"Skipped {skipped_count} candidates due to caps (mechanic cap: {skipped_by_mechanic}, "
        f"category cap: {skipped_by_category}, both: {skipped_by_both}). "
        f"Mechanic caps hit: {list(caps_hit_mechanics)}. "
        f"Category caps hit: {list(caps_hit_categories)}."
    )
    return selected

