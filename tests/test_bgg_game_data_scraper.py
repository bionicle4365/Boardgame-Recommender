import os
import sys
import json
from unittest.mock import MagicMock, patch
import pytest
import xml.etree.ElementTree as ET
import pandas as pd
import pyarrow

# Set env variables before import
os.environ['S3_OUTPUT_BUCKET_NAME'] = 'test-bucket'
os.environ['BGG_API_TOKEN'] = 'test-token'

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_game_data_scraper'))
import bgg_game_data_scraper

def test_xml_helpers():
    xml_str = """
    <item id="10">
        <name type="primary" value="Catan"/>
        <yearpublished value="1995"/>
        <description>Classic game</description>
        <link type="boardgamecategory" value="Negotiation"/>
        <link type="boardgamecategory" value="Trading"/>
    </item>
    """
    root = ET.fromstring(xml_str)
    
    assert bgg_game_data_scraper._get_element_value(root, "./name", attribute="value") == "Catan"
    assert bgg_game_data_scraper._get_element_value(root, "./yearpublished", attribute="value") == "1995"
    assert bgg_game_data_scraper._get_element_value(root, "./missing", attribute="value", default="N/A") == "N/A"
    
    assert bgg_game_data_scraper._get_element_text(root, "./description") == "Classic game"
    assert bgg_game_data_scraper._get_element_text(root, "./missing", default="N/A") == "N/A"
    
    links = bgg_game_data_scraper._get_links(root, "boardgamecategory")
    assert links == ["Negotiation", "Trading"]

@patch('requests.get')
def test_get_game_data_success(mock_get):
    xml_str = """
    <items>
        <item id="10" type="boardgame">
            <name type="primary" value="Catan"/>
            <yearpublished value="1995"/>
            <minplayers value="3"/>
            <maxplayers value="4"/>
            <playingtime value="60"/>
            <minplaytime value="45"/>
            <maxplaytime value="90"/>
            <minage value="10"/>
            <thumbnail>https://cf.geekdo-images.com/thumb/catan.png</thumbnail>
            <image>https://cf.geekdo-images.com/original/catan.png</image>
            <statistics>
                <ratings>
                    <bayesaverage value="7.25"/>
                    <averageweight value="2.32"/>
                </ratings>
            </statistics>
            <link type="boardgamecategory" value="Trading"/>
            <link type="boardgamemechanic" value="Dice Rolling"/>
            <link type="boardgamedesigner" value="Klaus Teuber"/>
            <link type="boardgamepublisher" value="Kosmos"/>
            <poll name="suggested_numplayers" title="Suggested Players">
                <results numplayers="3">
                    <result value="Best" numvotes="15"/>
                    <result value="Recommended" numvotes="5"/>
                    <result value="Not Recommended" numvotes="1"/>
                </results>
                <results numplayers="4">
                    <result value="Best" numvotes="2"/>
                    <result value="Recommended" numvotes="18"/>
                    <result value="Not Recommended" numvotes="0"/>
                </results>
                <results numplayers="2">
                    <result value="Best" numvotes="0"/>
                    <result value="Recommended" numvotes="1"/>
                    <result value="Not Recommended" numvotes="10"/>
                </results>
            </poll>
        </item>
    </items>
    """
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = xml_str.encode('utf-8')
    mock_get.return_value = mock_resp

    data = bgg_game_data_scraper.get_game_data(10)
    assert data is not None
    assert data['id'] == '10'
    assert data['name'] == 'Catan'
    assert data['year_published'] == 1995
    assert data['min_players'] == 3
    assert data['max_players'] == 4
    assert data['playing_time'] == 60
    assert data['min_playtime'] == 45
    assert data['max_playtime'] == 90
    assert data['min_age'] == 10
    assert data['rating'] == 7.25
    assert data['complexity'] == 2.32
    assert data['thumbnail'] == 'https://cf.geekdo-images.com/thumb/catan.png'
    assert data['image'] == 'https://cf.geekdo-images.com/original/catan.png'
    assert data['categories'] == ['Trading']
    assert data['mechanics'] == ['Dice Rolling']
    assert data['designers'] == ['Klaus Teuber']
    assert data['publishers'] == ['Kosmos']
    assert data['suggested_players_best'] == ['3']
    assert data['suggested_players_recommended'] == ['3', '4']

@patch('requests.get')
@patch('time.sleep') # prevent sleep from delaying tests
def test_get_game_data_retry_and_success(mock_sleep, mock_get):
    xml_str = """
    <items>
        <item id="10" type="boardgame">
            <name type="primary" value="Catan"/>
        </item>
    </items>
    """
    # 2 failures followed by 1 success
    mock_fail = MagicMock()
    mock_fail.raise_for_status.side_effect = Exception("HTTP 502")
    
    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_ok.content = xml_str.encode('utf-8')
    
    mock_get.side_effect = [mock_fail, mock_fail, mock_ok]

    data = bgg_game_data_scraper.get_game_data(10, max_retries=3, base_delay=0.1)
    assert data is not None
    assert data['name'] == 'Catan'
    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2

@patch('bgg_game_data_scraper.get_game_data')
@patch('pandas.DataFrame.to_parquet')
def test_lambda_handler_sqs_events(mock_to_parquet, mock_get_game_data):
    mock_get_game_data.return_value = {
        'id': '10',
        'type': 'boardgame',
        'name': 'Catan',
        'year_published': 1995,
        'min_players': 3,
        'max_players': 4,
        'playing_time': 60,
        'min_playtime': 45,
        'max_playtime': 90,
        'min_age': 10,
        'rating': 7.25,
        'complexity': 2.32,
        'thumbnail': 'https://cf.geekdo-images.com/thumb/catan.png',
        'image': 'https://cf.geekdo-images.com/original/catan.png',
        'categories': ['Trading'],
        'mechanics': ['Dice Rolling'],
        'designers': ['Klaus Teuber'],
        'publishers': ['Kosmos'],
        'suggested_players_best': ['3'],
        'suggested_players_recommended': ['3', '4']
    }

    event = {
        "Records": [
            {"messageId": "m1", "body": "10"}
        ]
    }
    response = bgg_game_data_scraper.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['processed_ids'] == [10]

    # Verify that parquet saving was called with correct arguments
    mock_to_parquet.assert_called_once()
    args, kwargs = mock_to_parquet.call_args
    assert args[0] == 's3://test-bucket/data/boardgames/10.parquet'
    assert kwargs['index'] is False
    assert kwargs['engine'] == 'pyarrow'
    assert isinstance(kwargs['schema'], pyarrow.Schema)

@patch('bgg_game_data_scraper.get_game_data')
def test_lambda_handler_game_not_found(mock_get_game_data):
    """Game not found on BGG (None) should be a graceful skip — no DLQ."""
    mock_get_game_data.return_value = None

    event = {
        "Records": [
            {"messageId": "m1", "body": "999"}
        ]
    }
    response = bgg_game_data_scraper.lambda_handler(event, None)
    # Graceful skip: message is deleted from queue (200), NOT routed to DLQ
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert 999 in res_body['processed_ids']
    assert 'batchItemFailures' not in response


@patch('bgg_game_data_scraper.get_game_data')
def test_lambda_handler_sqs_fetch_failures(mock_get_game_data):
    """Real API fetch failure (GAME_FETCH_FAILED) should route to DLQ."""
    mock_get_game_data.return_value = bgg_game_data_scraper.GAME_FETCH_FAILED

    event = {
        "Records": [
            {"messageId": "m1", "body": "999"}
        ]
    }
    response = bgg_game_data_scraper.lambda_handler(event, None)
    assert response['statusCode'] == 207
    res_body = json.loads(response['body'])
    assert res_body['failed_ids'] == [999]
    assert response['batchItemFailures'] == [{"itemIdentifier": "m1"}]
