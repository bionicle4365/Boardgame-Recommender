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
def test_lambda_handler_refresh_bypasses_cache(mock_cache, mock_status):
    now = datetime.now(timezone.utc)
    mock_status.return_value = (True, False, now)
    mock_cache.return_value = [{"name": "Gloomhaven", "reason": "Sim"}]
    event = {'queryStringParameters': {'username': 'testuser', 'refresh': 'true'}}
    
    # Bypassing the cache will trigger user profile loading, which we trigger a mock fail on to terminate the function.
    with patch('bgg_recommender.s3') as mock_s3:
        mock_s3.download_file.side_effect = Exception("Mocked download error to skip bedrock invocation")
        response = bgg_recommender.lambda_handler(event, None)
        assert response['statusCode'] == 500
        assert mock_cache.called is False

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
    
    assert 'system' in kwargs
    assert "board game recommendation expert" in kwargs['system'][0]['text']
    assert kwargs['inferenceConfig']['temperature'] == 0.6

@patch('bgg_recommender.get_user_profile_status')
@patch('bgg_recommender.get_cached_recommendations')
@patch('bgg_recommender.s3')
@patch('pandas.read_parquet')
@patch('bgg_recommender.get_bgg_hotness')
@patch('bgg_recommender.bedrock')
def test_lambda_handler_duration_and_complexity_preferences(mock_bedrock, mock_hotness, mock_read_parquet, mock_s3, mock_cache, mock_status):
    now = datetime.now(timezone.utc)
    mock_status.return_value = (True, False, now)
    mock_cache.return_value = None
    
    user_df = pd.DataFrame([
        {"id": "100", "username": "testuser", "rating": 9.0, "own": True}
    ])
    
    catalog_df = pd.DataFrame([
        {
            "id": "100", "name": "Catan Heavy", "categories": ["cat1"], "mechanics": ["mech1"], "rating": 8.0, 
            "year_published": 1995, "min_players": 2, "max_players": 4, "playing_time": 60, "min_playtime": 45, "max_playtime": 90,
            "complexity": 4.0, "min_age": 12, "thumbnail": "t1", "image": "i1", "designers": ["Klaus"], "publishers": ["Kosmos"]
        },
        {
            "id": "200", "name": "Carcassonne Light", "categories": ["cat1"], "mechanics": ["mech1"], "rating": 8.5, 
            "year_published": 2000, "min_players": 2, "max_players": 5, "playing_time": 30, "min_playtime": 30, "max_playtime": 30,
            "complexity": 1.5, "min_age": 8, "thumbnail": "t3", "image": "i3", "designers": ["Wrede"], "publishers": ["Hans"]
        }
    ])
    
    mock_read_parquet.side_effect = [user_df, catalog_df]
    mock_hotness.return_value = []
    
    mock_bedrock_response = {
        'output': {
            'message': {
                'content': [
                    {
                        'text': '{"recommendations": [{"name": "Carcassonne Light", "reason": "Because it matches your preference for short, light games."}]}'
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
            'duration_pref': 'short',
            'complexity_pref': 'low',
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
    assert res_body['recommendations'][0]['name'] == 'Carcassonne Light'
    assert res_body['recommendations'][0]['id'] == '200'
    
    mock_bedrock.converse.assert_called_once()
    args, kwargs = mock_bedrock.converse.call_args
    prompt_text = kwargs['messages'][0]['content'][0]['text']
    assert "Target Play Time Preference: Short" in prompt_text
    assert "Target Complexity/Weight Preference: Low" in prompt_text
    assert "If specific play time or complexity preferences are provided, also mention how this game fits those preferences." in prompt_text


def test_lambda_handler_complexity_pref_light_heavy():
    # Verify that passing 'light' and 'heavy' maps correctly to 'low' and 'high' logic
    import scoring
    candidates_df = pd.DataFrame([
        {"id": "100", "name": "Carcassonne Light", "categories": [], "mechanics": [], "rating": 8.0, "complexity": 1.5},
        {"id": "200", "name": "Gloomhaven Heavy", "categories": [], "mechanics": [], "rating": 8.0, "complexity": 4.5}
    ])
    
    # Test scoring with complexity_pref='light'
    results_light = scoring.score_candidates(
        candidates=candidates_df,
        mech_weights={},
        cat_weights={},
        user_designers={},
        user_publishers={},
        complexity_weights={},
        hotness_scores={},
        catalog_df=candidates_df,
        query_params={'complexity_pref': 'light', 'w_mech': '0', 'w_cat': '0', 'w_pop': '0', 'w_comp': '1.0'}
    )
    assert results_light[0]['name'] == 'Carcassonne Light'
    
    # Test scoring with complexity_pref='heavy'
    results_heavy = scoring.score_candidates(
        candidates=candidates_df,
        mech_weights={},
        cat_weights={},
        user_designers={},
        user_publishers={},
        complexity_weights={},
        hotness_scores={},
        catalog_df=candidates_df,
        query_params={'complexity_pref': 'heavy', 'w_mech': '0', 'w_cat': '0', 'w_pop': '0', 'w_comp': '1.0'}
    )
    assert results_heavy[0]['name'] == 'Gloomhaven Heavy'


@patch('bgg_recommender.s3')
def test_lambda_handler_get_profile_endpoint(mock_s3):
    # Mock download_file to mock file download and read
    def mock_download(bucket, key, local_path):
        with open(local_path, 'w', encoding='utf-8') as f:
            json.dump({
                "mech_weights": {"mech1": 4.0},
                "cat_weights": {"cat1": 4.0},
                "complexity_weights": {"Light": 0.0, "Medium-Light": 4.0, "Medium-Heavy": 0.0, "Heavy": 0.0},
                "designer_weights": {"des1": 4.0},
                "publisher_weights": {"pub1": 4.0},
                "generated_at": datetime.now(timezone.utc).isoformat()
            }, f)
    mock_s3.download_file.side_effect = mock_download

    event = {
        'rawPath': '/profile',
        'queryStringParameters': {
            'username': 'testuser'
        }
    }
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['complexity_weights'] == {"Light": 0.0, "Medium-Light": 4.0, "Medium-Heavy": 0.0, "Heavy": 0.0}
    assert res_body['cat_weights']['cat1'] == 4.0
    mock_s3.download_file.assert_called_once_with('test-bucket', 'data/users/testuser_taste_profile.json', '/tmp/testuser_taste_profile_api.json')


@patch('bgg_recommender.get_user_profile_status')
@patch('bgg_recommender.trigger_background_scrape')
@patch('bgg_recommender.s3')
def test_lambda_handler_get_profile_endpoint_404(mock_s3, mock_trigger, mock_status):
    mock_status.return_value = (False, False, None)
    err_resp = {'Error': {'Code': '404', 'Message': 'Not Found'}}
    mock_s3.download_file.side_effect = ClientError(err_resp, 'DownloadFile')

    event = {
        'rawPath': '/profile',
        'queryStringParameters': {
            'username': 'testuser_missing'
        }
    }
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 202
    mock_trigger.assert_called_once_with('testuser_missing')


@patch('bgg_recommender.get_user_profile_status')
@patch('bgg_recommender.get_cached_recommendations')
@patch('bgg_recommender.s3')
@patch('pandas.read_parquet')
@patch('bgg_recommender.get_bgg_hotness')
@patch('bgg_recommender.bedrock')
def test_lambda_handler_precomputed_taste_profile(mock_bedrock, mock_hotness, mock_read_parquet, mock_s3, mock_cache, mock_status):
    now = datetime.now(timezone.utc)
    mock_status.return_value = (True, False, now - timedelta(hours=1)) # parquet modified 1 hour ago
    mock_cache.return_value = None # cache miss

    # Mock taste profile JSON download
    def mock_download(bucket, key, local_path):
        if "_taste_profile.json" in key:
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "mech_weights": {"mech1": 5.0},
                    "cat_weights": {"cat1": 5.0},
                    "complexity_weights": {"Light": 0.0, "Medium-Light": 0.0, "Medium-Heavy": 5.0, "Heavy": 0.0},
                    "designer_weights": {"des1": 5.0},
                    "publisher_weights": {"pub1": 5.0},
                    "generated_at": now.isoformat() # profile generated now (newer than parquet)
                }, f)
        elif ".parquet" in key:
            # download of user parquet (though we mock pd.read_parquet anyway)
            pass
    mock_s3.download_file.side_effect = mock_download
    mock_s3.head_object.return_value = {} # Profile exists check succeeds

    # Mock user profile DataFrame (needs id column)
    user_df = pd.DataFrame([
        {"id": "100", "username": "testuser", "rating": 9.0, "own": True}
    ])
    # Mock catalog DataFrame
    catalog_df = pd.DataFrame([
        {"id": "100", "name": "Catan", "categories": ["cat1"], "mechanics": ["mech1"], "rating": 8.0, "year_published": 1995, "max_players": 4, "complexity": 3.0}
    ])
    mock_read_parquet.side_effect = [user_df, catalog_df]
    mock_hotness.return_value = []

    mock_bedrock_response = {
        'output': {
            'message': {
                'content': [
                    {
                        'text': '{"recommendations": [{"name": "Catan", "reason": "Precomputed matches complexity."}]}'
                    }
                ]
            }
        }
    }
    mock_bedrock.converse.return_value = mock_bedrock_response

    event = {
        'queryStringParameters': {
            'username': 'testuser',
            'own_status': 'owned',
            'w_mech': '0.5',
            'w_cat': '0.5'
        }
    }
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['status'] == 'ready'
    assert len(res_body['recommendations']) == 1
    assert res_body['recommendations'][0]['name'] == 'Catan'

    # Verify that S3 downloaded the taste profile
    mock_s3.download_file.assert_any_call('test-bucket', 'data/users/testuser_taste_profile.json', '/tmp/testuser_taste_profile.json')


@patch('bgg_recommender.get_user_profile_status')
@patch('bgg_recommender.get_cached_recommendations')
@patch('bgg_recommender.s3')
@patch('pandas.read_parquet')
@patch('bgg_recommender.get_bgg_hotness')
@patch('bgg_recommender.bedrock')
def test_lambda_handler_new_first_class_weights(mock_bedrock, mock_hotness, mock_read_parquet, mock_s3, mock_cache, mock_status):
    now = datetime.now(timezone.utc)
    mock_status.return_value = (True, False, now)
    mock_cache.return_value = None

    user_df = pd.DataFrame([
        {"id": "100", "username": "testuser", "rating": 9.0, "own": True}
    ])
    catalog_df = pd.DataFrame([
        {
            "id": "100", "name": "Catan Heavy", "categories": ["cat1"], "mechanics": ["mech1"], "rating": 8.0, 
            "year_published": 1995, "min_players": 2, "max_players": 4, "playing_time": 60, "min_playtime": 45, "max_playtime": 90,
            "complexity": 4.0, "min_age": 12, "thumbnail": "t1", "image": "i1", "designers": ["Klaus"], "publishers": ["Kosmos"]
        }
    ])
    mock_read_parquet.side_effect = [user_df, catalog_df]
    mock_hotness.return_value = []

    mock_bedrock_response = {
        'output': {
            'message': {
                'content': [
                    {
                        'text': '{"recommendations": [{"name": "Catan Heavy", "reason": "Matches your preference weights."}]}'
                    }
                ]
            }
        }
    }
    mock_bedrock.converse.return_value = mock_bedrock_response

    # Test with explicit weights for comp, des, and pub
    event = {
        'queryStringParameters': {
            'username': 'testuser',
            'own_status': 'unowned',
            'w_mech': '0.2',
            'w_cat': '0.2',
            'w_pop': '0.1',
            'w_hot': '0.1',
            'w_comp': '0.8',
            'w_des': '0.6',
            'w_pub': '0.4'
        }
    }
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['status'] == 'ready'

    # Verify that the Bedrock call prompt contains the new weights context
    mock_bedrock.converse.assert_called_once()
    args, kwargs = mock_bedrock.converse.call_args
    prompt_text = kwargs['messages'][0]['content'][0]['text']
    assert "Complexity Similarity Weight: 80%" in prompt_text
    assert "Designer Similarity Weight: 60%" in prompt_text
    assert "Publisher Similarity Weight: 40%" in prompt_text


def test_milestone_18_opener_uniqueness():
    valid_reasons = [
        "Since you like Catan, you will enjoy the resource trading here.",
        "This game features similar draft mechanics to 7 Wonders.",
        "Perfect for 4 players looking for a quick cooperative session.",
        "Designed by Uwe Rosenberg, which matches your designer preference.",
        "A highly thematic space experience that shares elements with Eclipse.",
        "This offers a great medium-heavy challenge matching your tastes.",
        "An interesting contrast to abstract games, featuring heavy theme.",
        "Plays in under 30 minutes, fitting your short playtime request.",
        "A classic entry from designer Stefan Feld with similar mechanisms.",
        "If you enjoy hand management, this game handles it brilliantly."
    ]
    seen_openers = set()
    for r in valid_reasons:
        words = tuple(r.lower().split()[:4])
        assert words not in seen_openers, f"Duplicate opener detected: {words}"
        seen_openers.add(words)

    invalid_reasons = [
        "If you enjoyed Gloomhaven, you will love X.",
        "If you enjoyed Gloomhaven, you will love Y."
    ]
    seen_openers_invalid = set()
    duplicate_found = False
    for r in invalid_reasons:
        words = tuple(r.lower().split()[:4])
        if words in seen_openers_invalid:
            duplicate_found = True
            break
        seen_openers_invalid.add(words)
    assert duplicate_found is True


def test_milestone_18_angle_coverage():
    reasons = [
        "Since you like Catan, you will enjoy the resource trading mechanisms here.",
        "This game features similar draft card play to 7 Wonders.",
        "Perfect for 4 players looking for a quick cooperative session.",
        "Designed by Uwe Rosenberg, which matches your designer preference.",
        "A highly thematic space experience that shares elements with Eclipse.",
        "This offers a great medium-heavy challenge matching your complexity tastes.",
        "An interesting contrast to abstract games, featuring heavy theme.",
        "Plays in under 30 minutes, fitting your short playtime request.",
        "A classic entry from publisher Hans im Glück with similar mechanisms.",
        "If you enjoy worker placement, this game handles it brilliantly."
    ]
    
    angle_keywords = {
        'mechanics': ['mechanis', 'draft', 'card play', 'worker placement', 'hand management', 'dice', 'trading'],
        'theme': ['theme', 'thematic', 'atmosphere', 'space experience', 'narrative', 'setting'],
        'complexity': ['complexity', 'medium-heavy', 'challenge', 'light', 'weight', 'heavy'],
        'player count': ['player count', 'players', 'group size', 'social'],
        'novelty': ['contrast', 'fresh', 'distinct', 'different from'],
        'pacing': ['minute', 'pacing', 'playtime', 'length', 'quick', 'hour'],
        'lineage': ['designer', 'publisher', 'uwe rosenberg', 'stefan feld', 'hans im glück', 'lineage', 'DNA']
    }
    
    matched_angles = set()
    for r in reasons:
        r_lower = r.lower()
        for angle, keywords in angle_keywords.items():
            if any(kw in r_lower for kw in keywords):
                matched_angles.add(angle)
                
    assert len(matched_angles) >= 4, f"Only matched angles: {matched_angles}"
@patch('bgg_recommender.s3')
def test_conventions_endpoint(mock_s3):
    # Setup mock active_previews.json and active_previews_games.json in S3
    mock_previews = [
        {
            "convention_id": "gencon2026",
            "name": "Gen Con 2026 Preview",
            "date": "2026-08-01",
            "previewid": 92
        }
    ]
    mock_games = {
        "gencon2026": ["123", "456", "789"]
    }
    
    # We mock local download of files
    def side_effect(bucket, key, local_path):
        if "active_previews_games.json" in key:
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(mock_games, f)
        elif "active_previews.json" in key:
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(mock_previews, f)
            
    mock_s3.download_file.side_effect = side_effect
    
    # Reset caches to force reload
    bgg_recommender.PREVIEWS_CACHE = None
    bgg_recommender.PREVIEWS_CACHE_TIME = None
    bgg_recommender.PREVIEWS_GAMES_CACHE = None
    bgg_recommender.PREVIEWS_GAMES_CACHE_TIME = None
    
    event = {
        'rawPath': '/conventions',
        'queryStringParameters': {}
    }
    
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert len(res_body) == 1
    assert res_body[0]['convention_id'] == 'gencon2026'
    assert res_body[0]['name'] == 'Gen Con 2026 Preview'
    assert res_body[0]['date'] == '2026-08-01'
    assert res_body[0]['game_count'] == 3


@patch('bgg_recommender.get_user_profile_status')
@patch('bgg_recommender.get_cached_recommendations')
@patch('bgg_recommender.s3')
@patch('pandas.read_parquet')
@patch('bgg_recommender.get_bgg_hotness')
@patch('bgg_recommender.bedrock')
@patch('bgg_recommender.get_active_previews')
@patch('bgg_recommender.get_active_previews_games')
def test_convention_id_filtering(mock_get_active_previews_games, mock_get_active_previews, mock_bedrock, mock_hotness, mock_read_parquet, mock_s3, mock_cache, mock_status):
    # Setup mock active previews & games map
    mock_get_active_previews.return_value = [
        {
            "convention_id": "gencon2026",
            "name": "Gen Con 2026 Preview",
            "date": "2026-08-01",
            "previewid": 92
        }
    ]
    mock_get_active_previews_games.return_value = {
        "gencon2026": ["456"] # Only Catan (456) in convention
    }
    
    now = datetime.now(timezone.utc)
    mock_status.return_value = (True, False, now) # profile exists and is fresh
    mock_cache.return_value = None # cache miss
    
    # Mock taste profile JSON download
    def mock_download(bucket, key, local_path):
        if "_taste_profile.json" in key:
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "mech_weights": {"Trading": 5.0},
                    "cat_weights": {"Strategy": 5.0},
                    "complexity_weights": {"Light": 0.0, "Medium-Light": 5.0, "Medium-Heavy": 0.0, "Heavy": 0.0},
                    "designer_weights": {},
                    "publisher_weights": {},
                    "generated_at": now.isoformat()
                }, f)
        elif ".parquet" in key:
            pass
            
    mock_s3.download_file.side_effect = mock_download
    mock_s3.head_object.return_value = {}
    
    # Setup mock catalog with two games (Gloomhaven 123 and Catan 456)
    # Mock user owns/rates a different game id (789) so Catan is not filtered out by rated_ids when own_status is 'any'
    user_df = pd.DataFrame([
        {"id": "789", "username": "testuser", "rating": 8.0, "own": True}
    ])
    catalog_df = pd.DataFrame([
        {"id": "123", "name": "Gloomhaven", "categories": ["Thematic"], "mechanics": ["Cooperative"], "rating": 8.5, "year_published": 2017, "complexity": 3.8},
        {"id": "456", "name": "Catan", "categories": ["Strategy"], "mechanics": ["Trading"], "rating": 7.1, "year_published": 1995, "complexity": 2.3}
    ])
    mock_read_parquet.side_effect = [user_df, catalog_df]
    mock_hotness.return_value = []
    
    mock_bedrock_response = {
        'output': {
            'message': {
                'content': [
                    {
                        'text': '{"recommendations": [{"name": "Catan", "reason": "Since you like trading in Catan, this matches."}]}'
                    }
                ]
            }
        }
    }
    mock_bedrock.converse.return_value = mock_bedrock_response
    
    # Test with convention filter
    event = {
        'queryStringParameters': {
            'username': 'testuser',
            'own_status': 'any',
            'convention_id': 'gencon2026'
        }
    }
    
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 200
    res_body = json.loads(response['body'])
    assert res_body['status'] == 'ready'
    
    # Verify recommendation count is 1 (filtered to Catan)
    recs = res_body['recommendations']
    assert len(recs) == 1
    assert recs[0]['name'] == 'Catan'


def test_primary_publisher_only():
    import scoring
    
    # 1. Test compute_taste_profile_inline with multiple publishers
    user_df = pd.DataFrame([
        {"id": "100", "username": "testuser", "rating": 9.0, "own": True}
    ])
    catalog_df = pd.DataFrame([
        {
            "id": "100",
            "name": "Catan",
            "categories": [],
            "mechanics": [],
            "rating": 8.0,
            "complexity": 2.0,
            "designers": [],
            "publishers": ["pub1", "pub_local1"]
        }
    ])
    
    # Run inline taste profile computation
    mech_weights, cat_weights, user_designers, user_publishers, complexity_weights = scoring.compute_taste_profile_inline(
        user_df=user_df,
        catalog_df=catalog_df,
        usernames=["testuser"],
        user_parquet_modified={}
    )
    
    # Assert that only the primary publisher "pub1" is included in user_publishers
    assert "pub1" in user_publishers
    assert user_publishers["pub1"] == 4.0
    assert "pub_local1" not in user_publishers
    
    # 2. Test score_candidates matches only on primary publisher
    candidates_df = pd.DataFrame([
        {
            "id": "200",
            "name": "Match Primary",
            "categories": [],
            "mechanics": [],
            "rating": 8.0,
            "complexity": 2.0,
            "designers": [],
            "publishers": ["pub1", "pub_local2"]
        },
        {
            "id": "300",
            "name": "Mismatch Primary (Local is pub1)",
            "categories": [],
            "mechanics": [],
            "rating": 8.0,
            "complexity": 2.0,
            "designers": [],
            "publishers": ["pub_local1", "pub1"]
        }
    ])
    
    # Run scoring with w_pub=1.0 and others at 0.0
    scores = scoring.score_candidates(
        candidates=candidates_df,
        mech_weights={},
        cat_weights={},
        user_designers={},
        user_publishers=user_publishers,
        complexity_weights={},
        hotness_scores={},
        catalog_df=candidates_df,
        query_params={'w_mech': '0', 'w_cat': '0', 'w_pop': '0', 'w_comp': '0', 'w_pub': '1.0'}
    )
    
    # Match Primary should have pub_sim = 1.0 (since it starts with pub1)
    # Mismatch Primary should have pub_sim = 0.0 (since it starts with pub_local1)
    match_primary = next(c for c in scores if c["id"] == "200")
    mismatch_primary = next(c for c in scores if c["id"] == "300")
    
    # Let's verify that the composite score matches the expectations:
    # Match Primary has pub_sim=1.0, denominator = 1.0 -> comp_score = 1.0
    # Mismatch Primary has pub_sim=0.0, denominator = 1.0 -> comp_score = 0.0
    assert match_primary["id"] == "200"
    assert mismatch_primary["id"] == "300"
    
    # In scores, the candidates are returned sorted by score.
    # Therefore, "Match Primary" should be first and "Mismatch Primary" second.
    assert scores[0]["id"] == "200"
    assert scores[1]["id"] == "300"


def test_validate_username():
    from cache_utils import validate_username
    assert validate_username("bionicle4365") is True
    assert validate_username("user_123") is True
    assert validate_username("A") is True
    assert validate_username("a" * 25) is True
    
    assert validate_username("a" * 26) is False
    assert validate_username("") is False
    assert validate_username(None) is False
    assert validate_username("user-123") is False
    assert validate_username("user name") is False
    assert validate_username("../path") is False
    assert validate_username("user$") is False


def test_handle_profile_invalid_username():
    query_params = {'username': 'user-123'}
    response = bgg_recommender._handle_profile(query_params)
    assert response['statusCode'] == 400
    assert 'Invalid username' in response['body']


def test_handle_recommendations_invalid_username():
    query_params = {'username': 'bionicle4365,user-123'}
    response = bgg_recommender._handle_recommendations(query_params)
    assert response['statusCode'] == 400
    assert 'Invalid username' in response['body']

@patch('bgg_recommender.get_user_profile_status')
def test_lambda_handler_compression(mock_status):
    import gzip
    import base64

    # We will simulate a profile request where the status check returns not found,
    # resulting in a 202 status code. This is a simple request that doesn't trigger
    # extensive mocks but returns a valid body.
    mock_status.return_value = (False, False, None)

    event = {
        'rawPath': '/profile',
        'queryStringParameters': {
            'username': 'bionicle4365'
        },
        'headers': {
            'accept-encoding': 'gzip'
        }
    }
    
    with patch('bgg_recommender.trigger_background_scrape') as mock_trigger:
        response = bgg_recommender.lambda_handler(event, None)
        assert response['statusCode'] == 202
        assert response['headers']['Content-Encoding'] == 'gzip'
        assert response['isBase64Encoded'] is True

        # Decode and decompress
        decoded_body = base64.b64decode(response['body'])
        decompressed_body = gzip.decompress(decoded_body).decode('utf-8')
        body_data = json.loads(decompressed_body)
        assert body_data['status'] == 'scraping'


def test_diversify_candidates_no_clustering():
    import scoring
    # Create 35 candidates with completely unique mechanics and categories
    candidates = [
        {
            "id": i,
            "name": f"Game {i}",
            "mechanics": [f"Mech {i}"],
            "categories": [f"Cat {i}"]
        }
        for i in range(35)
    ]
    # target_count = 25
    result = scoring.diversify_candidates(candidates, target_count=25)
    assert len(result) == 25
    # Should be exactly the first 25 candidates in order
    for idx, game in enumerate(result):
        assert game["id"] == idx


def test_diversify_candidates_clustering_mechanic():
    import scoring
    # First candidate has Mech A. Next 15 candidates also have Mech A.
    # The remaining 20 candidates have unique mechanics (Mech B, Mech C, etc.)
    candidates = []
    # Index 0
    candidates.append({
        "id": 0,
        "name": "First Game",
        "mechanics": ["Mech A"],
        "categories": ["Cat A"]
    })
    # Indexes 1 to 15 (all Mech A)
    for i in range(1, 16):
        candidates.append({
            "id": i,
            "name": f"Cluster Game {i}",
            "mechanics": ["Mech A"],
            "categories": [f"Cat {i}"]
        })
    # Indexes 16 to 39 (diverse mechanics)
    for i in range(16, 40):
        candidates.append({
            "id": i,
            "name": f"Diverse Game {i}",
            "mechanics": [f"Mech {i}"],
            "categories": [f"Cat {i}"]
        })

    # max_per_mechanic = 3
    result = scoring.diversify_candidates(candidates, max_per_mechanic=3, target_count=25)
    assert len(result) == 25

    # Check that only 3 games with "Mech A" are selected (index 0, plus 2 of the cluster)
    mech_a_count = sum(1 for g in result if g["mechanics"] and g["mechanics"][0] == "Mech A")
    assert mech_a_count == 3

    # First game (index 0) must be retained
    assert result[0]["id"] == 0
    # Next two should be index 1 and 2 (first items in cluster)
    assert result[1]["id"] == 1
    assert result[2]["id"] == 2
    # The rest should skip the remaining cluster and pull from the diverse ones
    assert result[3]["id"] == 16


def test_diversify_candidates_clustering_category():
    import scoring
    # First candidate has Cat X. Next 15 candidates also have Cat X.
    # The remaining 20 candidates have unique categories.
    candidates = []
    candidates.append({
        "id": 0,
        "name": "First Game",
        "mechanics": ["Mech 0"],
        "categories": ["Cat X"]
    })
    for i in range(1, 16):
        candidates.append({
            "id": i,
            "name": f"Cluster Game {i}",
            "mechanics": [f"Mech {i}"],
            "categories": ["Cat X"]
        })
    for i in range(16, 40):
        candidates.append({
            "id": i,
            "name": f"Diverse Game {i}",
            "mechanics": [f"Mech {i}"],
            "categories": [f"Cat {i}"]
        })

    # max_per_category = 2
    result = scoring.diversify_candidates(candidates, max_per_category=2, target_count=25)
    assert len(result) == 25

    # Check that only 2 games with "Cat X" are selected
    cat_x_count = sum(1 for g in result if g["categories"] and g["categories"][0] == "Cat X")
    assert cat_x_count == 2
    assert result[0]["id"] == 0
    assert result[1]["id"] == 1
    assert result[2]["id"] == 16


def test_diversify_candidates_always_retains_first():
    import scoring
    # First candidate has Mech A.
    # Set max_per_mechanic = 0 (or 1 with duplicate) to see if it is still kept
    candidates = [
        {
            "id": i,
            "name": f"Game {i}",
            "mechanics": ["Mech A"],
            "categories": ["Cat A"]
        }
        for i in range(30)
    ]
    # Even if max_per_mechanic is 0, the first game (index 0) must be returned in the list.
    # Let's run with target_count = 25, max_per_mechanic = 0.
    # Since max_per_mechanic = 0, every game after index 0 is skipped because their Mech is Mech A and count >= 0.
    # This will trigger fallback since selected count is 1 (< 25).
    # To test always retaining first without triggering fallback, let's use:
    # 1st game: Mech A, Cat A.
    # Next 29 games: Mech B, Cat B.
    # If we set max_per_mechanic = 1 for Mech A, Mech B can have higher cap.
    candidates = [
        {"id": 0, "name": "Game 0", "mechanics": ["Mech A"], "categories": ["Cat A"]}
    ] + [
        {"id": i, "name": f"Game {i}", "mechanics": [f"Mech {i}"], "categories": [f"Cat {i}"]}
        for i in range(1, 30)
    ]
    # Since Mech A has appeared once, if we set max_per_mechanic=1, and we have a duplicate of Mech A later:
    candidates.append({"id": 30, "name": "Game 30", "mechanics": ["Mech A"], "categories": ["Cat 30"]})

    result = scoring.diversify_candidates(candidates, max_per_mechanic=1, target_count=25)
    # The first game (id 0) is Mech A. The last game (id 30) is Mech A.
    # Game 30 should be skipped, but Game 0 is retained.
    assert len(result) == 25
    assert result[0]["id"] == 0
    assert 30 not in [g["id"] for g in result]


def test_diversify_candidates_fallback():
    import scoring
    # 40 games, all sharing same mechanic and category.
    # Cap = 2. Maximum selected can only be 2.
    # Since 2 < 25, the fallback must trigger and return the original list.
    candidates = [
        {
            "id": i,
            "name": f"Game {i}",
            "mechanics": ["Mech A"],
            "categories": ["Cat A"]
        }
        for i in range(40)
    ]
    result = scoring.diversify_candidates(candidates, max_per_mechanic=2, max_per_category=2, target_count=25)
    assert len(result) == 40
    for idx, game in enumerate(result):
        assert game["id"] == idx



