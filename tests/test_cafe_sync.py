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


# ── 1. Authentication & Validation Tests ─────────────────────────────────────

def test_cafe_sync_unauthorized():
    event = {
        'rawPath': '/cafe/sync',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {}}}
        },
        'queryStringParameters': {'cafe_id': 'the-malt-and-meeple'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 401
    body = json.loads(response['body'])
    assert 'Unauthorized' in body['error']


def test_cafe_sync_missing_cafe_id():
    event = {
        'rawPath': '/cafe/sync',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {'sub': 'user-123'}}}
        },
        'queryStringParameters': {},
        'body': json.dumps({})
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'cafe_id is required' in body['error']


@patch('bgg_preferences_handler.cafes_table')
def test_cafe_sync_cafe_not_found(mock_cafes_table):
    mock_cafes_table.get_item.return_value = {}  # Item not found

    event = {
        'rawPath': '/cafe/sync',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {'sub': 'user-123'}}}
        },
        'queryStringParameters': {'cafe_id': 'nonexistent-cafe'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 404
    body = json.loads(response['body'])
    assert 'not found' in body['error']


@patch('bgg_preferences_handler.cafes_table')
def test_cafe_sync_forbidden_caller(mock_cafes_table):
    # Cafe is owned by different user
    mock_cafes_table.get_item.return_value = {
        'Item': {
            'cafe_id': 'the-malt-and-meeple',
            'owner_cognito_id': 'different-user-999',
            'bgg_username': 'maltandmeeple'
        }
    }

    event = {
        'rawPath': '/cafe/sync',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {'sub': 'attacker-user-123'}}}
        },
        'queryStringParameters': {'cafe_id': 'the-malt-and-meeple'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 403
    body = json.loads(response['body'])
    assert 'Forbidden' in body['error']


@patch('bgg_preferences_handler.cafes_table')
def test_cafe_sync_missing_bgg_username(mock_cafes_table):
    mock_cafes_table.get_item.return_value = {
        'Item': {
            'cafe_id': 'the-malt-and-meeple',
            'owner_cognito_id': 'user-123',
            'bgg_username': ''
        }
    }

    event = {
        'rawPath': '/cafe/sync',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {'sub': 'user-123'}}}
        },
        'queryStringParameters': {'cafe_id': 'the-malt-and-meeple'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 400
    body = json.loads(response['body'])
    assert 'associated BGG username' in body['error']


# ── 2. On-Demand Sync Success & Cache Invalidation Tests ───────────────────────

@patch('bgg_preferences_handler.cafes_table')
@patch('bgg_preferences_handler.s3')
@patch('boto3.client')
def test_cafe_sync_success_query_param(mock_boto_client, mock_s3, mock_cafes_table):
    mock_cafes_table.get_item.return_value = {
        'Item': {
            'cafe_id': 'the-malt-and-meeple',
            'owner_cognito_id': 'owner-user-123',
            'bgg_username': 'maltandmeeple',
            'table_count': 15
        }
    }
    mock_sqs = MagicMock()
    mock_boto_client.return_value = mock_sqs

    # Mock S3 list_objects_v2 paginator for cache invalidation
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {
            'Contents': [
                {'Key': 'data/recommendation_cache/cafe_the-malt-and-meeple_party_4_30.json'},
                {'Key': 'data/recommendation_cache/cafe_the-malt-and-meeple_strategy_2_60.json'}
            ]
        }
    ]
    mock_s3.get_paginator.return_value = mock_paginator

    event = {
        'rawPath': '/cafe/sync',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {'sub': 'owner-user-123'}}}
        },
        'queryStringParameters': {'cafe_id': 'the-malt-and-meeple'}
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'success'
    assert body['cafe_id'] == 'the-malt-and-meeple'
    assert body['bgg_username'] == 'maltandmeeple'
    assert 'last_sync_timestamp' in body

    # 1. DynamoDB updated last_sync_timestamp
    mock_cafes_table.update_item.assert_called_once()
    update_kwargs = mock_cafes_table.update_item.call_args[1]
    assert update_kwargs['Key'] == {'cafe_id': 'the-malt-and-meeple'}

    # 2. S3 cache objects deleted
    mock_s3.delete_objects.assert_called_once_with(
        Bucket=bgg_preferences_handler.s3_bucket,
        Delete={'Objects': [
            {'Key': 'data/recommendation_cache/cafe_the-malt-and-meeple_party_4_30.json'},
            {'Key': 'data/recommendation_cache/cafe_the-malt-and-meeple_strategy_2_60.json'}
        ]}
    )

    # 3. SQS message dispatched with cafe context
    mock_boto_client.assert_called_with('sqs', region_name='us-east-1')
    mock_sqs.send_message.assert_called_once()
    sqs_kwargs = mock_sqs.send_message.call_args[1]
    sent_payload = json.loads(sqs_kwargs['MessageBody'])
    assert sent_payload['username'] == 'maltandmeeple'
    assert sent_payload['cafe_id'] == 'the-malt-and-meeple'
    assert sent_payload['is_cafe'] is True


@patch('bgg_preferences_handler.cafes_table')
@patch('bgg_preferences_handler.s3')
@patch('boto3.client')
def test_cafe_sync_success_json_body(mock_boto_client, mock_s3, mock_cafes_table):
    mock_cafes_table.get_item.return_value = {
        'Item': {
            'cafe_id': 'the-malt-and-meeple',
            'owner_cognito_id': 'owner-user-123',
            'bgg_username': 'maltandmeeple'
        }
    }
    mock_sqs = MagicMock()
    mock_boto_client.return_value = mock_sqs

    # Empty cache pagination
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{}]
    mock_s3.get_paginator.return_value = mock_paginator

    event = {
        'rawPath': '/cafe/sync',
        'requestContext': {
            'http': {'method': 'POST'},
            'authorizer': {'jwt': {'claims': {'sub': 'owner-user-123'}}}
        },
        'body': json.dumps({'cafe_id': 'THE-MALT-AND-MEEPLE'})
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'success'
    assert body['cafe_id'] == 'the-malt-and-meeple'

    mock_sqs.send_message.assert_called_once()


# ── 3. EventBridge Weekly Scheduled Sync Tests ───────────────────────────────

@patch('bgg_preferences_handler.cafes_table')
@patch('boto3.client')
def test_sync_all_cafes_scheduled(mock_boto_client, mock_cafes_table):
    mock_cafes_table.scan.return_value = {
        'Items': [
            {'cafe_id': 'cafe-alpha', 'bgg_username': 'user_alpha'},
            {'cafe_id': 'cafe-beta', 'bgg_username': 'user_beta'}
        ]
    }
    mock_sqs = MagicMock()
    mock_boto_client.return_value = mock_sqs

    event = {
        'source': 'aws.events',
        'resources': ['arn:aws:events:us-east-1:123456789012:rule/weekly-bgg-cafe-sync-schedule']
    }
    response = bgg_preferences_handler.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['status'] == 'success'
    assert body['queued_count'] == 2
    assert body['cafes'] == ['cafe-alpha', 'cafe-beta']

    assert mock_sqs.send_message.call_count == 2
    calls = mock_sqs.send_message.call_args_list
    first_body = json.loads(calls[0][1]['MessageBody'])
    assert first_body['username'] == 'user_alpha'
    assert first_body['cafe_id'] == 'cafe-alpha'
    assert first_body['is_cafe'] is True
