import os
import json
import base64
import boto3
from decimal import Decimal

# Helper to handle Decimal types in DynamoDB JSON serialization
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# Initialize DynamoDB Resource
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'bgg-user-preferences')
table = dynamodb.Table(table_name)

def lambda_handler(event, context):
    # Handle OPTIONS preflight request (CORS)
    # API Gateway HTTP API proxy format passes routeKey or requestContext.http.method
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    
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

    # Extract user ID from JWT Claims
    claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
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
            
            # Helper function to convert float types to Decimals for DynamoDB
            def floats_to_decimals(obj):
                if isinstance(obj, float):
                    return Decimal(str(obj))
                elif isinstance(obj, dict):
                    return {k: floats_to_decimals(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [floats_to_decimals(x) for x in obj]
                return obj

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
