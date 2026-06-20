import os
import sys
import json
from unittest.mock import MagicMock, patch
import pytest
import xml.etree.ElementTree as ET
import pandas as pd

# Set mock env variables before import
os.environ['S3_OUTPUT_BUCKET_NAME'] = 'test-bucket'
os.environ['BGG_API_TOKEN'] = 'test-token'

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_user_data_scraper'))
import bgg_user_data_scraper

def test_xml_helper():
    xml_str = '<item objectid="100"><status own="1"/></item>'
    root = ET.fromstring(xml_str)
    assert bgg_user_data_scraper._get_element_value(root, ".//status", attribute="own") == "1"

@patch('requests.get')
def test_get_user_data_success(mock_get):
    xml_str = """
    <items>
        <item objectid="10" subtype="boardgame">
            <name>Catan</name>
            <status own="1"/>
            <stats>
                <rating value="9"/>
            </stats>
        </item>
        <item objectid="20" subtype="boardgame">
            <name>Carcassonne</name>
            <status own="0"/>
            <stats>
                <rating value="N/A"/>
            </stats>
        </item>
    </items>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = xml_str.encode('utf-8')
    mock_get.return_value = mock_resp

    data = bgg_user_data_scraper.get_user_data("testuser")
    assert data is not None
    assert len(data) == 1 # Only ID 10 is own/rated (ID 20 has own=0 and rating=N/A, so it is skipped)
    assert data[0]['id'] == '10'
    assert data[0]['username'] == 'testuser'
    assert data[0]['rating'] == 9.0
    assert data[0]['own'] is True

@patch('requests.get')
@patch('time.sleep')
def test_get_user_data_retry_limit(mock_sleep, mock_get):
    mock_fail = MagicMock()
    mock_fail.raise_for_status.side_effect = Exception("HTTP 500")
    mock_get.side_effect = [mock_fail, mock_fail, mock_fail]

    data = bgg_user_data_scraper.get_user_data("testuser")
    assert data is None
    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2

@patch('bgg_user_data_scraper.get_user_data')
@patch('pandas.DataFrame.to_parquet')
def test_lambda_handler_success(mock_to_parquet, mock_get_user_data):
    mock_get_user_data.return_value = [
        {'id': '10', 'username': 'testuser', 'rating': 9.0, 'own': True}
    ]

    event = {
        "Records": [
            {"messageId": "msg123", "body": "testuser"}
        ]
    }
    response = bgg_user_data_scraper.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['processed_ids'] == ['testuser']
    
    mock_to_parquet.assert_called_once_with(
        's3://test-bucket/data/users/testuser.parquet',
        index=False,
        engine='pyarrow'
    )
