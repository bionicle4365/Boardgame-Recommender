import os
import sys
import json
from unittest.mock import MagicMock, patch
import pytest
from decimal import Decimal

# Set mock env variables BEFORE importing bgg_preferences_handler
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_ACCESS_KEY_ID'] = 'mock-key'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'mock-secret'
os.environ['DYNAMODB_TABLE_NAME'] = 'bgg-user-preferences'

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_preferences'))
import bgg_preferences_handler

@patch('bgg_preferences_handler.table')
def test_lambda_handler_options(mock_table):
    event = {
        'requestContext': {
            'http': {
                'method': 'OPTIONS'
            }
        }
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 204
    assert response['headers']['Access-Control-Allow-Methods'] == 'GET,POST,OPTIONS'
    mock_table.get_item.assert_not_called()

@patch('bgg_preferences_handler.table')
def test_lambda_handler_unauthorized(mock_table):
    event = {
        'requestContext': {}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 401
    assert 'Unauthorized' in response['body']

@patch('bgg_preferences_handler.table')
def test_lambda_handler_get_default(mock_table):
    mock_table.get_item.return_value = {} # Record does not exist
    
    event = {
        'requestContext': {
            'http': {
                'method': 'GET'
            },
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'user-123'
                    }
                }
            }
        }
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['userId'] == 'user-123'
    assert body['playgroups'] == []
    assert body['saved_weights'] == {}
    mock_table.get_item.assert_called_once_with(Key={'userId': 'user-123'})

@patch('bgg_preferences_handler.table')
def test_lambda_handler_get_existing(mock_table):
    mock_table.get_item.return_value = {
        'Item': {
            'userId': 'user-123',
            'playgroups': [{'id': 'g1', 'name': 'G1'}],
            'saved_weights': {'mech': Decimal('0.5')}
        }
    }
    
    event = {
        'requestContext': {
            'http': {
                'method': 'GET'
            },
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'user-123'
                    }
                }
            }
        }
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['userId'] == 'user-123'
    assert len(body['playgroups']) == 1
    assert body['saved_weights']['mech'] == 0.5

@patch('bgg_preferences_handler.table')
def test_lambda_handler_post_success(mock_table):
    event = {
        'requestContext': {
            'http': {
                'method': 'POST'
            },
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'user-123'
                    }
                }
            }
        },
        'body': json.dumps({
            'playgroups': [{'id': 'g1', 'name': 'G1'}],
            'saved_weights': {'mech': 0.5, 'cat': 0.8}
        })
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'success'
    
    # Verify update_item call details
    mock_table.update_item.assert_called_once()
    args, kwargs = mock_table.update_item.call_args
    assert kwargs['Key'] == {'userId': 'user-123'}
    assert '#playgroups' in kwargs['UpdateExpression']
    assert '#saved_weights' in kwargs['UpdateExpression']
    assert kwargs['ExpressionAttributeValues'][':saved_weights']['mech'] == Decimal('0.5')
    assert kwargs['ExpressionAttributeValues'][':saved_weights']['cat'] == Decimal('0.8')


@patch('bgg_preferences_handler.table')
@patch('boto3.client')
def test_lambda_handler_post_partial_update(mock_boto_client, mock_table):
    mock_sqs = MagicMock()
    mock_boto_client.return_value = mock_sqs
    
    event = {
        'requestContext': {
            'http': {
                'method': 'POST'
            },
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'user-123'
                    }
                }
            }
        },
        'body': json.dumps({
            'bgg_username': 'bionicle4365'
        })
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    
    mock_table.update_item.assert_called_once()
    args, kwargs = mock_table.update_item.call_args
    assert kwargs['Key'] == {'userId': 'user-123'}
    assert kwargs['UpdateExpression'] == 'SET #bgg_username = :bgg_username'
    assert kwargs['ExpressionAttributeValues'] == {':bgg_username': 'bionicle4365'}
    assert kwargs['ExpressionAttributeNames'] == {'#bgg_username': 'bgg_username'}
    
    # Verify SQS trigger
    mock_boto_client.assert_called_once_with('sqs', region_name='us-east-1')
    mock_sqs.send_message.assert_called_once()

@patch('bgg_preferences_handler.table')
def test_lambda_handler_compression(mock_table):
    import gzip
    import base64

    mock_table.get_item.return_value = {
        'Item': {
            'userId': 'user-123',
            'playgroups': [],
            'saved_weights': {}
        }
    }
    
    event = {
        'requestContext': {
            'http': {
                'method': 'GET'
            },
            'authorizer': {
                'jwt': {
                    'claims': {
                        'sub': 'user-123'
                    }
                }
            }
        },
        'headers': {
            'accept-encoding': 'gzip'
        }
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    assert response['headers']['Content-Type'] == 'application/json'
    assert response['headers']['Content-Encoding'] == 'gzip'
    assert response['isBase64Encoded'] is True

    # Decode and decompress
    decoded_body = base64.b64decode(response['body'])
    decompressed_body = gzip.decompress(decoded_body).decode('utf-8')
    body_data = json.loads(decompressed_body)
    assert body_data['userId'] == 'user-123'


