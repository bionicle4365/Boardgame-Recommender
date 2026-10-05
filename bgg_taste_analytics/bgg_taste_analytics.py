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

# In-memory cache for catalog and feature frequencies
CATALOG_CACHE = None
FEATURE_FREQUENCIES_CACHE = None

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

def generate_catalog_feature_frequencies(catalog_df, output_path=None):
    """
    Computes catalog document frequencies and IDF factors for mechanics and categories.
    Co-located in bgg_taste_analytics for container runtime safety.
    """
    if hasattr(catalog_df, 'select') and hasattr(catalog_df, 'to_pandas'):
        cols = [c for c in ['mechanics', 'categories'] if c in catalog_df.column_names]
        df = catalog_df.select(cols).to_pandas()
        total_games = catalog_df.num_rows
    else:
        df = catalog_df
        total_games = len(df)

    mechanic_counts = {}
    category_counts = {}

    if 'mechanics' in df.columns:
        for val in df['mechanics'].dropna():
            if isinstance(val, (list, np.ndarray, tuple, set)):
                unique_mechs = set(val)
            elif isinstance(val, str):
                unique_mechs = {m.strip() for m in val.split(',') if m.strip()}
            else:
                continue
            for m in unique_mechs:
                mechanic_counts[m] = mechanic_counts.get(m, 0) + 1

    if 'categories' in df.columns:
        for val in df['categories'].dropna():
            if isinstance(val, (list, np.ndarray, tuple, set)):
                unique_cats = set(val)
            elif isinstance(val, str):
                unique_cats = {c.strip() for c in val.split(',') if c.strip()}
            else:
                continue
            for c in unique_cats:
                category_counts[c] = category_counts.get(c, 0) + 1

    mechanic_idf = {
        mech: round(math.log(1.0 + float(total_games) / max(1, count)), 4)
        for mech, count in mechanic_counts.items()
    }
    category_idf = {
        cat: round(math.log(1.0 + float(total_games) / max(1, count)), 4)
        for cat, count in category_counts.items()
    }

    result = {
        "metadata": {
            "total_games": total_games,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "unique_mechanics": len(mechanic_counts),
            "unique_categories": len(category_counts),
            "formula": "ln(1.0 + N_catalog / N_feature)"
        },
        "mechanic_frequencies": mechanic_counts,
        "category_frequencies": category_counts,
        "mechanic_idf": mechanic_idf,
        "category_idf": category_idf
    }

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2)

    return result


def get_feature_frequencies(catalog_df=None):
    """Downloads catalog_feature_frequencies.json from S3 or loads local bundle, with in-memory caching."""
    global FEATURE_FREQUENCIES_CACHE
    if FEATURE_FREQUENCIES_CACHE is not None:
        return FEATURE_FREQUENCIES_CACHE

    key = "data/catalog_feature_frequencies.json"
    local_path = "/tmp/catalog_feature_frequencies.json"

    # 1. Try S3 download
    try:
        logger.info(f"Fetching catalog feature frequencies from S3: {key}")
        s3.download_file(bucket, key, local_path)
        with open(local_path, 'r', encoding='utf-8') as f:
            FEATURE_FREQUENCIES_CACHE = json.load(f)
            logger.info(f"Loaded feature frequencies from S3 ({FEATURE_FREQUENCIES_CACHE.get('total_games', 0)} catalog games).")
            return FEATURE_FREQUENCIES_CACHE
    except Exception as e:
        logger.info(f"Could not load feature frequencies from S3: {e}")

    # 2. Try bundled/local file
    bundled_paths = [
        os.path.join(os.path.dirname(__file__), "catalog_feature_frequencies.json"),
        os.path.join(os.path.dirname(__file__), "..", "scratch", "catalog_feature_frequencies.json"),
        local_path
    ]
    for bp in bundled_paths:
        if os.path.exists(bp):
            try:
                with open(bp, 'r', encoding='utf-8') as f:
                    FEATURE_FREQUENCIES_CACHE = json.load(f)
                    logger.info(f"Loaded feature frequencies from bundled file: {bp}")
                    return FEATURE_FREQUENCIES_CACHE
            except Exception as e:
                logger.warning(f"Failed to read bundled feature frequencies at {bp}: {e}")

    # 3. Fallback: on-the-fly generation if catalog_df is available and non-empty
    if catalog_df is not None and len(catalog_df) > 0:
        try:
            FEATURE_FREQUENCIES_CACHE = generate_catalog_feature_frequencies(catalog_df)
            return FEATURE_FREQUENCIES_CACHE
        except Exception as e:
            logger.warning(f"Failed on-the-fly feature frequencies generation: {e}")

    return {}

def apply_feature_idf(damped_weights, feature_type, feature_frequencies):
    """
    Applies Inverse Document Frequency (IDF) weighting to damped affinities:
        Score = damped_score * IDF(feature)
    where IDF(feature) = ln(1.0 + N_catalog / max(1, N_feature)).
    """
    if not feature_frequencies or not damped_weights:
        return damped_weights

    if feature_type in ("categories", "category"):
        idf_key = "category_idf"
    elif feature_type in ("mechanics", "mechanic"):
        idf_key = "mechanic_idf"
    else:
        idf_key = f"{feature_type}_idf"
    precomputed_idfs = feature_frequencies.get(idf_key, {})

    total_games = feature_frequencies.get("total_games", 0)
    counts = feature_frequencies.get(feature_type, {})

    weighted = {}
    for item, w in damped_weights.items():
        if item in precomputed_idfs:
            idf = float(precomputed_idfs[item])
        elif total_games > 0:
            count = counts.get(item, 0)
            idf = math.log(1.0 + total_games / max(1, count))
        else:
            idf = 1.0
        weighted[item] = round(w * idf, 2)
    return weighted

def process_taste_profile(username):
    """
    Calculates and uploads the taste profile JSON for a single user.
    Applies logarithmic damping followed by catalog TF-IDF discounting to elevate
    distinctive mechanics and categories over ubiquitous baseline tags.
    """
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
        liked_games = user_df[user_df['own']]
    if liked_games.empty:
        liked_games = user_df.sort_values(by='rating', ascending=False).head(10)

    liked_joined = liked_games.merge(catalog_df, on='id', how='inner', suffixes=('_user', '_catalog'))

    mech_weights = {}
    cat_weights = {}
    raw_mech_weights = {}
    raw_cat_weights = {}
    designer_weights = {}
    publisher_weights = {}
    complexity_weights = {
        "Light": 0.0,
        "Medium-Light": 0.0,
        "Medium-Heavy": 0.0,
        "Heavy": 0.0
    }
    complexity_counts = {
        "Light": 0,
        "Medium-Light": 0,
        "Medium-Heavy": 0,
        "Heavy": 0
    }
    user_mean_complexity = 2.4

    if not liked_joined.empty:
        # Default complexity fallback if none of the games have complexity data
        complexity_weights["Medium-Light"] = 1.0

        mech_weights_raw = {}
        mech_counts = {}
        cat_weights_raw = {}
        cat_counts = {}
        designer_weights_raw = {}
        designer_counts = {}
        publisher_weights_raw = {}
        publisher_counts = {}

        # Derive rating-weighted affinities
        has_publishers = 'publishers' in liked_joined.columns
        has_complexity = 'complexity' in liked_joined.columns
        
        complexity_count = 0
        weighted_comp_sum = 0.0
        total_comp_weight = 0.0
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
                cat_weights_raw[c] = cat_weights_raw.get(c, 0.0) + weight
                cat_counts[c] = cat_counts.get(c, 0) + 1
            for m in set(mechs):
                mech_weights_raw[m] = mech_weights_raw.get(m, 0.0) + weight
                mech_counts[m] = mech_counts.get(m, 0) + 1

            des = row.get('designers')
            des = list(des) if isinstance(des, (list, np.ndarray)) else []
            for d in des:
                designer_weights_raw[d] = designer_weights_raw.get(d, 0.0) + weight
                designer_counts[d] = designer_counts.get(d, 0) + 1

            if has_publishers:
                pubs = row.get('publishers')
                pubs = list(pubs) if isinstance(pubs, (list, np.ndarray)) else []
                if pubs:
                    primary_pub = pubs[0]
                    publisher_weights_raw[primary_pub] = publisher_weights_raw.get(primary_pub, 0.0) + weight
                    publisher_counts[primary_pub] = publisher_counts.get(primary_pub, 0) + 1

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
                        complexity_counts = {
                            "Light": 0,
                            "Medium-Light": 0,
                            "Medium-Heavy": 0,
                            "Heavy": 0
                        }
                    complexity_count += 1
                    weighted_comp_sum += comp * weight
                    total_comp_weight += weight
                    if comp < 2.0:
                        comp_bucket = "Light"
                    elif comp <= 2.8:
                        comp_bucket = "Medium-Light"
                    elif comp <= 3.5:
                        comp_bucket = "Medium-Heavy"
                    else:
                        comp_bucket = "Heavy"
                    complexity_weights[comp_bucket] += weight
                    complexity_counts[comp_bucket] += 1

        # Apply logarithmic damping to all rating-weighted affinity vectors
        raw_mech_weights = calculate_damped_affinity(mech_weights_raw, mech_counts)
        raw_cat_weights = calculate_damped_affinity(cat_weights_raw, cat_counts)
        designer_weights = calculate_damped_affinity(designer_weights_raw, designer_counts)
        publisher_weights = calculate_damped_affinity(publisher_weights_raw, publisher_counts)

        # Apply catalog feature frequency IDF discounting
        feature_frequencies = get_feature_frequencies(catalog_df=catalog_df)
        mech_weights = apply_feature_idf(raw_mech_weights, "mechanics", feature_frequencies)
        cat_weights = apply_feature_idf(raw_cat_weights, "categories", feature_frequencies)

        # Compute averages for complexity weights if we had valid complexity data
        if complexity_count > 0:
            for b in complexity_weights:
                if complexity_counts[b] > 0:
                    complexity_weights[b] = round(complexity_weights[b] / complexity_counts[b], 2)
                else:
                    complexity_weights[b] = 0.0

        user_mean_complexity = round(weighted_comp_sum / total_comp_weight, 2) if total_comp_weight > 0 else 2.4

    # Write profile JSON
    profile = {
        "mech_weights": mech_weights,
        "cat_weights": cat_weights,
        "raw_mech_weights": raw_mech_weights,
        "raw_cat_weights": raw_cat_weights,
        "complexity_weights": complexity_weights,
        "user_mean_complexity": user_mean_complexity,
        "designer_weights": designer_weights,
        "publisher_weights": publisher_weights,
        "idf_applied": True,
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
