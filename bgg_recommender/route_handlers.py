"""
Route handlers for subsidiary endpoints (/profile, /conventions) and HTTP response helpers.
"""
import json
import gzip
import base64
from botocore.exceptions import ClientError
from cache_utils import logger


def _get_recommender_attr(name):
    import sys
    rec = sys.modules.get('bgg_recommender')
    if rec and hasattr(rec, name):
        return getattr(rec, name)
    import cache_utils
    return getattr(cache_utils, name, None)


def _cors_headers(content_type='application/json'):
    return {
        'Content-Type': content_type
    }


def _compress_response(event, response):
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


def _handle_profile(query_params):
    """Serves pre-computed taste profiles from S3."""
    username = query_params.get('username')
    if not username:
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'username query parameter is required'})
        }

    validate_username = _get_recommender_attr('validate_username')
    if not validate_username(username):
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'Invalid username format'})
        }

    refresh = query_params.get('refresh', 'false').lower() == 'true'

    trigger_background_scrape = _get_recommender_attr('trigger_background_scrape')
    if refresh:
        logger.info(f"Forced refresh requested for user {username}. Triggering background scrape.")
        trigger_background_scrape(username)
        return {
            'statusCode': 202,
            'headers': _cors_headers(),
            'body': json.dumps({'status': 'scraping'})
        }

    # Check profile status
    get_user_profile_status = _get_recommender_attr('get_user_profile_status')
    try:
        exists, is_stale, u_modified = get_user_profile_status(username, ttl_hours=24)
        if not exists:
            logger.info(f"User profile for '{username}' not found. Queueing scrape job.")
            trigger_background_scrape(username)
            return {
                'statusCode': 202,
                'headers': _cors_headers(),
                'body': json.dumps({'status': 'scraping'})
            }
        elif is_stale:
            logger.info(f"User profile for '{username}' is stale. Queueing background update scrape job.")
            trigger_background_scrape(username)
    except Exception as s3_check_err:
        logger.error(f"S3 checks failed for {username}: {s3_check_err}")

    profile_key = f"data/users/{username}_taste_profile.json"
    local_profile_path = f"/tmp/{username}_taste_profile_api.json"
    s3_client = _get_recommender_attr('s3')
    bucket_name = _get_recommender_attr('bucket')
    try:
        logger.info(f"Downloading taste profile from S3 for endpoint: {profile_key}")
        s3_client.download_file(bucket_name, profile_key, local_profile_path)
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
            trigger_background_scrape(username)
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
    get_active_previews = _get_recommender_attr('get_active_previews')
    get_active_previews_games = _get_recommender_attr('get_active_previews_games')
    active_previews = get_active_previews()
    active_games = get_active_previews_games()
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
