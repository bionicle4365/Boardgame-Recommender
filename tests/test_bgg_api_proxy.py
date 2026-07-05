import os
import sys
import json
from unittest.mock import patch, MagicMock
import urllib.error
import pytest

# Add the lambda dir to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_api_proxy'))
import bgg_api_proxy

def test_lambda_handler_missing_username():
    event = {
        'queryStringParameters': {}
    }
    response = bgg_api_proxy.lambda_handler(event, None)
    assert response['statusCode'] == 400
    assert 'username query parameter is required' in response['body']

def test_lambda_handler_invalid_username():
    event = {
        'queryStringParameters': {
            'username': 'invalid-user!'
        }
    }
    response = bgg_api_proxy.lambda_handler(event, None)
    assert response['statusCode'] == 400
    assert 'Invalid username format' in response['body']

@patch('urllib.request.urlopen')
def test_lambda_handler_success(mock_urlopen):
    # Mock response
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.read.return_value = b"<collection></collection>"
    mock_urlopen.return_value.__enter__.return_value = mock_resp

    event = {
        'queryStringParameters': {
            'username': 'bionicle4365'
        }
    }
    response = bgg_api_proxy.lambda_handler(event, None)
    assert response['statusCode'] == 200
    assert response['headers']['Content-Type'] == 'application/xml'
    assert response['body'] == "<collection></collection>"
    assert 'Access-Control-Allow-Origin' not in response['headers']
