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
    get_feature_frequencies, apply_feature_idf,
    get_bgg_hotness, get_user_profile_status, trigger_background_scrape,
    build_game_metadata,
)


def calculate_damped_affinity(weights_sum, counts, alpha=0.3):
    """
    Applies logarithmic damping to prevent high game counts from linearly inflating affinity scores:
    Score = (sum(weight) / count) * (1.0 + alpha * ln(count))
    """
    damped = {}
    for item, tot_w in weights_sum.items():
        n = counts.get(item, 1)
        avg_w = tot_w / n
        damped[item] = round(avg_w * (1.0 + alpha * math.log(n)), 2)
    return damped


def compute_taste_profile_inline(user_df, catalog_df, usernames, user_parquet_modified, individual_profiles=None, feature_frequencies=None, apply_idf=True):
    """
    Computes taste profiles for each user, loading pre-computed S3 profiles concurrently when available
    and falling back to inline computation when stale or missing.
    Applies catalog frequency IDF discounting for offline & inline parity.

    Returns (mech_weights, cat_weights, user_designers, user_publishers, complexity_weights).
    """
    import json
    from concurrent.futures import ThreadPoolExecutor

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

    def _fetch_user_taste_profile(u):
        profile_key = f"data/users/{u}_taste_profile.json"
        local_profile_path = f"/tmp/{u}_taste_profile.json"
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
                    return (u, True, prof_data)
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
        return (u, False, None)

    fetched_profiles = {}
    if len(usernames) > 1:
        with ThreadPoolExecutor(max_workers=min(10, len(usernames))) as executor:
            results = executor.map(_fetch_user_taste_profile, usernames)
            for u, loaded, prof_data in results:
                if loaded and prof_data:
                    fetched_profiles[u] = prof_data
    elif len(usernames) == 1:
        u, loaded, prof_data = _fetch_user_taste_profile(usernames[0])
        if loaded and prof_data:
            fetched_profiles[u] = prof_data

    for u in usernames:
        profile_loaded = False
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

        if u in fetched_profiles:
            prof_data = fetched_profiles[u]
            u_mech_weights = prof_data.get('mech_weights', {})
            u_cat_weights = prof_data.get('cat_weights', {})
            u_user_designers = prof_data.get('designer_weights', {})
            u_user_publishers = prof_data.get('publisher_weights', {})
            u_complexity_weights = prof_data.get('complexity_weights', {})
            if 'user_mean_complexity' in prof_data:
                u_complexity_weights['user_mean_complexity'] = prof_data['user_mean_complexity']

            # If the precomputed profile was created before Milestone 62 and lacks idf_applied, apply IDF on the fly
            if apply_idf and not prof_data.get('idf_applied'):
                freqs = feature_frequencies if feature_frequencies is not None else get_feature_frequencies(catalog_df=catalog_df)
                u_mech_weights = apply_feature_idf(u_mech_weights, "mechanics", freqs)
                u_cat_weights = apply_feature_idf(u_cat_weights, "categories", freqs)

            profile_loaded = True

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
            has_user_complexity = False
            u_weighted_comp_sum = 0.0
            u_comp_weight_total = 0.0
            u_mech_weights_raw = {}
            u_mech_counts = {}
            u_cat_weights_raw = {}
            u_cat_counts = {}
            u_des_weights_raw = {}
            u_des_counts = {}
            u_pub_weights_raw = {}
            u_pub_counts = {}

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
                        u_cat_weights_raw[c] = u_cat_weights_raw.get(c, 0.0) + weight
                        u_cat_counts[c] = u_cat_counts.get(c, 0) + 1
                    for m in set(mechs):
                        u_mech_weights_raw[m] = u_mech_weights_raw.get(m, 0.0) + weight
                        u_mech_counts[m] = u_mech_counts.get(m, 0) + 1

                    des = row.get('designers')
                    des = list(des) if isinstance(des, (list, np.ndarray)) else []
                    for d in des:
                        u_des_weights_raw[d] = u_des_weights_raw.get(d, 0.0) + weight
                        u_des_counts[d] = u_des_counts.get(d, 0) + 1

                    if has_publishers:
                        pubs = row.get('publishers')
                        pubs = list(pubs) if isinstance(pubs, (list, np.ndarray)) else []
                        if pubs:
                            primary_pub = pubs[0]
                            u_pub_weights_raw[primary_pub] = u_pub_weights_raw.get(primary_pub, 0.0) + weight
                            u_pub_counts[primary_pub] = u_pub_counts.get(primary_pub, 0) + 1

                    if has_complexity:
                        comp = row.get('complexity')
                        if comp is not None and not math.isnan(float(comp)):
                            comp = float(comp)
                            has_user_complexity = True
                            u_weighted_comp_sum += comp * weight
                            u_comp_weight_total += weight
                            if comp < 2.0:
                                comp_bucket = "Light"
                            elif comp <= 2.8:
                                comp_bucket = "Medium-Light"
                            elif comp <= 3.5:
                                comp_bucket = "Medium-Heavy"
                            else:
                                comp_bucket = "Heavy"
                            u_complexity_weights[comp_bucket] = round(u_complexity_weights.get(comp_bucket, 0.0) + weight, 2)

                u_mech_weights = calculate_damped_affinity(u_mech_weights_raw, u_mech_counts)
                u_cat_weights = calculate_damped_affinity(u_cat_weights_raw, u_cat_counts)
                u_user_designers = calculate_damped_affinity(u_des_weights_raw, u_des_counts)
                u_user_publishers = calculate_damped_affinity(u_pub_weights_raw, u_pub_counts)

                # Apply catalog frequency IDF discounting for parity with bgg_taste_analytics.py
                if apply_idf:
                    freqs = feature_frequencies if feature_frequencies is not None else get_feature_frequencies(catalog_df=catalog_df)
                    u_mech_weights = apply_feature_idf(u_mech_weights, "mechanics", freqs)
                    u_cat_weights = apply_feature_idf(u_cat_weights, "categories", freqs)

            if has_user_complexity and u_comp_weight_total > 0:
                u_complexity_weights["user_mean_complexity"] = round(u_weighted_comp_sum / u_comp_weight_total, 2)
            else:
                u_complexity_weights["Medium-Light"] = 1.0
                u_complexity_weights["user_mean_complexity"] = 2.4

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
            if comp_bucket == 'user_mean_complexity':
                continue
            complexity_weights[comp_bucket] = complexity_weights.get(comp_bucket, 0.0) + w

    # Calculate blended user_mean_complexity
    user_means = []
    for u in usernames:
        if individual_profiles and u in individual_profiles:
            u_mean = individual_profiles[u][4].get('user_mean_complexity')
            if u_mean is not None:
                user_means.append(u_mean)
        elif u in fetched_profiles and 'user_mean_complexity' in fetched_profiles[u]:
            user_means.append(fetched_profiles[u]['user_mean_complexity'])
    if not user_means:
        bucket_centers = {"Light": 1.5, "Medium-Light": 2.4, "Medium-Heavy": 3.15, "Heavy": 4.0}
        tot_b = sum(complexity_weights.get(b, 0.0) for b in bucket_centers)
        if tot_b > 0:
            complexity_weights['user_mean_complexity'] = round(
                sum(complexity_weights.get(b, 0.0) * c for b, c in bucket_centers.items()) / tot_b, 2
            )
        else:
            complexity_weights['user_mean_complexity'] = 2.4
    else:
        complexity_weights['user_mean_complexity'] = round(sum(user_means) / len(user_means), 2)

    return mech_weights, cat_weights, user_designers, user_publishers, complexity_weights


def get_vibe_weights(vibe_key):
    """
    Returns pre-computed affinity vectors and target complexity Gaussian parameters (mu, sigma)
    for a given cafe vibe preset ('party', 'casual_strategy', 'deep_strategy', 'cooperative', 'direct_conflict').
    Maps mood vibe presets directly into normalized mechanic/category weight vectors and continuous
    complexity penalty parameters without requiring offline taste profile generation.
    """
    key = str(vibe_key or '').lower().strip().replace(' ', '_').replace('-', '_')

    # Preset configurations
    vibe_presets = {
        'party': {
            'mu': 1.4,
            'sigma': 0.55,
            'mechs': {
                'Party Game': 3.0, 'Humor': 2.5, 'Acting': 2.5, 'Singing': 2.0,
                'Storytelling': 2.0, 'Voting': 2.0, 'Trivia / Word Game': 2.0,
                'Push Your Luck': 2.2, 'Deduction': 1.8, 'Real-Time': 2.0,
                'Simultaneous Action Selection': 1.8, 'Communication Limits': 2.0
            },
            'cats': {
                'Party Game': 3.0, 'Humor': 2.5, 'Trivia': 2.2, 'Word Game': 2.2,
                'Card Game': 1.5, 'Bluffing': 2.0, 'Deduction': 1.8
            }
        },
        'casual_strategy': {
            'mu': 2.1,
            'sigma': 0.60,
            'mechs': {
                'Set Collection': 2.8, 'Drafting': 2.5, 'Open Drafting': 2.5,
                'Tile Placement': 2.8, 'Route/Network Building': 2.2,
                'Hand Management': 2.2, 'Grid Movement': 1.8, 'Contract / Goal Fulfillment': 2.0
            },
            'cats': {
                'City Building': 2.5, 'Animals': 2.2, 'Farming': 2.0, 'Trains': 2.0,
                'Economic': 1.8, 'Abstract Strategy': 2.0, 'Puzzle': 2.2, 'Card Game': 1.5
            }
        },
        'deep_strategy': {
            'mu': 3.6,
            'sigma': 0.60,
            'mechs': {
                'Worker Placement': 3.0, 'Engine Building': 2.8, 'Area Majority / Influence': 2.5,
                'Market': 2.2, 'Income': 2.2, 'Variable Player Powers': 2.0,
                'Action Retrieval': 2.0, 'Tech Trees / Tech Tracks': 2.5, 'Resource Management': 2.5
            },
            'cats': {
                'Economic': 3.0, 'Civilization': 2.8, 'Industry / Manufacturing': 2.5,
                'Sci-Fi': 2.0, 'Territory Building': 2.2, 'Renaissance': 2.0, 'Strategy': 2.5
            }
        },
        'cooperative': {
            'mu': 2.2,
            'sigma': 0.60,
            'mechs': {
                'Cooperative Game': 3.5, 'Communication Limits': 2.5,
                'Scenario / Mission / Campaign Game': 2.5, 'Solo / Solitaire Game': 1.5,
                'Role Playing': 2.0, 'Deduction': 2.0, 'Traitor Game': 2.2,
                'Variable Player Powers': 2.0
            },
            'cats': {
                'Cooperative': 3.5, 'Adventure': 2.5, 'Horror': 2.2, 'Mystery': 2.5,
                'Sci-Fi': 2.0, 'Fantasy': 2.0, 'Medical': 2.0
            }
        },
        'direct_conflict': {
            'mu': 2.7,
            'sigma': 0.65,
            'mechs': {
                'Take That': 3.0, 'Area Majority / Influence': 2.8, 'Area Movement': 2.5,
                'Dice Rolling': 2.2, 'Direct Conflict': 3.0, 'Player Elimination': 2.2,
                'Betting and Bluffing': 2.5, 'Hand Management': 1.8, 'Auction/Bidding': 2.0
            },
            'cats': {
                'Wargame': 3.0, 'Bluffing': 2.5, 'Fighting': 2.8, 'Miniatures': 2.2,
                'Territory Building': 2.5, 'Science Fiction': 2.0, 'Fantasy': 2.0, 'Pirates': 2.2
            }
        }
    }

    # Alias mapping
    alias_map = {
        'party': 'party', 'social': 'party', 'casual': 'party', 'icebreaker': 'party',
        'casual_strategy': 'casual_strategy', 'light_strategy': 'casual_strategy',
        'gateway': 'casual_strategy', 'chill': 'casual_strategy',
        'deep_strategy': 'deep_strategy', 'heavy': 'deep_strategy',
        'heavy_strategy': 'deep_strategy', 'brain_burner': 'deep_strategy',
        'cooperative': 'cooperative', 'coop': 'cooperative', 'team': 'cooperative',
        'direct_conflict': 'direct_conflict', 'conflict': 'direct_conflict',
        'pvp': 'direct_conflict', 'take_that': 'direct_conflict'
    }

    matched_vibe = alias_map.get(key, 'casual_strategy')
    preset = vibe_presets[matched_vibe]

    mu = preset['mu']
    sigma = preset['sigma']

    bucket_centers = {"Light": 1.5, "Medium-Light": 2.4, "Medium-Heavy": 3.15, "Heavy": 4.0}
    comp_buckets = {}
    for b_name, b_val in bucket_centers.items():
        dist = abs(b_val - mu)
        comp_buckets[b_name] = round(max(0.1, 1.0 - (dist / 1.5)), 2)
    comp_buckets['user_mean_complexity'] = mu
    comp_buckets['mean'] = mu
    comp_buckets['sigma'] = sigma

    return {
        'vibe': matched_vibe,
        'mech_weights': preset['mechs'],
        'cat_weights': preset['cats'],
        'user_designers': {},
        'user_publishers': {},
        'complexity_weights': comp_buckets,
        'mu': mu,
        'sigma': sigma,
        'target_complexity': mu,
        'target_sigma': sigma
    }


def calculate_bucket_complexity_affinity(cand_complexity, complexity_weights):
    """
    Computes complexity affinity using smooth piecewise linear interpolation
    across the four BGG complexity bucket centers:
    - Light: 1.5
    - Medium-Light: 2.4
    - Medium-Heavy: 3.15
    - Heavy: 4.0

    If complexity_weights is a dictionary containing any standard bucket keys,
    interpolates the user's affinity based on candidate complexity.
    Falls back gracefully to continuous Gaussian decay if only a scalar mean is provided.
    """
    if not isinstance(complexity_weights, dict):
        try:
            mu = float(complexity_weights)
            diff = (cand_complexity - mu) / 0.75
            return max(0.0, min(1.0, math.exp(-0.5 * (diff ** 2))))
        except (ValueError, TypeError):
            return 0.0

    bucket_keys = ["Light", "Medium-Light", "Medium-Heavy", "Heavy"]
    has_buckets = any(b in complexity_weights for b in bucket_keys)

    if not has_buckets:
        mu = complexity_weights.get('user_mean_complexity') or complexity_weights.get('mean')
        if mu is not None:
            try:
                mu = float(mu)
                sigma = float(complexity_weights.get('sigma', 0.75))
                diff = (cand_complexity - mu) / sigma
                return max(0.0, min(1.0, math.exp(-0.5 * (diff ** 2))))
            except (ValueError, TypeError):
                return 0.0
        return 0.0

    centers = [
        (1.5, float(complexity_weights.get("Light", 0.0))),
        (2.4, float(complexity_weights.get("Medium-Light", 0.0))),
        (3.15, float(complexity_weights.get("Medium-Heavy", 0.0))),
        (4.0, float(complexity_weights.get("Heavy", 0.0)))
    ]
    max_val = max(v for _, v in centers)
    if max_val <= 0.0:
        mu = complexity_weights.get('user_mean_complexity') or complexity_weights.get('mean')
        if mu is not None:
            try:
                mu = float(mu)
                sigma = float(complexity_weights.get('sigma', 0.75))
                diff = (cand_complexity - mu) / sigma
                return max(0.0, min(1.0, math.exp(-0.5 * (diff ** 2))))
            except (ValueError, TypeError):
                pass
        return 0.5

    if cand_complexity <= centers[0][0]:
        return max(0.0, min(1.0, centers[0][1] / max_val))
    if cand_complexity >= centers[-1][0]:
        return max(0.0, min(1.0, centers[-1][1] / max_val))

    for i in range(len(centers) - 1):
        c1, v1 = centers[i]
        c2, v2 = centers[i + 1]
        if c1 <= cand_complexity <= c2:
            t = (cand_complexity - c1) / (c2 - c1)
            interp = (1.0 - t) * v1 + t * v2
            return max(0.0, min(1.0, interp / max_val))

    return 0.0


def calculate_game_score(row, mech_weights, cat_weights, user_designers, user_publishers,
                         complexity_weights, hotness_scores, query_params, weights,
                         total_mech_weight, total_cat_weight, total_complexity_weight,
                         total_des_weight, total_pub_weight, has_complexity, has_publishers):
    """
    Computes the composite score for a single game record against a taste profile.
    """
    w_mech = weights.get('w_mech', 0.60)
    w_cat = weights.get('w_cat', 0.40)
    w_pop = weights.get('w_pop', 0.20)
    w_hot = weights.get('w_hot', 0.0)
    w_comp = weights.get('w_comp', 0.35)
    w_des = weights.get('w_des', 0.35)
    w_pub = weights.get('w_pub', 0.1)

    player_count = query_params.get('player_count')
    duration_pref = query_params.get('duration_pref', 'any').lower()
    complexity_pref = query_params.get('complexity_pref', 'any').lower()

    g_id = str(row['id'])
    cand_cats = list(dict.fromkeys(safe_list(row.get('categories'))))
    cand_mechs = list(dict.fromkeys(safe_list(row.get('mechanics'))))

    # Compute true cosine similarity for categories
    cat_sim = 0.0
    cand_cat_count = len(cand_cats)
    if cand_cat_count > 0 and cat_weights:
        cat_dot = sum(cat_weights.get(c, 0.0) for c in cand_cats)
        cat_user_norm = math.sqrt(sum(v * v for v in cat_weights.values()))
        cat_cand_norm = math.sqrt(cand_cat_count)
        if (cat_cand_norm * cat_user_norm) > 0:
            cat_sim = cat_dot / (cat_cand_norm * cat_user_norm)
            cat_sim = max(0.0, min(1.0, cat_sim))

    # Compute true cosine similarity for mechanics
    mech_sim = 0.0
    cand_mech_count = len(cand_mechs)
    if cand_mech_count > 0 and mech_weights:
        mech_dot = sum(mech_weights.get(m, 0.0) for m in cand_mechs)
        mech_user_norm = math.sqrt(sum(v * v for v in mech_weights.values()))
        mech_cand_norm = math.sqrt(cand_mech_count)
        if (mech_cand_norm * mech_user_norm) > 0:
            mech_sim = mech_dot / (mech_cand_norm * mech_user_norm)
            mech_sim = max(0.0, min(1.0, mech_sim))

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
        elif has_complexity:
            comp_sim = calculate_bucket_complexity_affinity(cand_complexity, complexity_weights)

    # Compute cosine similarity for designers (projected into same weighted space)
    des_sim = 0.0
    cand_des = safe_list(row.get('designers'))
    if cand_des and user_designers:
        des_dot_sq = sum(user_designers.get(d, 0.0)**2 for d in cand_des)
        des_user_norm_sq = sum(v * v for v in user_designers.values())
        des_sim = math.sqrt(des_dot_sq / des_user_norm_sq) if des_user_norm_sq > 0 else 0.0

    # Compute cosine similarity for publishers
    pub_sim = 0.0
    if has_publishers:
        cand_pubs = safe_list(row.get('publishers'))
        if cand_pubs and user_publishers:
            primary_cand_pub = cand_pubs[0]
            pub_dot = user_publishers.get(primary_cand_pub, 0.0)
            pub_game_norm = 1.0
            pub_user_norm = math.sqrt(sum(v * v for v in user_publishers.values()))
            pub_sim = pub_dot / (pub_user_norm * pub_game_norm) if (pub_user_norm * pub_game_norm) > 0 else 0.0

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

    total_complexity_weight = sum(v for k, v in complexity_weights.items() if k != 'user_mean_complexity') or 1.0
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
        'suggested_players_best', 'suggested_players_recommended',
        'shelf_location'
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
    Ensures that we do not cluster too many games with the same mechanics or categories.
    Accumulates fractional weights (1.0 for primary, 0.5 for secondary tags) with caps.
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
    mechanic_counts = defaultdict(float)
    category_counts = defaultdict(float)

    skipped_count = 0
    skipped_by_mechanic = 0
    skipped_by_category = 0
    skipped_by_both = 0

    caps_hit_mechanics = set()
    caps_hit_categories = set()

    for idx, row in enumerate(scored_candidates):
        if len(selected) >= target_count:
            break

        cand_mechs_raw = row.get('mechanics')
        cand_cats_raw = row.get('categories')

        # Convert to list and deduplicate preserving order
        cand_mechs = list(dict.fromkeys(list(cand_mechs_raw))) if cand_mechs_raw is not None else []
        cand_cats = list(dict.fromkeys(list(cand_cats_raw))) if cand_cats_raw is not None else []

        primary_mech = cand_mechs[0] if cand_mechs else None
        secondary_mechs = cand_mechs[1:] if len(cand_mechs) > 1 else []

        primary_cat = cand_cats[0] if cand_cats else None
        secondary_cats = cand_cats[1:] if len(cand_cats) > 1 else []

        # Always retain the highest-scored candidate
        if idx == 0:
            selected.append(row)
            if primary_mech:
                mechanic_counts[primary_mech] += 1.0
            for m in secondary_mechs:
                mechanic_counts[m] += 0.5
            if primary_cat:
                category_counts[primary_cat] += 1.0
            for c in secondary_cats:
                category_counts[c] += 0.5
            continue

        # Check caps across all mechanics and categories
        mech_capped = False
        for m in cand_mechs:
            if mechanic_counts[m] >= max_per_mechanic:
                mech_capped = True
                caps_hit_mechanics.add(m)
                break

        cat_capped = False
        for c in cand_cats:
            if category_counts[c] >= max_per_category:
                cat_capped = True
                caps_hit_categories.add(c)
                break

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
            mechanic_counts[primary_mech] += 1.0
        for m in secondary_mechs:
            mechanic_counts[m] += 0.5
        if primary_cat:
            category_counts[primary_cat] += 1.0
        for c in secondary_cats:
            category_counts[c] += 0.5

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


def filter_dislike_exclusions(candidates, user_df, catalog_df):
    """
    Filters out candidates dominated by mechanics of disliked games (rating < 6.5)
    and having no overlap with liked games' mechanics.
    """
    if user_df is None or user_df.empty:
        return candidates

    liked_df = user_df[user_df['rating'] >= 6.5]
    if liked_df.empty:
        liked_df = user_df[user_df['own']]

    disliked_df = user_df[user_df['rating'] < 6.5]
    if disliked_df.empty:
        return candidates

    # Get mechanics of liked games
    liked_joined = liked_df.merge(catalog_df, on='id', how='inner')
    like_mechs = set()
    for _, row in liked_joined.iterrows():
        mechs = safe_list(row.get('mechanics'))
        like_mechs.update(mechs)

    # Get mechanics of disliked games
    disliked_joined = disliked_df.merge(catalog_df, on='id', how='inner')
    dislike_mechs = set()
    for _, row in disliked_joined.iterrows():
        mechs = safe_list(row.get('mechanics'))
        dislike_mechs.update(mechs)

    if not dislike_mechs:
        return candidates

    filtered = []
    excluded_count = 0
    for row in candidates:
        cand_mechs = set(safe_list(row.get('mechanics')))
        if not cand_mechs:
            filtered.append(row)
            continue

        like_overlap = cand_mechs.intersection(like_mechs)
        dislike_overlap = cand_mechs.intersection(dislike_mechs)

        # Dominated check: shares no overlap with liked mechanics AND
        # has dislike mechanics representing at least 50% of the candidate's mechanics
        if len(like_overlap) == 0 and len(dislike_overlap) > 0 and len(dislike_overlap) >= len(cand_mechs) / 2.0:
            excluded_count += 1
            logger.info(f"Excluding candidate {row.get('name')} due to dislike mechanics domination (no liked mechanics, dislike overlap: {dislike_overlap})")
            continue
        filtered.append(row)

    logger.info(f"Dislike hard exclusion filtered {excluded_count} candidates. Remaining: {len(filtered)}")
    return filtered


def deduplicate_candidate_variants(candidates, target_count=12):
    """
    Deduplicates candidates that represent different editions, printings, or minor variants
    of the same game title, keeping the highest-ranked candidate for each base game.
    """
    if not candidates:
        return candidates

    seen_stems = set()
    deduped = []

    edition_markers = [
        ' (2nd edition)', ' (second edition)', ' (3rd edition)', ' (third edition)',
        ' (4th edition)', ' (fourth edition)', ' (deluxe edition)', ' (revised edition)',
        ' (special edition)', ' (collector\'s edition)', ' (anniversary edition)',
        ' (big box)', ' (big box edition)', ' 2nd edition', ' second edition',
        ' deluxe edition', ' revised edition', ' 10th anniversary edition'
    ]

    for cand in candidates:
        name = cand.get('name', '')
        stem = name.lower().strip()
        for marker in edition_markers:
            stem = stem.replace(marker, '')
        stem = stem.strip()

        if stem in seen_stems:
            logger.info(f"Deduplicating variant candidate '{name}' (matches stem '{stem}')")
            continue

        seen_stems.add(stem)
        deduped.append(cand)
        if target_count and len(deduped) >= target_count:
            break

    return deduped


def attach_candidate_linkages(candidates, liked_games_df, max_favorites=2):
    """
    Computes and attaches explicit ground-truth linkages between each candidate game
    and the user's liked games.

    For each candidate, identifies:
    - matched_favorites: List of 1-2 liked game titles with highest mechanic/category/designer overlap.
    - key_shared_mechanics: Distinctive mechanics shared between candidate and matched favorites.
    - key_shared_categories: Distinctive categories shared between candidate and matched favorites.
    - best_players: Formatted community sweet-spot player count string from suggested_players_best.

    Returns the candidates list with enriched dicts.
    """
    if not candidates:
        return candidates

    liked_items = []
    if liked_games_df is not None and not liked_games_df.empty:
        for _, l_row in liked_games_df.iterrows():
            l_name = l_row.get('name', '')
            if not l_name:
                continue
            l_mechs = set(safe_list(l_row.get('mechanics')))
            l_cats = set(safe_list(l_row.get('categories')))
            l_des = set(safe_list(l_row.get('designers')))
            raw_rating = l_row.get('rating_user', l_row.get('rating', 8.0))
            try:
                l_rating = float(raw_rating) if pd.notna(raw_rating) else 8.0
            except (ValueError, TypeError):
                l_rating = 8.0

            liked_items.append({
                'name': l_name,
                'rating': l_rating,
                'mechanics': l_mechs,
                'categories': l_cats,
                'designers': l_des
            })

    for cand in candidates:
        cand_name = cand.get('name', '')
        cand_mechs = set(safe_list(cand.get('mechanics')))
        cand_cats = set(safe_list(cand.get('categories')))
        cand_des = set(safe_list(cand.get('designers')))

        # Match against liked items
        scored_matches = []
        for l_item in liked_items:
            if l_item['name'].lower() == cand_name.lower():
                continue
            shared_m = cand_mechs.intersection(l_item['mechanics'])
            shared_c = cand_cats.intersection(l_item['categories'])
            shared_d = cand_des.intersection(l_item['designers'])

            if not shared_m and not shared_c and not shared_d:
                continue

            # Weight mechanics highest, then designers, then categories, with rating boost
            overlap_score = (len(shared_m) * 2.0) + (len(shared_c) * 1.0) + (len(shared_d) * 2.5)
            if l_item['rating'] >= 8.5:
                overlap_score += 0.5

            scored_matches.append((overlap_score, l_item['name'], shared_m, shared_c, shared_d))

        scored_matches.sort(key=lambda x: x[0], reverse=True)
        top_matches = scored_matches[:max_favorites]

        matched_favs = [m[1] for m in top_matches]
        shared_mechs = []
        shared_cats = []
        for m in top_matches:
            for mech in m[2]:
                if mech not in shared_mechs:
                    shared_mechs.append(mech)
            for cat in m[3]:
                if cat not in shared_cats:
                    shared_cats.append(cat)

        cand['matched_favorites'] = matched_favs
        cand['key_shared_mechanics'] = shared_mechs[:3]
        cand['key_shared_categories'] = shared_cats[:2]

        # Extract best player count from community poll if available
        best_p_raw = cand.get('suggested_players_best')
        if best_p_raw is not None:
            best_p_list = safe_list(best_p_raw)
            if best_p_list:
                cand['best_players'] = ", ".join(str(p) for p in best_p_list)

    return candidates


