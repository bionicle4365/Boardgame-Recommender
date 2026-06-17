import os
import urllib.request
import urllib.error
import json

def lambda_handler(event, context):
    query_params = event.get('queryStringParameters') or {}
    username = query_params.get('username')
    if not username:
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': 'username query parameter is required'})
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
                    'Content-Type': 'application/xml',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': content
            }
    except urllib.error.HTTPError as e:
        # Forward HTTP errors directly from BGG (e.g. 202 Accepted, 400, etc.)
        content = e.read().decode('utf-8')
        return {
            'statusCode': e.code,
            'headers': {
                'Content-Type': 'application/xml',
                'Access-Control-Allow-Origin': '*'
            },
            'body': content
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }
