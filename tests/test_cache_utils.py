import os
import sys
import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, mock_open
import pytest
import pandas as pd
import numpy as np
from botocore.exceptions import ClientError

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

# Add bgg_recommender directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_recommender'))
import cache_utils
import bgg_recommender

@pytest.fixture(autouse=True)
def reset_globals():
    # Reset in-memory cache attributes in bgg_recommender module before each test
    bgg_recommender.CATALOG_CACHE = None
    bgg_recommender.PREVIEWS_CACHE = None
    bgg_recommender.PREVIEWS_CACHE_TIME = None
    bgg_recommender.PREVIEWS_GAMES_CACHE = None
    bgg_recommender.PREVIEWS_GAMES_CACHE_TIME = None
    yield

def test_safe_list():
    assert cache_utils.safe_list([1, 2, 3]) == [1, 2, 3]
    assert cache_utils.safe_list(np.array([4, 5])) == [4, 5]
    assert cache_utils.safe_list(None) == []
    assert cache_utils.safe_list("not-a-list") == []

def test_build_game_metadata():
    row = {
        'id': '100',
        'name': 'Sample Game',
        'year_published': 2020,
        'min_players': 2,
        'max_players': 4,
        'playing_time': 60,
        'min_playtime': 45,
        'max_playtime': 90,
        'min_age': 10,
        'rating': 7.8,
        'complexity': 2.5,
        'thumbnail': 'thumb.jpg',
        'image': 'image.jpg'
    }
    metadata = cache_utils.build_game_metadata(row)
    assert metadata['id'] == '100'
    assert metadata['name'] == 'Sample Game'
    assert metadata['year_published'] == 2020
    assert metadata['rating'] == 7.8
    assert metadata['complexity'] == 2.5
    assert metadata['thumbnail'] == 'thumb.jpg'

    # Test with NaN / null values
    row_nulls = {
        'id': 200,
        'name': 'Null Game',
        'year_published': np.nan,
        'min_players': None,
        'max_players': None,
        'playing_time': np.nan,
        'min_playtime': np.nan,
        'max_playtime': np.nan,
        'min_age': np.nan,
        'rating': np.nan,
        'complexity': np.nan,
        'thumbnail': None,
        'image': None
    }
    metadata_nulls = cache_utils.build_game_metadata(row_nulls)
    assert metadata_nulls['id'] == '200'
    assert metadata_nulls['year_published'] is None
    assert metadata_nulls['min_players'] is None
    assert metadata_nulls['rating'] is None
    assert metadata_nulls['thumbnail'] is None

@patch('cache_utils._default_s3')
def test_get_active_previews_games_cache_hit(mock_s3):
    # Setup in-memory cache
    bgg_recommender.PREVIEWS_GAMES_CACHE = {"conv1": ["game1", "game2"]}
    bgg_recommender.PREVIEWS_GAMES_CACHE_TIME = time.time()

    res = cache_utils.get_active_previews_games()
    assert res == {"conv1": ["game1", "game2"]}
    mock_s3.download_file.assert_not_called()

@patch('cache_utils._default_s3')
@patch('builtins.open', new_callable=mock_open, read_data='{"conv1": ["game1"]}')
def test_get_active_previews_games_cache_miss(mock_file, mock_s3):
    res = cache_utils.get_active_previews_games()
    assert res == {"conv1": ["game1"]}
    mock_s3.download_file.assert_called_once_with('test-bucket', 'data/active_previews_games.json', '/tmp/active_previews_games.json')

@patch('cache_utils._default_s3')
def test_get_active_previews_games_failure(mock_s3):
    mock_s3.download_file.side_effect = Exception("S3 error")
    res = cache_utils.get_active_previews_games()
    assert res == {}

@patch('cache_utils._default_s3')
def test_get_active_previews_cache_hit(mock_s3):
    bgg_recommender.PREVIEWS_CACHE = [{"convention_id": "c1"}]
    bgg_recommender.PREVIEWS_CACHE_TIME = time.time()

    res = cache_utils.get_active_previews()
    assert res == [{"convention_id": "c1"}]
    mock_s3.download_file.assert_not_called()

@patch('cache_utils._default_s3')
@patch('builtins.open', new_callable=mock_open, read_data='[{"convention_id": "c2"}]')
def test_get_active_previews_cache_miss(mock_file, mock_s3):
    res = cache_utils.get_active_previews()
    assert res == [{"convention_id": "c2"}]
    mock_s3.download_file.assert_called_once_with('test-bucket', 'data/active_previews.json', '/tmp/active_previews.json')

@patch('cache_utils._default_s3')
def test_get_active_previews_failure(mock_s3):
    mock_s3.download_file.side_effect = Exception("S3 error")
    res = cache_utils.get_active_previews()
    assert res == []

@patch('cache_utils._default_s3')
@patch('pandas.read_parquet')
def test_get_catalog_success(mock_read_parquet, mock_s3):
    mock_df = pd.DataFrame([{"id": "1", "name": "Catan"}])
    mock_read_parquet.return_value = mock_df

    df = cache_utils.get_catalog()
    assert df is not None
    assert len(df) == 1
    mock_s3.download_file.assert_called_once_with('test-bucket', 'data/boardgames_combined/catalog.parquet', '/tmp/catalog.parquet')

    # cache hit
    mock_s3.reset_mock()
    df2 = cache_utils.get_catalog()
    assert df2 is df
    mock_s3.download_file.assert_not_called()

@patch('cache_utils._default_s3')
def test_get_catalog_failure(mock_s3):
    mock_s3.download_file.side_effect = Exception("S3 download error")
    df = cache_utils.get_catalog()
    assert df is None

@patch('cache_utils._default_s3')
def test_get_user_profile_status_exists(mock_s3):
    now = datetime.now(timezone.utc)
    mock_s3.head_object.return_value = {
        'LastModified': now - timedelta(hours=5)
    }
    exists, is_stale, modified = cache_utils.get_user_profile_status("user1", ttl_hours=24)
    assert exists is True
    assert is_stale is False
    assert modified == now - timedelta(hours=5)

    exists, is_stale, modified = cache_utils.get_user_profile_status("user1", ttl_hours=2)
    assert exists is True
    assert is_stale is True

@patch('cache_utils._default_s3')
def test_get_user_profile_status_missing(mock_s3):
    err_resp = {'Error': {'Code': '404', 'Message': 'Not Found'}}
    mock_s3.head_object.side_effect = ClientError(err_resp, 'HeadObject')
    exists, is_stale, modified = cache_utils.get_user_profile_status("user1")
    assert exists is False
    assert is_stale is False
    assert modified is None

@patch('cache_utils._default_s3')
def test_get_user_profile_status_other_error(mock_s3):
    err_resp = {'Error': {'Code': '500', 'Message': 'Internal Error'}}
    mock_s3.head_object.side_effect = ClientError(err_resp, 'HeadObject')
    with pytest.raises(ClientError):
        cache_utils.get_user_profile_status("user1")

@patch('cache_utils._default_sqs')
def test_trigger_background_scrape_success(mock_sqs):
    with patch('cache_utils.user_sqs_queue_url', 'https://sqs.test.com'):
        cache_utils.trigger_background_scrape("user1")
        mock_sqs.send_message.assert_called_once_with(
            QueueUrl='https://sqs.test.com',
            MessageBody='user1'
        )

@patch('cache_utils._default_sqs')
def test_trigger_background_scrape_no_url(mock_sqs):
    with patch('cache_utils.user_sqs_queue_url', None):
        cache_utils.trigger_background_scrape("user1")
        mock_sqs.send_message.assert_not_called()

@patch('cache_utils._default_sqs')
def test_trigger_background_scrape_error(mock_sqs):
    with patch('cache_utils.user_sqs_queue_url', 'https://sqs.test.com'):
        mock_sqs.send_message.side_effect = Exception("SQS send error")
        # should log error and not raise exception
        cache_utils.trigger_background_scrape("user1")
        mock_sqs.send_message.assert_called_once()

@patch('cache_utils._default_s3')
@patch('builtins.open', new_callable=mock_open, read_data='[{"name": "Catan"}]')
def test_get_cached_recommendations_fresh(mock_file, mock_s3):
    now = datetime.now(timezone.utc)
    mock_s3.head_object.return_value = {
        'LastModified': now - timedelta(hours=2)
    }
    recs = cache_utils.get_cached_recommendations("cache-key", now - timedelta(hours=4), ttl_hours=24)
    assert recs == [{"name": "Catan"}]

@patch('cache_utils._default_s3')
def test_get_cached_recommendations_stale(mock_s3):
    now = datetime.now(timezone.utc)
    mock_s3.head_object.return_value = {
        'LastModified': now - timedelta(hours=25)
    }
    recs = cache_utils.get_cached_recommendations("cache-key", now - timedelta(hours=30), ttl_hours=24)
    assert recs is None

@patch('cache_utils._default_s3')
def test_get_cached_recommendations_invalidated(mock_s3):
    now = datetime.now(timezone.utc)
    mock_s3.head_object.return_value = {
        'LastModified': now - timedelta(hours=5)
    }
    # profile modified at now-2h, cache modified at now-5h -> invalidated
    recs = cache_utils.get_cached_recommendations("cache-key", now - timedelta(hours=2), ttl_hours=24)
    assert recs is None

@patch('cache_utils._default_s3')
def test_get_cached_recommendations_miss(mock_s3):
    err_resp = {'Error': {'Code': '404', 'Message': 'Not Found'}}
    mock_s3.head_object.side_effect = ClientError(err_resp, 'HeadObject')
    recs = cache_utils.get_cached_recommendations("cache-key", None)
    assert recs is None

@patch('cache_utils._default_s3')
def test_get_cached_recommendations_other_error(mock_s3):
    err_resp = {'Error': {'Code': '500', 'Message': 'Internal Error'}}
    mock_s3.head_object.side_effect = ClientError(err_resp, 'HeadObject')
    with pytest.raises(ClientError):
        cache_utils.get_cached_recommendations("cache-key", None)

@patch('cache_utils._default_s3')
@patch('builtins.open', new_callable=mock_open)
def test_save_recommendations_to_cache(mock_file, mock_s3):
    cache_utils.save_recommendations_to_cache("cache-key", [{"name": "Catan"}])
    mock_s3.upload_file.assert_called_once()
    args, kwargs = mock_s3.upload_file.call_args
    assert args[1] == 'test-bucket'
    assert args[2] == 'cache-key'

@patch('cache_utils._default_s3')
def test_save_recommendations_to_cache_error(mock_s3):
    mock_s3.upload_file.side_effect = Exception("S3 upload error")
    # should log error and not raise exception
    cache_utils.save_recommendations_to_cache("cache-key", [{"name": "Catan"}])
    mock_s3.upload_file.assert_called_once()

@patch('cache_utils._default_s3')
@patch('requests.get')
def test_get_bgg_hotness_fresh_cache(mock_get, mock_s3):
    now = datetime.now(timezone.utc)
    mock_s3.head_object.return_value = {
        'LastModified': now - timedelta(minutes=10)
    }
    with patch('builtins.open', new_callable=mock_open, read_data='[{"id": "1", "rank": 1, "name": "Catan"}]'):
        hot = cache_utils.get_bgg_hotness(ttl_hours=2)
        assert hot == [{"id": "1", "rank": 1, "name": "Catan"}]
        mock_get.assert_not_called()

@patch('cache_utils._default_s3')
@patch('requests.get')
def test_get_bgg_hotness_api_success(mock_get, mock_s3):
    mock_s3.head_object.side_effect = ClientError({'Error': {'Code': '404'}}, 'HeadObject')
    mock_xml = """<items><item id="12" rank="1"><name value="Catan"/></item></items>"""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = mock_xml.encode('utf-8')
    mock_get.return_value = mock_response

    with patch('builtins.open', new_callable=mock_open) as mock_file:
        hot = cache_utils.get_bgg_hotness(ttl_hours=2)
        assert len(hot) == 1
        assert hot[0]["id"] == "12"
        assert hot[0]["rank"] == 1
        assert hot[0]["name"] == "Catan"
        mock_get.assert_called_once_with("https://boardgamegeek.com/xmlapi2/hot?type=boardgame", headers={"Authorization": "Bearer test-token"}, timeout=5)
        mock_s3.upload_file.assert_called_once()

@patch('cache_utils._default_s3')
@patch('requests.get')
def test_get_bgg_hotness_api_failure_fallback(mock_get, mock_s3):
    mock_s3.head_object.side_effect = ClientError({'Error': {'Code': '404'}}, 'HeadObject')
    mock_get.side_effect = Exception("HTTP error")

    # Mock download of stale S3 cache
    with patch('builtins.open', new_callable=mock_open, read_data='[{"id": "99", "rank": 2, "name": "Fallback"}]'):
        hot = cache_utils.get_bgg_hotness(ttl_hours=2)
        assert hot == [{"id": "99", "rank": 2, "name": "Fallback"}]
        mock_s3.download_file.assert_called_once()

@patch('cache_utils._default_s3')
@patch('requests.get')
def test_get_bgg_hotness_api_failure_no_fallback(mock_get, mock_s3):
    mock_s3.head_object.side_effect = ClientError({'Error': {'Code': '404'}}, 'HeadObject')
    mock_get.side_effect = Exception("HTTP error")
    mock_s3.download_file.side_effect = Exception("No cache file on S3")

    hot = cache_utils.get_bgg_hotness(ttl_hours=2)
    assert hot == []

def test_validate_username():
    assert cache_utils.validate_username("user123") is True
    assert cache_utils.validate_username("user_name") is True
    assert cache_utils.validate_username("") is False
    assert cache_utils.validate_username("a" * 26) is False
    assert cache_utils.validate_username("user-name") is False  # hyphen not allowed

def test_parse_weights():
    # Happy path
    qp = {'w_mech': '0.7', 'w_cat': '0.3', 'w_pop': '0.9', 'w_hot': '0.1', 'w_comp': '0.5', 'w_des': '0.8', 'w_pub': '0.2'}
    w = cache_utils.parse_weights(qp)
    assert w['w_mech'] == 0.7
    assert w['w_cat'] == 0.3
    assert w['w_pub'] == 0.2

    # Clamping
    qp_clamp = {'w_mech': '1.5', 'w_cat': '-0.5'}
    w_clamp = cache_utils.parse_weights(qp_clamp)
    assert w_clamp['w_mech'] == 1.0
    assert w_clamp['w_cat'] == 0.0

    # Defaults and malformed inputs
    qp_malformed = {'w_mech': 'abc', 'w_cat': None}
    w_malformed = cache_utils.parse_weights(qp_malformed)
    assert w_malformed['w_mech'] == 0.5
    assert w_malformed['w_cat'] == 0.5
