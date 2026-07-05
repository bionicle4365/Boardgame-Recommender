import os
import urllib.request
import urllib.error
import json
import re

def lambda_handler(event, context):
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

