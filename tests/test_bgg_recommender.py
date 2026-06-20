import os
import sys
import json
import math
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, mock_open
import pytest
import pandas as pd
import numpy as np
from botocore.exceptions import ClientError

# Set mock env variables BEFORE importing bgg_recommender to satisfy boto3 initialization
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_ACCESS_KEY_ID'] = 'mock-key'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'mock-secret'
os.environ['S3_OUTPUT_BUCKET_NAME'] = 'test-bucket'
os.environ['USER_SQS_QUEUE_URL'] = 'https://sqs.test.com'
os.environ['BGG_API_TOKEN'] = 'test-token'

# Mock boto3.client to avoid UnknownServiceError: 'bedrock-runtime' on older botocore
import boto3
original_client = boto3.client
def mock_boto3_client(service_name, *args, **kwargs):
    if service_name == 'bedrock-runtime':
        return MagicMock()
    try:
        return original_client(service_name, *args, **kwargs)
    except Exception:
        return MagicMock()
boto3.client = mock_boto3_client

# Add the lambda dir to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_recommender'))
import bgg_recommender

@pytest.fixture(autouse=True)
def reset_globals():
    # Reset in-memory cache before each test
    bgg_recommender.CATALOG_CACHE = None
    yield

def test_safe_list():
    assert bgg_recommender.safe_list([1, 2, 3]) == [1, 2, 3]
    assert bgg_recommender.safe_list(np.array([4, 5])) == [4, 5]
    assert bgg_recommender.safe_list(None) == []
    assert bgg_recommender.safe_list("not-a-list") == []

@patch('bgg_recommender.s3')
@patch('pandas.read_parquet')
def test_get_catalog_success(mock_read_parquet, mock_s3):
    mock_df = pd.DataFrame([{"id": "1", "name": "Catan"}])
    mock_read_parquet.return_value = mock_df

    # Test cache miss & successful download
    df = bgg_recommender.get_catalog()
    assert df is not None
    assert len(df) == 1
    assert df.iloc[0]["name"] == "Catan"
    mock_s3.download_file.assert_called_once_with('test-bucket', 'data/boardgames_combined/catalog.parquet', '/tmp/catalog.parquet')

    # Test cache hit (should not call download_file again)
    mock_s3.reset_mock()
    df2 = bgg_recommender.get_catalog()
    assert df2 is df
    mock_s3.download_file.assert_not_called()

@patch('bgg_recommender.s3')
def test_get_catalog_failure(mock_s3):
    mock_s3.download_file.side_effect = Exception("S3 download error")
    df = bgg_recommender.get_catalog()
    assert df is None

@patch('bgg_recommender.s3')
def test_get_user_profile_status_fresh(mock_s3):
    now = datetime.now(timezone.utc)
    mock_s3.head_object.return_value = {
        'LastModified': now - timedelta(hours=5)
    }
    exists, is_stale, modified = bgg_recommender.get_user_profile_status("user1", ttl_hours=24)
    assert exists is True
    assert is_stale is False
    assert modified == now - timedelta(hours=5)

@patch('bgg_recommender.s3')
def test_get_user_profile_status_stale(mock_s3):
    now = datetime.now(timezone.utc)
    mock_s3.head_object.return_value = {
        'LastModified': now - timedelta(hours=25)
    }
    exists, is_stale, modified = bgg_recommender.get_user_profile_status("user1", ttl_hours=24)
    assert exists is True
    assert is_stale is True

@patch('bgg_recommender.s3')
def test_get_user_profile_status_missing(mock_s3):
    err_resp = {'Error': {'Code': '404', 'Message': 'Not Found'}}
    mock_s3.head_object.side_effect = ClientError(err_resp, 'HeadObject')
    exists, is_stale, modified = bgg_recommender.get_user_profile_status("user1", ttl_hours=24)
    assert exists is False
    assert is_stale is False
    assert modified is None

@patch('bgg_recommender.sqs')
def test_trigger_background_scrape(mock_sqs):
    bgg_recommender.trigger_background_scrape("user1")
    mock_sqs.send_message.assert_called_once_with(
        QueueUrl='https://sqs.test.com',
        MessageBody='user1'
    )

@patch('bgg_recommender.s3')
@patch('builtins.open', new_callable=mock_open, read_data='[{"name": "Catan", "reason": "like"}]')
def test_get_cached_recommendations_fresh(mock_file, mock_s3):
    now = datetime.now(timezone.utc)
    mock_s3.head_object.return_value = {
        'LastModified': now - timedelta(hours=2)
    }
    recs = bgg_recommender.get_cached_recommendations("cache-key", now - timedelta(hours=4), ttl_hours=24)
    assert recs == [{"name": "Catan", "reason": "like"}]

@patch('bgg_recommender.s3')
def test_get_cached_recommendations_stale(mock_s3):
    now = datetime.now(timezone.utc)
    mock_s3.head_object.return_value = {
        'LastModified': now - timedelta(hours=25)
    }
    recs = bgg_recommender.get_cached_recommendations("cache-key", now - timedelta(hours=30), ttl_hours=24)
    assert recs is None

@patch('bgg_recommender.s3')
def test_get_cached_recommendations_invalidated(mock_s3):
    now = datetime.now(timezone.utc)
    mock_s3.head_object.return_value = {
        'LastModified': now - timedelta(hours=5)
    }
    # profile updated at now-2h, which is newer than recommendations cached at now-5h
    recs = bgg_recommender.get_cached_recommendations("cache-key", now - timedelta(hours=2), ttl_hours=24)
    assert recs is None

@patch('bgg_recommender.s3')
@patch('builtins.open', new_callable=mock_open)
def test_save_recommendations_to_cache(mock_file, mock_s3):
    bgg_recommender.save_recommendations_to_cache("cache-key", [{"name": "Catan"}])
    mock_s3.upload_file.assert_called_once()
    args, kwargs = mock_s3.upload_file.call_args
    assert args[1] == 'test-bucket'
    assert args[2] == 'cache-key'

@patch('bgg_recommender.s3')
@patch('requests.get')
def test_get_bgg_hotness_fresh_cache(mock_get, mock_s3):
    now = datetime.now(timezone.utc)
    mock_s3.head_object.return_value = {
        'LastModified': now - timedelta(minutes=10)
    }
    with patch('builtins.open', new_callable=mock_open, read_data='[{"id": "1", "rank": 1, "name": "Catan"}]'):
        hot = bgg_recommender.get_bgg_hotness(ttl_hours=2)
        assert hot == [{"id": "1", "rank": 1, "name": "Catan"}]
        mock_get.assert_not_called()

@patch('bgg_recommender.s3')
@patch('requests.get')
def test_get_bgg_hotness_api_call(mock_get, mock_s3):
    # Cache is stale or missing
    mock_s3.head_object.side_effect = ClientError({'Error': {'Code': '404'}}, 'HeadObject')
    
    mock_xml = """<items><item id="12" rank="1"><name value="Catan"/></item></items>"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = mock_xml.encode('utf-8')
    mock_get.return_value = mock_response

    with patch('builtins.open', new_callable=mock_open) as mock_file:
        hot = bgg_recommender.get_bgg_hotness(ttl_hours=2)
        assert len(hot) == 1
        assert hot[0]["id"] == "12"
        assert hot[0]["rank"] == 1
        assert hot[0]["name"] == "Catan"
        mock_get.assert_called_once_with("https://boardgamegeek.com/xmlapi2/hot?type=boardgame", headers={"Authorization": "Bearer test-token"}, timeout=5)

@patch('bgg_recommender.get_user_profile_status')
def test_lambda_handler_missing_username(mock_status):
    response = bgg_recommender.lambda_handler({}, None)
    assert response['statusCode'] == 400
    assert "username query parameter is required" in response['body']

@patch('bgg_recommender.get_user_profile_status')
@patch('bgg_recommender.trigger_background_scrape')
def test_lambda_handler_scraping_status(mock_trigger, mock_status):
    mock_status.return_value = (False, False, None) # user profile doesn't exist
    event = {'queryStringParameters': {'username': 'testuser'}}
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['status'] == 'scraping'
    assert res_body['scraping_users'] == ['testuser']
    mock_trigger.assert_called_once_with('testuser')

@patch('bgg_recommender.get_user_profile_status')
@patch('bgg_recommender.get_cached_recommendations')
def test_lambda_handler_cached_ready(mock_cache, mock_status):
    now = datetime.now(timezone.utc)
    mock_status.return_value = (True, False, now)
    mock_cache.return_value = [{"name": "Gloomhaven", "reason": "Sim"}]
    event = {'queryStringParameters': {'username': 'testuser'}}
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['status'] == 'ready'
    assert res_body['recommendations'] == [{"name": "Gloomhaven", "reason": "Sim"}]

@patch('bgg_recommender.get_user_profile_status')
@patch('bgg_recommender.get_cached_recommendations')
@patch('bgg_recommender.s3')
@patch('pandas.read_parquet')
@patch('bgg_recommender.get_bgg_hotness')
@patch('bgg_recommender.bedrock')
def test_lambda_handler_full_computation(mock_bedrock, mock_hotness, mock_read_parquet, mock_s3, mock_cache, mock_status):
    now = datetime.now(timezone.utc)
    mock_status.return_value = (True, False, now) # profiles are fresh
    mock_cache.return_value = None # cache miss
    
    # Mock user profile DataFrame
    user_df = pd.DataFrame([
        {"id": "100", "username": "testuser", "rating": 9.0, "own": True},
        {"id": "101", "username": "testuser", "rating": 5.0, "own": False}
    ])
    
    # Mock catalog DataFrame
    catalog_df = pd.DataFrame([
        {"id": "100", "name": "Catan", "categories": ["cat1"], "mechanics": ["mech1"], "rating": 8.0, "year_published": 1995, "max_players": 4},
        {"id": "200", "name": "Gloomhaven", "categories": ["cat1"], "mechanics": ["mech2"], "rating": 9.0, "year_published": 2017, "max_players": 4},
        {"id": "300", "name": "Pandemic", "categories": ["cat2"], "mechanics": ["mech1"], "rating": 7.5, "year_published": 2008, "max_players": 4}
    ])
    
    # Side effects for read_parquet calls: first is user profile, second is catalog
    mock_read_parquet.side_effect = [user_df, catalog_df]
    mock_hotness.return_value = []

    # Mock bedrock response
    mock_bedrock_response = {
        'output': {
            'message': {
                'content': [
                    {
                        'text': '{"recommendations": [{"name": "Gloomhaven", "reason": "Because of Catan similarities."}]}'
                    }
                ]
            }
        }
    }
    mock_bedrock.converse.return_value = mock_bedrock_response

    event = {
        'queryStringParameters': {
            'username': 'testuser',
            'own_status': 'unowned',
            'w_mech': '0.8',
            'w_cat': '0.2'
        }
    }
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['status'] == 'ready'
    assert len(res_body['recommendations']) == 1
    assert res_body['recommendations'][0]['name'] == 'Gloomhaven'
    assert res_body['recommendations'][0]['id'] == '200'


@patch('bgg_recommender.get_user_profile_status')
@patch('bgg_recommender.get_cached_recommendations')
@patch('bgg_recommender.s3')
@patch('pandas.read_parquet')
@patch('bgg_recommender.get_bgg_hotness')
@patch('bgg_recommender.bedrock')
def test_lambda_handler_advanced_scoring(mock_bedrock, mock_hotness, mock_read_parquet, mock_s3, mock_cache, mock_status):
    now = datetime.now(timezone.utc)
    mock_status.return_value = (True, False, now)
    mock_cache.return_value = None
    
    # User rated 1 game highly that is high complexity (4.0) by designer "Klaus" and publisher "Kosmos"
    user_df = pd.DataFrame([
        {"id": "100", "username": "testuser", "rating": 9.0, "own": True}
    ])
    
    # Catalog contains:
    # 100 - liked game (high complexity, Kosmos, Klaus)
    # 200 - candidate A (complexity 3.8, similar mechanics, Klaus, Kosmos, recommended for 3 players)
    # 300 - candidate B (complexity 1.5, similar mechanics, other designer/pub, not recommended for 3 players)
    catalog_df = pd.DataFrame([
        {
            "id": "100", "name": "Catan Heavy", "categories": ["cat1"], "mechanics": ["mech1"], "rating": 8.0, 
            "year_published": 1995, "min_players": 2, "max_players": 4, "playing_time": 60, "min_playtime": 45, "max_playtime": 90,
            "complexity": 4.0, "min_age": 12, "thumbnail": "t1", "image": "i1", "designers": ["Klaus"], "publishers": ["Kosmos"],
            "suggested_players_best": ["3"], "suggested_players_recommended": ["3", "4"]
        },
        {
            "id": "200", "name": "Gloomhaven Heavy", "categories": ["cat1"], "mechanics": ["mech1"], "rating": 8.5, 
            "year_published": 2017, "min_players": 1, "max_players": 4, "playing_time": 120, "min_playtime": 60, "max_playtime": 120,
            "complexity": 3.8, "min_age": 14, "thumbnail": "t2", "image": "i2", "designers": ["Klaus"], "publishers": ["Kosmos"],
            "suggested_players_best": ["3"], "suggested_players_recommended": ["3", "4"]
        },
        {
            "id": "300", "name": "Carcassonne Light", "categories": ["cat1"], "mechanics": ["mech1"], "rating": 8.5, 
            "year_published": 2000, "min_players": 2, "max_players": 5, "playing_time": 30, "min_playtime": 30, "max_playtime": 30,
            "complexity": 1.5, "min_age": 8, "thumbnail": "t3", "image": "i3", "designers": ["Wrede"], "publishers": ["Hans"],
            "suggested_players_best": ["2"], "suggested_players_recommended": ["2", "4"]
        }
    ])
    
    mock_read_parquet.side_effect = [user_df, catalog_df]
    mock_hotness.return_value = []
    
    mock_bedrock_response = {
        'output': {
            'message': {
                'content': [
                    {
                        'text': '{"recommendations": [{"name": "Gloomhaven Heavy", "reason": "Because it matches Klaus and complexity preference."}]}'
                    }
                ]
            }
        }
    }
    mock_bedrock.converse.return_value = mock_bedrock_response
    
    event = {
        'queryStringParameters': {
            'username': 'testuser',
            'own_status': 'unowned',
            'player_count': '3',
            'w_mech': '1.0',
            'w_cat': '0.0',
            'w_pop': '0.0',
            'w_hot': '0.0'
        }
    }
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['status'] == 'ready'
    assert len(res_body['recommendations']) == 1
    assert res_body['recommendations'][0]['name'] == 'Gloomhaven Heavy'
    assert res_body['recommendations'][0]['id'] == '200'
    
    mock_bedrock.converse.assert_called_once()
    args, kwargs = mock_bedrock.converse.call_args
    prompt_text = kwargs['messages'][0]['content'][0]['text']
    assert "Complexity: 3.8/5" in prompt_text
    assert "Designers: Klaus" in prompt_text
    assert "Players: 1-4" in prompt_text
    assert "Playtime: 120m" in prompt_text
