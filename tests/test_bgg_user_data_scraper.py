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

@patch('requests.get')
def test_get_user_data_invalid_user(mock_get):
    xml_str = """
    <errors>
        <error>
            <message>Invalid username specified</message>
        </error>
    </errors>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = xml_str.encode('utf-8')
    mock_get.return_value = mock_resp

    data = bgg_user_data_scraper.get_user_data("tester1")
    assert data == [] # Should return an empty list gracefully

@patch('bgg_user_data_scraper.get_user_data')
@patch('pandas.DataFrame.to_parquet')
def test_lambda_handler_invalid_user_saves_empty_parquet(mock_to_parquet, mock_get_user_data):
    mock_get_user_data.return_value = [] # User doesn't exist or empty collection

    event = {
        "Records": [
            {"messageId": "msg124", "body": "tester1"}
        ]
    }
    response = bgg_user_data_scraper.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['processed_ids'] == ['tester1']
    
    mock_to_parquet.assert_called_once()
    # Check that it saves with the expected columns
    args, kwargs = mock_to_parquet.call_args
    assert args[0] == 's3://test-bucket/data/users/tester1.parquet'


@patch('requests.get')
def test_get_user_data_cafe_mode(mock_get):
    xml_str = """
    <items>
        <item objectid="100" subtype="boardgame">
            <name>Azul</name>
            <yearpublished>2017</yearpublished>
            <image>https://example.com/azul.jpg</image>
            <thumbnail>https://example.com/azul_thumb.jpg</thumbnail>
            <stats minplayers="2" maxplayers="4" minplaytime="30" maxplaytime="45" playingtime="45" numowned="50000">
                <rating value="8.5">
                    <usersrated value="45000"/>
                    <average value="7.8"/>
                </rating>
            </stats>
            <status own="1"/>
        </item>
        <item objectid="200" subtype="boardgame">
            <name>Unowned Game</name>
            <yearpublished>2020</yearpublished>
            <stats minplayers="1" maxplayers="5" minplaytime="60" maxplaytime="90" playingtime="60" numowned="100">
                <rating value="7.0">
                    <usersrated value="80"/>
                    <average value="6.5"/>
                </rating>
            </stats>
            <status own="0"/>
        </item>
    </items>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = xml_str.encode('utf-8')
    mock_get.return_value = mock_resp

    data = bgg_user_data_scraper.get_user_data("testcafe", is_cafe=True)
    assert data is not None
    assert len(data) == 1
    game = data[0]
    assert game['id'] == '100'
    assert game['name'] == 'Azul'
    assert game['year_published'] == 2017
    assert game['min_players'] == 2
    assert game['max_players'] == 4
    assert game['playing_time'] == 45
    assert game['min_playtime'] == 30
    assert game['max_playtime'] == 45
    assert game['thumbnail'] == 'https://example.com/azul_thumb.jpg'
    assert game['image'] == 'https://example.com/azul.jpg'
    assert game['rating'] == 8.5
    assert game['average_rating'] == 7.8
    assert game['users_rated'] == 45000
    assert game['num_owned'] == 50000
    assert game['own'] is True


@patch('bgg_user_data_scraper.get_user_data')
@patch('pandas.DataFrame.to_parquet')
def test_lambda_handler_cafe_mode_saves_cafe_parquet(mock_to_parquet, mock_get_user_data):
    mock_get_user_data.return_value = [
        {
            'id': '100',
            'name': 'Azul',
            'year_published': 2017,
            'min_players': 2,
            'max_players': 4,
            'playing_time': 45,
            'min_playtime': 30,
            'max_playtime': 45,
            'thumbnail': 'https://example.com/azul_thumb.jpg',
            'image': 'https://example.com/azul.jpg',
            'rating': 8.5,
            'average_rating': 7.8,
            'users_rated': 45000,
            'num_owned': 50000,
            'own': True
        }
    ]

    event = {
        "Records": [
            {
                "messageId": "msg_cafe_1",
                "body": json.dumps({
                    "username": "malt_bgg",
                    "cafe_id": "malt-and-meeple",
                    "is_cafe": True
                })
            }
        ]
    }
    response = bgg_user_data_scraper.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['processed_ids'] == ['malt_bgg']

    mock_get_user_data.assert_called_once_with('malt_bgg', is_cafe=True)
    mock_to_parquet.assert_called_once_with(
        's3://test-bucket/data/cafes/malt-and-meeple/collection.parquet',
        index=False,
        engine='pyarrow'
    )

