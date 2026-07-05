import os
import sys
import json
import math
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, mock_open
import pytest
import pandas as pd
import numpy as np
from botocore.exceptions import ClientError

# Set mock env variables BEFORE importing bgg_taste_analytics
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_ACCESS_KEY_ID'] = 'mock-key'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'mock-secret'
os.environ['S3_OUTPUT_BUCKET_NAME'] = 'test-bucket'

# Add the lambda dir to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_taste_analytics'))
import bgg_taste_analytics

@pytest.fixture(autouse=True)
def reset_globals():
    bgg_taste_analytics.CATALOG_CACHE = None
    yield

def test_extract_usernames_from_body_s3_event():
    # S3 event notification JSON
    body = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "data/users/alex.parquet"}
                }
            },
            {
                "s3": {
                    "bucket": {"name": "test-bucket"},
                    "object": {"key": "data/users/bob.parquet"}
                }
            }
        ]
    }
    body_str = json.dumps(body)
    usernames = bgg_taste_analytics.extract_usernames_from_body(body_str)
    assert usernames == ["alex", "bob"]

def test_extract_usernames_from_body_json_dict():
    # JSON with username key
    body = {"username": "charlie"}
    body_str = json.dumps(body)
    usernames = bgg_taste_analytics.extract_usernames_from_body(body_str)
    assert usernames == ["charlie"]

def test_extract_usernames_from_body_raw_string():
    # Raw string
    body_str = "  david  "
    usernames = bgg_taste_analytics.extract_usernames_from_body(body_str)
    assert usernames == ["david"]

@patch('bgg_taste_analytics.s3')
@patch('pandas.read_parquet')
def test_get_catalog_download_and_cache(mock_read_parquet, mock_s3):
    mock_df = pd.DataFrame([{"id": "1", "name": "Catan"}])
    mock_read_parquet.return_value = mock_df

    df = bgg_taste_analytics.get_catalog()
    assert df is not None
    assert len(df) == 1
    assert df.iloc[0]["name"] == "Catan"
    mock_s3.download_file.assert_called_once_with('test-bucket', 'data/boardgames_combined/catalog.parquet', '/tmp/catalog.parquet')

    # Test cache hit
    mock_s3.reset_mock()
    df2 = bgg_taste_analytics.get_catalog()
    assert df2 is df
    mock_s3.download_file.assert_not_called()

@patch('bgg_taste_analytics.s3')
@patch('pandas.read_parquet')
@patch('builtins.open', new_callable=mock_open)
def test_process_taste_profile(mock_file, mock_read_parquet, mock_s3):
    # Mock user collection dataframe
    user_df = pd.DataFrame([
        {"id": "100", "rating": 9.0, "own": True},
        {"id": "200", "rating": 5.0, "own": False},
        {"id": "300", "rating": 7.0, "own": True}
    ])
    # Mock catalog dataframe
    catalog_df = pd.DataFrame([
        {"id": "100", "name": "Catan", "categories": ["cat1"], "mechanics": ["mech1"], "rating": 8.0, "complexity": 2.0, "designers": ["des1"], "publishers": ["pub1", "pub_local1"]},
        {"id": "200", "name": "Gloomhaven", "categories": ["cat2"], "mechanics": ["mech2"], "rating": 9.0, "complexity": 4.5, "designers": ["des2"], "publishers": ["pub2"]},
        {"id": "300", "name": "Ticket to Ride", "categories": ["cat1"], "mechanics": ["mech3"], "rating": 7.5, "complexity": 2.5, "designers": ["des3"], "publishers": ["pub3"]}
    ])
    # Side effects for read_parquet calls
    mock_read_parquet.side_effect = [user_df, catalog_df]

    # Run taste profile logic
    bgg_taste_analytics.process_taste_profile("alex")

    # Assert S3 downloads occurred
    mock_s3.download_file.assert_any_call('test-bucket', 'data/users/alex.parquet', '/tmp/alex.parquet')
    
    # Assert JSON file was written and uploaded to S3
    mock_s3.upload_file.assert_called_once()
    args, kwargs = mock_s3.upload_file.call_args
    assert args[1] == 'test-bucket'
    assert args[2] == 'data/users/alex_taste_profile.json'

    # Check written file contents
    mock_file.assert_called_with('/tmp/alex_taste_profile.json', 'w', encoding='utf-8')
    handle = mock_file()
    written_data = "".join(call[0][0] for call in handle.write.call_args_list)
    profile_json = json.loads(written_data)

    assert "mech_weights" in profile_json
    assert "cat_weights" in profile_json
    assert "complexity_weights" in profile_json
    assert "designer_weights" in profile_json
    assert "publisher_weights" in profile_json
    assert "generated_at" in profile_json

    # Since user liked game ID 100 (rating 9.0 -> weight 4.0) and ID 300 (rating 7.0 -> weight 2.0),
    # categories/mechanics/designers/publishers accumulate:
    assert profile_json["cat_weights"]["cat1"] == 6.0
    assert profile_json["mech_weights"]["mech1"] == 4.0
    assert profile_json["mech_weights"]["mech3"] == 2.0
    assert profile_json["designer_weights"]["des1"] == 4.0
    assert profile_json["designer_weights"]["des3"] == 2.0
    assert profile_json["publisher_weights"]["pub1"] == 4.0
    assert profile_json["publisher_weights"]["pub3"] == 2.0
    assert "pub_local1" not in profile_json["publisher_weights"]
    # Complexity weights are averaged: (4.0 + 2.0) / 2 = 3.0
    assert profile_json["complexity_weights"] == {"Light": 0.0, "Medium-Light": 3.0, "Medium-Heavy": 0.0, "Heavy": 0.0}

@patch('bgg_taste_analytics.process_taste_profile')
def test_lambda_handler_success(mock_process):
    sqs_event = {
        "Records": [
            {
                "messageId": "msg-123",
                "body": "alex"
            }
        ]
    }
    resp = bgg_taste_analytics.lambda_handler(sqs_event, None)
    assert resp == {"batchItemFailures": []}
    mock_process.assert_called_once_with("alex")

@patch('bgg_taste_analytics.process_taste_profile')
def test_lambda_handler_failure(mock_process):
    mock_process.side_effect = Exception("S3 failed")
    sqs_event = {
        "Records": [
            {
                "messageId": "msg-123",
                "body": "alex"
            }
        ]
    }
    resp = bgg_taste_analytics.lambda_handler(sqs_event, None)
    assert resp == {"batchItemFailures": [{"itemIdentifier": "msg-123"}]}
