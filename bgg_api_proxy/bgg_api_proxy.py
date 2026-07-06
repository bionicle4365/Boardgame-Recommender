import os
import urllib.request
import urllib.error
import json
import re

def _lambda_handler_impl(event, context):
    query_params = event.get('queryStringParameters') or {}
    username = query_params.get('username')
    if not username:
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': 'username query parameter is required'})
        }

    # Validate username format
    if not re.match(r'^[a-zA-Z0-9_]{1,25}$', username):
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': 'Invalid username format'})
        }

    bgg_api_token = os.environ.get('BGG_API_TOKEN')
    headers = {}
    if bgg_api_token:
        headers['Authorization'] = f'Bearer {bgg_api_token}'

    # BGG XML API v2 Collection endpoint
    api_url = f"https://boardgamegeek.com/xmlapi2/collection?username={username}&stats=1"
    
    req = urllib.request.Request(api_url, headers=headers)
    
    try:
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            content = response.read().decode('utf-8')
            return {
                'statusCode': status_code,
                'headers': {
                    'Content-Type': 'application/xml'
                },
                'body': content
            }
    except urllib.error.HTTPError as e:
        # Forward HTTP errors directly from BGG (e.g. 202 Accepted, 400, etc.)
        content = e.read().decode('utf-8')
        return {
            'statusCode': e.code,
            'headers': {
                'Content-Type': 'application/xml'
            },
            'body': content
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': str(e)})
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

def lambda_handler(event, context):
    response = _lambda_handler_impl(event, context)
    return _compress_response(event, response)

