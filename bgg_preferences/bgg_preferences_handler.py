import gzip
import io
import os
import json
import base64
import re
import time
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal

# Helper to handle Decimal types in DynamoDB JSON serialization
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

def floats_to_decimals(obj):
    """
    Recursively converts float types to Decimals for DynamoDB serialization.
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [floats_to_decimals(x) for x in obj]
    return obj

def _extract_collection_field_value(cat_row, row, key, default=None):
    """
    Extracts a game attribute, prioritizing the master catalog row over the
    scraped collection row, ignoring NaN or None values.
    """
    import pandas as pd
    v = cat_row.get(key)
    if v is not None and pd.notna(v):
        return v
    v = row.get(key)
    if v is not None and pd.notna(v):
        return v
    return default

# Initialize DynamoDB Resource
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'bgg-user-preferences')
table = dynamodb.Table(table_name)

cafes_table_name = os.environ.get('DYNAMODB_CAFES_TABLE_NAME', 'bgg-cafes')
cafes_table = dynamodb.Table(cafes_table_name)

s3 = boto3.client('s3', region_name='us-east-1')
s3_bucket = os.environ.get('S3_OUTPUT_BUCKET_NAME', 'boardgame-app')

_CATALOG_CACHE = None

def _get_catalog_df():
    """
    Loads and caches the master game catalog (catalog.parquet) from S3.
    Caches in Lambda /tmp and memory for fast ID-linking queries.
    """
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE

    local_path = "/tmp/catalog.parquet"
    if not os.path.exists(local_path):
        key = "data/boardgames_combined/catalog.parquet"
        try:
            s3.download_file(s3_bucket, key, local_path)
        except Exception as e:
            print(f"Error downloading {key} from S3: {e}")
            return None

    import pandas as pd
    try:
        df = pd.read_parquet(local_path)
        if 'id' in df.columns:
            df['id'] = df['id'].astype(str)
        _CATALOG_CACHE = df
        return _CATALOG_CACHE
    except Exception as e:
        print(f"Error reading {local_path}: {e}")
        return None


def _handle_validate_bgg(query_params):
    """
    Validates a BGG username, fetches owned games, and tests shelf location
    regex extraction against game comments.
    """
    username = (query_params.get('username') or '').strip()
    if not username:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'username query parameter is required'})
        }

    if not re.match(r'^[a-zA-Z0-9_]{1,25}$', username):
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Invalid username format'})
        }

    raw_regex = query_params.get('shelf_regex', '').strip() or r'(?:Shelf|Location|Bin):?\s*([A-Za-z0-9\-]+)'
    try:
        shelf_pattern = re.compile(raw_regex, re.IGNORECASE)
    except re.error as re_err:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Invalid shelf_regex: {str(re_err)}'})
        }

    bgg_token = os.environ.get('BGG_API_TOKEN')
    headers = {
        'User-Agent': 'Boardgame-Recommender-Cafe-Validator/1.0'
    }
    if bgg_token:
        headers['Authorization'] = f'Bearer {bgg_token}'

    api_url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&own=1&stats=1&comments=1"

    max_retries = 3
    xml_content = None

    for attempt in range(max_retries):
        req = urllib.request.Request(api_url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body_bytes = resp.read()
                xml_str = body_bytes.decode('utf-8', errors='replace')

                if "<message>" in xml_str and "accepted" in xml_str.lower():
                    if attempt < max_retries - 1:
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    else:
                        return {
                            'statusCode': 202,
                            'headers': {'Content-Type': 'application/json'},
                            'body': json.dumps({'status': 'processing', 'message': 'BGG collection is currently processing. Please retry shortly.'})
                        }
                xml_content = xml_str
                break
        except urllib.error.HTTPError as he:
            if he.code == 202:
                if attempt < max_retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                else:
                    return {
                        'statusCode': 202,
                        'headers': {'Content-Type': 'application/json'},
                        'body': json.dumps({'status': 'processing', 'message': 'BGG collection is currently processing. Please retry shortly.'})
                    }
            elif he.code == 404:
                return {
                    'statusCode': 404,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': f'BGG user {username} not found.'})
                }
            else:
                return {
                    'statusCode': he.code,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': f'BGG API error ({he.code}): {he.reason}'})
                }
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': f'Failed to query BGG: {str(e)}'})
            }

    if not xml_content:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'No response received from BGG'})
        }

    try:
        root = ET.fromstring(xml_content)
    except Exception as parse_err:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Failed to parse BGG XML response: {str(parse_err)}'})
        }

    if root.tag == 'errors':
        err_msg_el = root.find('.//error/message')
        err_text = err_msg_el.text if err_msg_el is not None else 'User does not exist on BoardGameGeek.'
        return {
            'statusCode': 404,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': err_text})
        }

    items = root.findall('.//item')
    total_owned = 0
    shelf_tags_detected = 0
    sample_matches = []

    for item in items:
        status_el = item.find('status')
        is_owned = True
        if status_el is not None:
            is_owned = (status_el.get('own') == '1')

        if is_owned:
            total_owned += 1
            game_id = item.get('objectid', '')
            name_el = item.find('name')
            game_name = name_el.text if name_el is not None and name_el.text else f'Game {game_id}'
            comment_el = item.find('comment')
            comment_text = comment_el.text if comment_el is not None and comment_el.text else ''

            if comment_text:
                m = shelf_pattern.search(comment_text)
                if m:
                    shelf_tags_detected += 1
                    if len(sample_matches) < 5:
                        loc = m.group(1).strip() if m.groups() else m.group(0).strip()
                        sample_matches.append({
                            'id': game_id,
                            'name': game_name,
                            'raw_comment': comment_text,
                            'extracted_location': loc
                        })

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'status': 'success',
            'username': username,
            'total_owned': total_owned,
            'shelf_tags_detected': shelf_tags_detected,
            'sample_matches': sample_matches,
            'shelf_regex': raw_regex
        })
    }


def _handle_check_slug(query_params):
    """
    Checks if a vanity URL slug is available for cafe registration.
    """
    slug = (query_params.get('slug') or '').strip().lower()
    if not slug:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'slug query parameter is required'})
        }

    if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', slug) or len(slug) < 3 or len(slug) > 50:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Slug must be 3-50 lowercase alphanumeric characters and hyphens.'})
        }

    try:
        res = cafes_table.get_item(Key={'cafe_id': slug})
        is_available = ('Item' not in res)
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'available': is_available, 'slug': slug})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Failed to check slug availability: {str(e)}'})
        }


def _handle_cafe_onboard(event, claims):
    """
    Onboards a cafe venue, persisting metadata to DynamoDB bgg-cafes,
    mirroring to S3, and enqueueing an initial collection scrape job to SQS.
    """
    user_id = claims.get('sub')
    if not user_id:
        return {
            'statusCode': 401,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Unauthorized: Missing user authentication'})
        }

    body_str = event.get('body', '{}')
    if event.get('isBase64Encoded', False):
        body_str = base64.b64decode(body_str).decode('utf-8')
    try:
        body = json.loads(body_str)
    except Exception:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Invalid JSON request body'})
        }

    cafe_id = (body.get('cafe_id') or body.get('slug') or '').strip().lower()
    name = (body.get('name') or '').strip()
    bgg_username = (body.get('bgg_username') or '').strip()

    if not cafe_id or not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', cafe_id) or len(cafe_id) < 3 or len(cafe_id) > 50:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Valid cafe_id/slug is required (3-50 lowercase alphanumeric characters and hyphens).'})
        }
    if not name or len(name) < 2 or len(name) > 100:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Venue name must be between 2 and 100 characters.'})
        }
    if not bgg_username or not re.match(r'^[a-zA-Z0-9_]{1,25}$', bgg_username):
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Valid BGG username is required.'})
        }

    try:
        table_count = int(body.get('table_count', 20))
        if table_count < 1 or table_count > 200:
            raise ValueError()
    except (ValueError, TypeError):
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'table_count must be an integer between 1 and 200.'})
        }

    # Check for existing cafe_id to ensure uniqueness
    existing = None
    try:
        res = cafes_table.get_item(Key={'cafe_id': cafe_id})
        existing = res.get('Item')
        if existing and existing.get('owner_cognito_id') != user_id:
            return {
                'statusCode': 409,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': f'Slug "{cafe_id}" is already registered by another account.'})
            }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Failed to check slug ownership: {str(e)}'})
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    wifi_ssid = (body.get('wifi_ssid') or '').strip()
    wifi_password = (body.get('wifi_password') or '').strip()
    tagline = (body.get('tagline') or '').strip()
    shelf_regex = (body.get('shelf_regex') or r'(?:Shelf|Location|Bin):?\s*([A-Za-z0-9\-]+)').strip()
    drink_pairings_enabled = bool(body.get('drink_pairings_enabled', True))
    staff_pin = (body.get('staff_pin') or '').strip()
    logo_url = (body.get('logo_url') or '').strip()
    featured_game_ids = [str(gid) for gid in body.get('featured_game_ids', []) if gid]

    cafe_item = {
        'cafe_id': cafe_id,
        'owner_cognito_id': user_id,
        'name': name,
        'bgg_username': bgg_username,
        'slug': cafe_id,
        'table_count': table_count,
        'wifi_ssid': wifi_ssid,
        'wifi_password': wifi_password,
        'tagline': tagline,
        'shelf_regex': shelf_regex,
        'drink_pairings_enabled': drink_pairings_enabled,
        'featured_game_ids': featured_game_ids,
        'staff_pin': staff_pin,
        'logo_url': logo_url,
        'created_at': existing.get('created_at', now_iso) if existing else now_iso,
        'updated_at': now_iso,
        'last_sync_timestamp': existing.get('last_sync_timestamp', None) if existing else None
    }

    # 1. Persist to DynamoDB
    try:
        cafes_table.put_item(Item=cafe_item)
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Failed to save venue to DynamoDB: {str(e)}'})
        }

    # 2. Mirror metadata to S3
    try:
        meta_key = f"data/cafes/{cafe_id}/meta.json"
        s3.put_object(
            Bucket=s3_bucket,
            Key=meta_key,
            Body=json.dumps(cafe_item, cls=DecimalEncoder, indent=2),
            ContentType='application/json'
        )

        reg_key = "data/cafes_registry.json"
        try:
            reg_resp = s3.get_object(Bucket=s3_bucket, Key=reg_key)
            registry = json.loads(reg_resp['Body'].read().decode('utf-8'))
        except Exception:
            registry = {}

        registry[cafe_id] = {
            'cafe_id': cafe_id,
            'name': name,
            'slug': cafe_id,
            'bgg_username': bgg_username,
            'table_count': table_count,
            'tagline': tagline,
            'logo_url': logo_url,
            'updated_at': now_iso
        }
        s3.put_object(
            Bucket=s3_bucket,
            Key=reg_key,
            Body=json.dumps(registry, cls=DecimalEncoder, indent=2),
            ContentType='application/json'
        )
    except Exception as s3_err:
        print(f"Warning: Failed to mirror cafe to S3: {s3_err}")

    # 3. Enqueue initial scrape to SQS
    try:
        queue_url = os.environ.get('USER_SQS_QUEUE_URL')
        if queue_url:
            sqs = boto3.client('sqs', region_name='us-east-1')
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps({
                    'username': bgg_username,
                    'cafe_id': cafe_id,
                    'is_cafe': True
                })
            )
    except Exception as sqs_err:
        print(f"Warning: Failed to send initial scrape SQS message: {sqs_err}")

    sanitized = {k: v for k, v in cafe_item.items() if k not in ('staff_pin',)}
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'status': 'success',
            'message': 'Venue successfully registered',
            'cafe': sanitized
        }, cls=DecimalEncoder)
    }


def _handle_cafe_meta(query_params):
    """
    Returns public branding, Wi-Fi details, and table count for a registered cafe.
    """
    cafe_id = (query_params.get('cafe_id') or query_params.get('slug') or '').strip().lower()
    if not cafe_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'cafe_id or slug query parameter is required'})
        }

    try:
        res = cafes_table.get_item(Key={'cafe_id': cafe_id})
        item = res.get('Item')
        if not item:
            try:
                meta_obj = s3.get_object(Bucket=s3_bucket, Key=f"data/cafes/{cafe_id}/meta.json")
                item = json.loads(meta_obj['Body'].read().decode('utf-8'))
            except Exception:
                item = None

        if not item:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': f'Cafe "{cafe_id}" not found'})
            }

        public_meta = {
            'cafe_id': item['cafe_id'],
            'name': item.get('name', ''),
            'slug': item.get('slug', item['cafe_id']),
            'bgg_username': item.get('bgg_username', ''),
            'table_count': int(item.get('table_count', 0)),
            'wifi_ssid': item.get('wifi_ssid', ''),
            'wifi_password': item.get('wifi_password', ''),
            'tagline': item.get('tagline', ''),
            'drink_pairings_enabled': bool(item.get('drink_pairings_enabled', True)),
            'logo_url': item.get('logo_url', '')
        }
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(public_meta, cls=DecimalEncoder)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Failed to retrieve cafe metadata: {str(e)}'})
        }


def _handle_cafe_collection(query_params):
    """
    Returns the cafe's owned board games library with shelf locations (GET /cafe/collection).
    Public endpoint used by patron collection browser.
    """
    cafe_id = (query_params.get('cafe_id') or query_params.get('slug') or '').strip().lower()
    if not cafe_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'cafe_id or slug query parameter is required'})
        }

    # 1. Resolve cafe BGG username
    bgg_username = None
    try:
        res = cafes_table.get_item(Key={'cafe_id': cafe_id})
        item = res.get('Item')
        if not item:
            try:
                meta_obj = s3.get_object(Bucket=s3_bucket, Key=f"data/cafes/{cafe_id}/meta.json")
                item = json.loads(meta_obj['Body'].read().decode('utf-8'))
            except Exception:
                item = None
        if item:
            bgg_username = item.get('bgg_username')
    except Exception as e:
        print(f"Warning: Could not fetch cafe item for {cafe_id}: {e}")

    if not bgg_username:
        bgg_username = cafe_id

    # 2. Fast Path: Check for pre-rendered collection.json in S3 (<50ms)
    json_keys = [
        f"data/cafes/{cafe_id}/collection.json",
        f"data/cafes/{bgg_username}/collection.json"
    ]
    for jkey in list(dict.fromkeys(json_keys)):
        try:
            resp_json = s3.get_object(Bucket=s3_bucket, Key=jkey)
            if resp_json:
                raw_bytes = resp_json['Body'].read()
                try:
                    data_obj = json.loads(raw_bytes.decode('utf-8'))
                    if isinstance(data_obj, dict) and ('collection' in data_obj or data_obj.get('status') == 'ready'):
                        return {
                            'statusCode': 200,
                            'headers': {
                                'Content-Type': 'application/json',
                                'Cache-Control': 'public, max-age=3600, s-maxage=86400'
                            },
                            'body': raw_bytes.decode('utf-8')
                        }
                except Exception:
                    # Rewind stream in case Body is a seekable stream (e.g. in test mocks)
                    if hasattr(resp_json.get('Body'), 'seek'):
                        try:
                            resp_json['Body'].seek(0)
                        except Exception:
                            pass
                    continue
        except Exception:
            continue

    # 3. Fallback / Cold Path: Load collection from S3 parquet and link
    try:
        import pyarrow.parquet as pq
        import pandas as pd

        parquet_keys = [
            f"data/cafes/{bgg_username}/collection.parquet",
            f"data/cafes/{cafe_id}/collection.parquet"
        ]
        resp = None
        for key in list(dict.fromkeys(parquet_keys)):
            try:
                resp = s3.get_object(Bucket=s3_bucket, Key=key)
                if resp:
                    break
            except Exception:
                continue

        if not resp:
            raise FileNotFoundError(f"No collection.parquet found for {cafe_id} or {bgg_username}")

        buffer = io.BytesIO(resp['Body'].read())
        table = pq.read_table(buffer)
        df = table.to_pandas()

        if df.empty or 'id' not in df.columns:
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Cache-Control': 'public, max-age=3600, s-maxage=86400'
                },
                'body': json.dumps({
                    'status': 'ready',
                    'cafe_id': cafe_id,
                    'bgg_username': bgg_username,
                    'total': 0,
                    'collection': []
                })
            }

        df['id'] = df['id'].astype(str)

        # Shelf location mapping from cafe_df
        shelf_map = {}
        for shelf_col in ['shelf_location', 'shelf']:
            if shelf_col in df.columns:
                for gid, sval in zip(df['id'], df[shelf_col]):
                    if pd.notna(sval) and str(sval).strip():
                        shelf_map[str(gid)] = str(sval).strip()
                break

        # Check if cafe collection is normalized (ID-only) or legacy
        # Link against master catalog (catalog.parquet) on IDs to get all game information
        catalog_lookup = {}
        if 'name' not in df.columns or len(df.columns) <= 3:
            try:
                catalog_df = _get_catalog_df()
                if catalog_df is not None:
                    ids_set = set(str(gid) for gid in df['id'].dropna())
                    display_cols = [
                        'id', 'name', 'thumbnail', 'year_published', 'rating', 'complexity',
                        'min_players', 'max_players', 'playing_time', 'rules_video_url',
                        'rules_video_id', 'rules_video_title', 'teach_time'
                    ]
                    avail_cols = [c for c in display_cols if c in catalog_df.columns]
                    matched = catalog_df[catalog_df['id'].astype(str).isin(ids_set)][avail_cols]
                    catalog_lookup = matched.set_index('id').to_dict(orient='index')
            except Exception as cat_err:
                print(f"Warning: Failed to link with master catalog: {cat_err}")

        records = []
        for row in df.to_dict(orient='records'):
            gid = str(row.get('id', ''))
            cat_row = catalog_lookup.get(gid) or {}

            name_val = _extract_collection_field_value(cat_row, row, 'name', '')
            thumb_val = _extract_collection_field_value(cat_row, row, 'thumbnail', '')
            yp_val = _extract_collection_field_value(cat_row, row, 'year_published')
            rat_val = _extract_collection_field_value(cat_row, row, 'rating')
            comp_val = _extract_collection_field_value(cat_row, row, 'complexity')
            min_p = _extract_collection_field_value(cat_row, row, 'min_players', 1)
            max_p = _extract_collection_field_value(cat_row, row, 'max_players', 1)
            play_t = _extract_collection_field_value(cat_row, row, 'playing_time', 0)

            rec = {
                'id': gid,
                'name': str(name_val) if name_val is not None else '',
                'thumbnail': str(thumb_val) if thumb_val is not None else '',
                'year_published': int(yp_val) if yp_val is not None and int(yp_val) != 0 else None,
                'rating': float(rat_val) if rat_val is not None else None,
                'complexity': float(comp_val) if comp_val is not None else None,
                'min_players': int(min_p) if min_p is not None else 1,
                'max_players': int(max_p) if max_p is not None else 1,
                'playing_time': int(play_t) if play_t is not None else 0,
            }
            shelf = shelf_map.get(gid) or row.get('shelf_location') or row.get('shelf')
            if pd.notna(shelf) and str(shelf).strip():
                rec['shelf_location'] = str(shelf).strip()

            for f in ['rules_video_url', 'rules_video_id', 'rules_video_title', 'teach_time']:
                val = _extract_collection_field_value(cat_row, row, f)
                if val is not None and str(val).strip():
                    rec[f] = str(val).strip()
            records.append(rec)

        response_payload = {
            'status': 'ready',
            'cafe_id': cafe_id,
            'bgg_username': bgg_username,
            'total': len(records),
            'collection': records
        }
        response_body = json.dumps(response_payload)

        # Pre-render write-through: save to S3 so all subsequent calls take <50ms
        try:
            s3.put_object(
                Bucket=s3_bucket,
                Key=f"data/cafes/{cafe_id}/collection.json",
                Body=response_body.encode('utf-8'),
                ContentType='application/json',
                CacheControl='public, max-age=3600, s-maxage=86400'
            )
        except Exception as put_err:
            print(f"Warning: Could not save prerendered collection.json: {put_err}")

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Cache-Control': 'public, max-age=3600, s-maxage=86400'
            },
            'body': response_body
        }
    except Exception as err:
        print(f"Error loading cafe collection for {cafe_id} ({bgg_username}): {err}")
        # Check if scraping in progress
        for status_key in list(dict.fromkeys([f"data/cafes/{bgg_username}/scrape_status.json", f"data/cafes/{cafe_id}/scrape_status.json"])):
            try:
                status_obj = s3.get_object(Bucket=s3_bucket, Key=status_key)
                status_data = json.loads(status_obj['Body'].read().decode('utf-8'))
                if status_data.get('status') == 'scraping':
                    return {
                        'statusCode': 200,
                        'headers': {'Content-Type': 'application/json'},
                        'body': json.dumps({
                            'status': 'scraping',
                            'message': 'Syncing library for this venue...',
                            'collection': []
                        })
                    }
            except Exception:
                pass

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'status': 'ready',
                'cafe_id': cafe_id,
                'total': 0,
                'collection': []
            })
        }


def _handle_cafe_sync(event, claims):
    """
    On-demand sync endpoint for cafe inventory (POST /cafe/sync).
    Requires Cognito authentication. Verifies caller ownership in bgg-cafes DynamoDB,
    dispatches an immediate collection scrape job to SQS with cafe context,
    clears any active cafe recommendation cache, and updates last_sync_timestamp.
    """
    user_id = claims.get('sub')
    if not user_id:
        return {
            'statusCode': 401,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Unauthorized: Missing user authentication'})
        }

    # Extract cafe_id from query parameters or request body
    query_params = event.get('queryStringParameters') or {}
    cafe_id = query_params.get('cafe_id')

    if not cafe_id:
        body_str = event.get('body', '{}')
        if event.get('isBase64Encoded', False):
            body_str = base64.b64decode(body_str).decode('utf-8')
        try:
            body = json.loads(body_str) if isinstance(body_str, str) else body_str
            if isinstance(body, dict):
                cafe_id = body.get('cafe_id')
        except Exception:
            pass

    if not cafe_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'cafe_id is required'})
        }

    cafe_id = str(cafe_id).strip().lower()

    # Look up cafe in DynamoDB
    try:
        res = cafes_table.get_item(Key={'cafe_id': cafe_id})
        cafe = res.get('Item')
        if not cafe:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': f'Cafe "{cafe_id}" not found'})
            }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Failed to query cafe registry: {str(e)}'})
        }

    # Verify caller is the owner
    if cafe.get('owner_cognito_id') != user_id:
        return {
            'statusCode': 403,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Forbidden: You do not have permission to sync this cafe'})
        }

    bgg_username = cafe.get('bgg_username')
    if not bgg_username:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Cafe "{cafe_id}" does not have an associated BGG username'})
        }

    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Update last_sync_timestamp in DynamoDB
    try:
        cafes_table.update_item(
            Key={'cafe_id': cafe_id},
            UpdateExpression="SET #lst = :now, #ua = :now",
            ExpressionAttributeNames={
                '#lst': 'last_sync_timestamp',
                '#ua': 'updated_at'
            },
            ExpressionAttributeValues={
                ':now': now_iso
            }
        )
    except Exception as e:
        print(f"Warning: Failed to update last_sync_timestamp in DynamoDB: {e}")

    # 2. Invalidate recommendation cache in S3
    try:
        cache_prefix = f"data/recommendation_cache/cafe_{cafe_id}_"
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=s3_bucket, Prefix=cache_prefix)
        objects_to_delete = []
        for page in pages:
            for obj in page.get('Contents', []):
                objects_to_delete.append({'Key': obj['Key']})
        # Invalidate pre-rendered collection.json
        objects_to_delete.append({'Key': f"data/cafes/{cafe_id}/collection.json"})
        if bgg_username and bgg_username != cafe_id:
            objects_to_delete.append({'Key': f"data/cafes/{bgg_username}/collection.json"})
        if objects_to_delete:
            s3.delete_objects(
                Bucket=s3_bucket,
                Delete={'Objects': objects_to_delete}
            )
            print(f"Cleared cache objects and collection.json for cafe {cafe_id}")
    except Exception as cache_err:
        print(f"Warning: Failed to clear recommendation/collection cache for cafe {cafe_id}: {cache_err}")

    # 3. Enqueue scrape job to SQS with cafe context
    try:
        queue_url = os.environ.get('USER_SQS_QUEUE_URL')
        if queue_url:
            sqs = boto3.client('sqs', region_name='us-east-1')
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps({
                    'username': bgg_username,
                    'cafe_id': cafe_id,
                    'is_cafe': True
                })
            )
        else:
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'USER_SQS_QUEUE_URL environment variable is not configured'})
            }
    except Exception as sqs_err:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Failed to enqueue scrape job: {str(sqs_err)}'})
        }

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'status': 'success',
            'message': f'Sync job successfully enqueued for cafe "{cafe_id}".',
            'cafe_id': cafe_id,
            'bgg_username': bgg_username,
            'last_sync_timestamp': now_iso
        })
    }


def _handle_sync_all_cafes():
    """
    Scans bgg-cafes DynamoDB table and dispatches an SQS collection scrape message
    for every registered cafe. Triggered by weekly EventBridge rule or scheduled task.
    """
    queue_url = os.environ.get('USER_SQS_QUEUE_URL')
    if not queue_url:
        print("Error: USER_SQS_QUEUE_URL not configured")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'USER_SQS_QUEUE_URL not configured'})
        }

    try:
        response = cafes_table.scan(
            ProjectionExpression="cafe_id, bgg_username"
        )
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = cafes_table.scan(
                ProjectionExpression="cafe_id, bgg_username",
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        sqs = boto3.client('sqs', region_name='us-east-1')
        queued = []
        for item in items:
            cafe_id = item.get('cafe_id')
            bgg_username = item.get('bgg_username')
            if cafe_id and bgg_username:
                sqs.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps({
                        'username': bgg_username,
                        'cafe_id': cafe_id,
                        'is_cafe': True
                    })
                )
                queued.append(cafe_id)

        print(f"Weekly cafe sync queued {len(queued)} venues.")
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'status': 'success', 'queued_count': len(queued), 'cafes': queued})
        }
    except Exception as e:
        print(f"Error during weekly cafe sync: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Weekly cafe sync failed: {str(e)}'})
        }



def _handle_get_my_cafes(event, claims):
    """
    Retrieves all cafes owned by the authenticated caller (GET /cafe/my-cafes).
    Queries bgg-cafes DynamoDB using the owner_cognito_id-index GSI.
    """
    user_id = claims.get('sub')
    if not user_id:
        return {
            'statusCode': 401,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Unauthorized: Missing user authentication'})
        }

    try:
        response = cafes_table.query(
            IndexName='owner_cognito_id-index',
            KeyConditionExpression=Key('owner_cognito_id').eq(user_id)
        )
        items = response.get('Items', [])
        sanitized = []
        for item in items:
            c = {k: v for k, v in item.items() if k != 'staff_pin'}
            sanitized.append(c)
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'status': 'success', 'cafes': sanitized}, cls=DecimalEncoder)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Failed to retrieve owned cafes: {str(e)}'})
        }


def _handle_cafe_update(event, claims):
    """
    Updates configuration for an existing cafe (POST /cafe/update).
    Requires Cognito authentication. Verifies caller is owner_cognito_id.
    Persists updates to DynamoDB bgg-cafes, mirrors metadata to S3,
    and updates cafes_registry.json.
    """
    user_id = claims.get('sub')
    if not user_id:
        return {
            'statusCode': 401,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Unauthorized: Missing user authentication'})
        }

    body_str = event.get('body', '{}')
    if event.get('isBase64Encoded', False):
        body_str = base64.b64decode(body_str).decode('utf-8')

    try:
        body = json.loads(body_str) if isinstance(body_str, str) else body_str
        if not isinstance(body, dict):
            body = {}
    except Exception:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Invalid JSON in request body'})
        }

    cafe_id = str(body.get('cafe_id', '')).strip().lower()
    if not cafe_id:
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'cafe_id is required'})
        }

    try:
        res = cafes_table.get_item(Key={'cafe_id': cafe_id})
        existing = res.get('Item')
        if not existing:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': f'Cafe "{cafe_id}" not found'})
            }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Failed to query cafe: {str(e)}'})
        }

    if existing.get('owner_cognito_id') != user_id:
        return {
            'statusCode': 403,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': 'Forbidden: You do not have permission to update this cafe'})
        }

    now_iso = datetime.now(timezone.utc).isoformat()
    update_item = dict(existing)

    if 'name' in body and body['name']:
        name_val = str(body['name']).strip()
        if len(name_val) <= 100:
            update_item['name'] = name_val

    if 'tagline' in body:
        update_item['tagline'] = str(body['tagline']).strip()

    if 'table_count' in body:
        try:
            tc = int(body['table_count'])
            if 1 <= tc <= 500:
                update_item['table_count'] = tc
        except (ValueError, TypeError):
            pass

    if 'wifi_ssid' in body:
        update_item['wifi_ssid'] = str(body['wifi_ssid']).strip()

    if 'wifi_password' in body:
        update_item['wifi_password'] = str(body['wifi_password']).strip()

    if 'shelf_regex' in body:
        update_item['shelf_regex'] = str(body['shelf_regex']).strip()

    if 'drink_pairings_enabled' in body:
        update_item['drink_pairings_enabled'] = bool(body['drink_pairings_enabled'])

    if 'logo_url' in body:
        update_item['logo_url'] = str(body['logo_url']).strip()

    if 'bgg_username' in body and body['bgg_username']:
        bgg_user = str(body['bgg_username']).strip()
        if re.match(r'^[a-zA-Z0-9_]{1,25}$', bgg_user):
            update_item['bgg_username'] = bgg_user

    update_item['updated_at'] = now_iso

    # 1. Update in DynamoDB
    try:
        cafes_table.put_item(Item=update_item)
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': f'Failed to update venue in DynamoDB: {str(e)}'})
        }

    # 2. Mirror metadata to S3
    try:
        meta_key = f"data/cafes/{cafe_id}/meta.json"
        s3.put_object(
            Bucket=s3_bucket,
            Key=meta_key,
            Body=json.dumps(update_item, cls=DecimalEncoder, indent=2),
            ContentType='application/json'
        )

        reg_key = "data/cafes_registry.json"
        try:
            reg_resp = s3.get_object(Bucket=s3_bucket, Key=reg_key)
            registry = json.loads(reg_resp['Body'].read().decode('utf-8'))
        except Exception:
            registry = {}

        registry[cafe_id] = {
            'cafe_id': cafe_id,
            'name': update_item.get('name'),
            'slug': update_item.get('slug', cafe_id),
            'bgg_username': update_item.get('bgg_username'),
            'table_count': update_item.get('table_count'),
            'tagline': update_item.get('tagline'),
            'logo_url': update_item.get('logo_url'),
            'updated_at': now_iso
        }
        s3.put_object(
            Bucket=s3_bucket,
            Key=reg_key,
            Body=json.dumps(registry, cls=DecimalEncoder, indent=2),
            ContentType='application/json'
        )
    except Exception as s3_err:
        print(f"Warning: Failed to mirror updated cafe to S3: {s3_err}")

    sanitized = {k: v for k, v in update_item.items() if k != 'staff_pin'}
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'status': 'success',
            'message': 'Cafe settings updated successfully',
            'cafe': sanitized
        }, cls=DecimalEncoder)
    }


def _lambda_handler_impl(event, context):
    # Scheduled EventBridge or direct action for weekly cafe sync
    if event.get('action') == 'sync_all_cafes' or (event.get('source') == 'aws.events' and any('cafe' in r for r in event.get('resources', []))):
        return _handle_sync_all_cafes()

    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    path = event.get('rawPath', '') or event.get('requestContext', {}).get('http', {}).get('path', '')
    query_params = event.get('queryStringParameters') or {}

    # Handle OPTIONS preflight request (CORS)
    if method == 'OPTIONS':
        return {
            'statusCode': 204,
            'headers': {
                'Access-Control-Allow-Headers': 'content-type,authorization',
                'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
                'Access-Control-Max-Age': '300'
            },
            'body': ''
        }

    # Public /cafe endpoints
    if '/cafe/validate-bgg' in path:
        return _handle_validate_bgg(query_params)
    if '/cafe/check-slug' in path:
        return _handle_check_slug(query_params)
    if '/cafe/meta' in path:
        return _handle_cafe_meta(query_params)
    if '/cafe/collection' in path:
        return _handle_cafe_collection(query_params)

    # Authenticated endpoints
    claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
    if '/cafe/onboard' in path:
        return _handle_cafe_onboard(event, claims)
    if '/cafe/sync' in path:
        return _handle_cafe_sync(event, claims)
    if '/cafe/my-cafes' in path:
        return _handle_get_my_cafes(event, claims)
    if '/cafe/update' in path:
        return _handle_cafe_update(event, claims)

    # Extract user ID from JWT Claims for /preferences
    user_id = claims.get('sub')
    if not user_id:
        return {
            'statusCode': 401,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': 'Unauthorized: Missing user sub claim'})
        }

    if method == 'GET':
        try:
            response = table.get_item(Key={'userId': user_id})
            item = response.get('Item')
            if not item:
                # Return default empty settings
                item = {
                    'userId': user_id,
                    'playgroups': [],
                    'saved_weights': {},
                    'user_preferences': {},
                    'bgg_username': None
                }
            elif 'bgg_username' not in item:
                item['bgg_username'] = None
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps(item, cls=DecimalEncoder)
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'error': f'Failed to retrieve preferences: {str(e)}'})
            }

    elif method == 'POST':
        try:
            body_str = event.get('body', '{}')
            if event.get('isBase64Encoded', False):
                body_str = base64.b64decode(body_str).decode('utf-8')
            body = json.loads(body_str)

            # Extract fields
            playgroups = body.get('playgroups', [])
            saved_weights = body.get('saved_weights', {})
            user_preferences = body.get('user_preferences', {})
            bgg_username = body.get('bgg_username')

            update_parts = []
            expression_attribute_values = {}
            expression_attribute_names = {}

            allowed_fields = ['playgroups', 'saved_weights', 'user_preferences', 'bgg_username']
            for field in allowed_fields:
                if field in body:
                    val = floats_to_decimals(body[field])
                    update_parts.append(f"#{field} = :{field}")
                    expression_attribute_values[f":{field}"] = val
                    expression_attribute_names[f"#{field}"] = field

            if update_parts:
                update_expression = "SET " + ", ".join(update_parts)
                table.update_item(
                    Key={'userId': user_id},
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_attribute_values,
                    ExpressionAttributeNames=expression_attribute_names
                )

            # Pre-warm the cache by triggering the user scraper
            if bgg_username:
                sqs = boto3.client('sqs', region_name='us-east-1')
                queue_url = os.environ.get('USER_SQS_QUEUE_URL')
                if queue_url:
                    sqs.send_message(
                        QueueUrl=queue_url,
                        MessageBody=bgg_username
                    )

            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'status': 'success', 'userId': user_id})
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'error': f'Failed to save preferences: {str(e)}'})
            }

    return {
        'statusCode': 405,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': json.dumps({'error': 'Method Not Allowed'})
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

def lambda_handler(event, context):
    response = _lambda_handler_impl(event, context)
    return _compress_response(event, response)
