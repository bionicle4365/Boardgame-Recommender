import os
import sys
import json
from unittest.mock import MagicMock, patch
import pytest

# Mock environment variables before imports
os.environ['DYNAMODB_TABLE_NAME'] = 'test-preferences-table'
os.environ['DYNAMODB_CAFES_TABLE_NAME'] = 'test-cafes-table'
os.environ['S3_OUTPUT_BUCKET_NAME'] = 'test-boardgame-app'
os.environ['USER_SQS_QUEUE_URL'] = 'https://sqs.us-east-1.amazonaws.com/123456789012/test-user-queue'

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_preferences'))
import bgg_preferences_handler


# ── GET /cafe/my-cafes Tests ─────────────────────────────────────────────────

def test_get_my_cafes_unauthorized():
    event = {
        'rawPath': '/cafe/my-cafes',
        'requestContext': {
            'http': {'method': 'GET'},
            'authorizer': {'jwt': {'claims': {}}}
        }
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'Unauthorized' in body['error']


@patch('bgg_preferences_handler.cafes_table')
def test_get_my_cafes_empty_list(mock_cafes_table):
    mock_cafes_table.query.return_value = {'Items': []}

    event = {
        'rawPath': '/cafe/my-cafes',
        'requestContext': {
            'http': {'method': 'GET'},
            'authorizer': {'jwt': {'claims': {'sub': 'user-no-cafes'}}}
        }
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'success'
    assert body['cafes'] == []


@patch('bgg_preferences_handler.cafes_table')
def test_get_my_cafes_success(mock_cafes_table):
    mock_cafes_table.query.return_value = {
        'Items': [
            {
                'cafe_id': 'the-malt-and-meeple',
                'owner_cognito_id': 'user-123',
                'name': 'The Malt & Meeple',
                'table_count': 20,
                'staff_pin': '9999',
                'wifi_ssid': 'Malt-Guest'
            },
            {
                'cafe_id': 'dice-box-cafe',
                'owner_cognito_id': 'user-123',
                'name': 'The Dice Box',
                'table_count': 15,
                'staff_pin': '1234',
                'wifi_ssid': 'Dice-Guest'
            }
        ]
    }

    event = {
        'rawPath': '/cafe/my-cafes',
        'requestContext': {
            'http': {'method': 'GET'},
            'authorizer': {'jwt': {'claims': {'sub': 'user-123'}}}
        }
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'success'
    assert len(body['cafes']) == 2
    assert body['cafes'][0]['name'] == 'The Malt & Meeple'
    # Ensure sensitive staff_pin is stripped
    assert 'staff_pin' not in body['cafes'][0]
    assert 'staff_pin' not in body['cafes'][1]


@patch('bgg_preferences_handler.cafes_table')
def test_get_my_cafes_db_error(mock_cafes_table):
    mock_cafes_table.query.side_effect = Exception("DynamoDB GSI Unavailable")

    event = {
        'rawPath': '/cafe/my-cafes',
        'requestContext': {
            'http': {'method': 'GET'},
            'authorizer': {'jwt': {'claims': {'sub': 'user-123'}}}
        }
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 500
    body = json.loads(response['body'])
    assert 'Failed to retrieve owned cafes' in body['error']


# ── POST /cafe/update Tests ──────────────────────────────────────────────────

def test_cafe_update_unauthorized():
    event = {
        'rawPath': '/cafe/update',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {}}}
        },
        'body': json.dumps({'cafe_id': 'the-malt-and-meeple'})
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'Unauthorized' in body['error']


def test_cafe_update_missing_cafe_id():
    event = {
        'rawPath': '/cafe/update',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {'sub': 'user-123'}}}
        },
        'body': json.dumps({'name': 'Updated Name'})
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'cafe_id is required' in body['error']


@patch('bgg_preferences_handler.cafes_table')
def test_cafe_update_not_found(mock_cafes_table):
    mock_cafes_table.get_item.return_value = {}  # Item not found

    event = {
        'rawPath': '/cafe/update',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {'sub': 'user-123'}}}
        },
        'body': json.dumps({'cafe_id': 'nonexistent-cafe', 'name': 'New Name'})
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 404
    body = json.loads(response['body'])
    assert 'not found' in body['error']


@patch('bgg_preferences_handler.cafes_table')
def test_cafe_update_forbidden_caller(mock_cafes_table):
    mock_cafes_table.get_item.return_value = {
        'Item': {
            'cafe_id': 'the-malt-and-meeple',
            'owner_cognito_id': 'different-owner-999',
            'name': 'The Malt & Meeple'
        }
    }

    event = {
        'rawPath': '/cafe/update',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {'sub': 'intruder-user'}}}
        },
        'body': json.dumps({'cafe_id': 'the-malt-and-meeple', 'name': 'Hacked Name'})
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 403
    body = json.loads(response['body'])
    assert 'Forbidden' in body['error']


@patch('bgg_preferences_handler.s3')
@patch('bgg_preferences_handler.cafes_table')
def test_cafe_update_success(mock_cafes_table, mock_s3):
    initial_cafe = {
        'cafe_id': 'the-malt-and-meeple',
        'owner_cognito_id': 'user-123',
        'name': 'Old Name',
        'tagline': 'Old Tagline',
        'table_count': 10,
        'wifi_ssid': 'OldSSID',
        'wifi_password': 'OldPassword',
        'shelf_regex': r'Shelf:\s*([A-Z0-9]+)',
        'staff_pin': 'SECRET_PIN',
        'created_at': '2026-01-01T00:00:00Z'
    }
    mock_cafes_table.get_item.return_value = {'Item': initial_cafe}

    # S3 mock read for registry
    registry_data = json.dumps({'the-malt-and-meeple': {'name': 'Old Name'}}).encode('utf-8')
    body_mock = MagicMock()
    body_mock.read.return_value = registry_data
    mock_s3.get_object.return_value = {'Body': body_mock}

    payload = {
        'cafe_id': 'the-malt-and-meeple',
        'name': 'The Malt & Meeple Gastropub',
        'tagline': 'Craft Beers and 500 Board Games',
        'table_count': 25,
        'wifi_ssid': 'MaltMeeple-Guest',
        'wifi_password': 'diceanddrafts',
        'shelf_regex': r'(?:Shelf|Loc):\s*([A-Za-z0-9\-]+)',
        'drink_pairings_enabled': False,
        'bgg_username': 'maltmeeple_hq'
    }

    event = {
        'rawPath': '/cafe/update',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {'sub': 'user-123'}}}
        },
        'body': json.dumps(payload)
    }

    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'success'
    assert body['message'] == 'Cafe settings updated successfully'

    # Check returned cafe object
    cafe = body['cafe']
    assert cafe['name'] == 'The Malt & Meeple Gastropub'
    assert cafe['table_count'] == 25
    assert cafe['wifi_ssid'] == 'MaltMeeple-Guest'
    assert cafe['wifi_password'] == 'diceanddrafts'
    assert cafe['bgg_username'] == 'maltmeeple_hq'
    assert cafe['drink_pairings_enabled'] is False
    assert 'staff_pin' not in cafe

    # Verify DynamoDB update
    mock_cafes_table.put_item.assert_called_once()
    saved_item = mock_cafes_table.put_item.call_args[1]['Item']
    assert saved_item['name'] == 'The Malt & Meeple Gastropub'
    assert saved_item['table_count'] == 25
    assert saved_item['staff_pin'] == 'SECRET_PIN'  # Preserved in backend store

    # Verify S3 mirror calls (meta.json and cafes_registry.json)
    assert mock_s3.put_object.call_count == 2
