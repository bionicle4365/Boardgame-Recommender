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

# Add repo root and lambda dir to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_taste_analytics'))
import bgg_taste_analytics

@pytest.fixture(autouse=True)
def reset_globals():
    bgg_taste_analytics.CATALOG_CACHE = None
    bgg_taste_analytics.FEATURE_FREQUENCIES_CACHE = None
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

    assert "raw_mech_weights" in profile_json
    assert "raw_cat_weights" in profile_json
    assert profile_json["idf_applied"] is True

    # Raw damped weights (prior to IDF discounting)
    # - cat1 occurs twice (n=2, tot_w=6.0, avg_w=3.0): 3.0 * (1 + 0.3 * ln(2)) = 3.62
    # - single count items (n=1) retain raw weight: weight * (1 + 0.3 * ln(1)) = weight
    assert profile_json["raw_cat_weights"]["cat1"] == 3.62
    assert profile_json["raw_mech_weights"]["mech1"] == 4.0
    assert profile_json["raw_mech_weights"]["mech3"] == 2.0

    # Final IDF-weighted affinities:
    # cat1 appears in 2 of 3 catalog games -> IDF = ln(1 + 3/2) = 0.9163 -> 3.62 * 0.9163 = 3.32
    # mech1 appears in 1 of 3 catalog games -> IDF = ln(1 + 3/1) = 1.3863 -> 4.0 * 1.3863 = 5.55
    # mech3 appears in 1 of 3 catalog games -> IDF = ln(1 + 3/1) = 1.3863 -> 2.0 * 1.3863 = 2.77
    assert profile_json["cat_weights"]["cat1"] == 3.32
    assert profile_json["mech_weights"]["mech1"] == 5.55
    assert profile_json["mech_weights"]["mech3"] == 2.77
    assert profile_json["designer_weights"]["des1"] == 4.0
    assert profile_json["designer_weights"]["des3"] == 2.0
    assert profile_json["publisher_weights"]["pub1"] == 4.0
    assert profile_json["publisher_weights"]["pub3"] == 2.0
    assert "pub_local1" not in profile_json["publisher_weights"]
    # Complexity weights are averaged: (4.0 + 2.0) / 2 = 3.0
    assert profile_json["complexity_weights"] == {"Light": 0.0, "Medium-Light": 3.0, "Medium-Heavy": 0.0, "Heavy": 0.0}

def test_calculate_damped_affinity():
    # 1 count: returns exact weight
    res1 = bgg_taste_analytics.calculate_damped_affinity({"ItemA": 4.0}, {"ItemA": 1})
    assert res1["ItemA"] == 4.0

    # Multiple counts: applies avg_w * (1 + 0.3 * ln(n))
    # n=9, tot_w=18.0 -> avg_w=2.0 -> 2.0 * (1 + 0.3 * ln(9)) = 3.32
    res9 = bgg_taste_analytics.calculate_damped_affinity({"ItemB": 18.0}, {"ItemB": 9})
    assert res9["ItemB"] == 3.32

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


def test_apply_feature_idf():
    # 1. Using precomputed IDF dict
    freqs = {
        "total_games": 1000,
        "mechanic_idf": {"Hand Management": 1.5, "Trick-taking": 4.0},
        "category_idf": {"Card Game": 1.2, "Wargame": 3.5}
    }
    raw_mechs = {"Hand Management": 5.0, "Trick-taking": 3.0}
    weighted = bgg_taste_analytics.apply_feature_idf(raw_mechs, "mechanics", freqs)
    # Hand Management: 5.0 * 1.5 = 7.50, Trick-taking: 3.0 * 4.0 = 12.00
    assert weighted["Hand Management"] == 7.50
    assert weighted["Trick-taking"] == 12.00

    # 2. Dynamic IDF calculation when idf dict is missing but counts are present
    freqs_counts = {
        "total_games": 100,
        "mechanics": {"Common": 80, "Rare": 5}
    }
    raw_mechs = {"Common": 4.0, "Rare": 2.0, "Unseen": 1.0}
    weighted_dyn = bgg_taste_analytics.apply_feature_idf(raw_mechs, "mechanics", freqs_counts)
    # Common: 4.0 * ln(1 + 100/80) = 4.0 * ln(2.25) = 4.0 * 0.8109 = 3.24
    assert weighted_dyn["Common"] == 3.24
    # Rare: 2.0 * ln(1 + 100/5) = 2.0 * ln(21) = 2.0 * 3.0445 = 6.09
    assert weighted_dyn["Rare"] == 6.09
    # Unseen: 1.0 * ln(1 + 100/1) = 1.0 * ln(101) = 4.62
    assert weighted_dyn["Unseen"] == 4.62

    # 3. Fallback when frequencies are empty
    empty_weighted = bgg_taste_analytics.apply_feature_idf(raw_mechs, "mechanics", {})
    assert empty_weighted == raw_mechs


@patch('bgg_taste_analytics.s3')
@patch('pandas.read_parquet')
@patch('builtins.open', new_callable=mock_open)
def test_process_taste_profile_distinctive_tag_elevation(mock_file, mock_read_parquet, mock_s3):
    # Specialized user: plays mostly Trick-taking (3 games, rated 8.0) and some Hand Management (6 games, rated 7.0)
    # In raw damped affinity: Hand Management has 6 games (weight 2.0) -> tot=12.0, avg=2.0 -> 2.0 * (1 + 0.3 * ln(6)) = 3.07
    # Trick-taking has 3 games (weight 3.0) -> tot=9.0, avg=3.0 -> 3.0 * (1 + 0.3 * ln(3)) = 3.99
    # Now suppose Hand Management had 10 games rated 8.0 (tot=30, avg=3.0) -> 3.0 * (1 + 0.3 * ln(10)) = 5.07
    # and Trick-taking had 3 games rated 8.0 (tot=9, avg=3.0) -> 3.0 * (1 + 0.3 * ln(3)) = 3.99
    # In raw damped affinity: Hand Management (5.07) > Trick-taking (3.99).
    user_records = []
    catalog_records = []

    # 10 Hand Management games
    for i in range(1, 11):
        g_id = f"hm_{i}"
        user_records.append({"id": g_id, "rating": 8.0, "own": True})
        catalog_records.append({
            "id": g_id, "name": f"HM Game {i}", "categories": ["Card Game"],
            "mechanics": ["Hand Management"], "rating": 7.5, "complexity": 2.5,
            "designers": ["Des A"], "publishers": ["Pub A"]
        })

    # 3 Trick-taking games
    for i in range(1, 4):
        g_id = f"tt_{i}"
        user_records.append({"id": g_id, "rating": 8.0, "own": True})
        catalog_records.append({
            "id": g_id, "name": f"TT Game {i}", "categories": ["Trick-taking Category"],
            "mechanics": ["Trick-taking"], "rating": 8.0, "complexity": 2.5,
            "designers": ["Des B"], "publishers": ["Pub B"]
        })

    user_df = pd.DataFrame(user_records)
    catalog_df = pd.DataFrame(catalog_records)
    mock_read_parquet.side_effect = [user_df, catalog_df]

    # Pre-populate FEATURE_FREQUENCIES_CACHE with realistic BGG frequencies
    # Hand Management: common (N_m = 17629 in 139123 games -> IDF = 2.1851)
    # Trick-taking: distinctive (N_m = 2988 in 139123 games -> IDF = 3.8620)
    bgg_taste_analytics.FEATURE_FREQUENCIES_CACHE = {
        "total_games": 139123,
        "mechanic_idf": {
            "Hand Management": 2.1851,
            "Trick-taking": 3.8620
        },
        "category_idf": {
            "Card Game": 1.4901,
            "Trick-taking Category": 4.5000
        }
    }

    bgg_taste_analytics.process_taste_profile("specialized_user")

    # Inspect written profile
    handle = mock_file()
    written_data = "".join(call[0][0] for call in handle.write.call_args_list if call[0])
    profile_json = json.loads(written_data)

    # 1. In raw damped weights: Hand Management was higher than Trick-taking
    assert profile_json["raw_mech_weights"]["Hand Management"] == 5.07
    assert profile_json["raw_mech_weights"]["Trick-taking"] == 3.99
    assert profile_json["raw_mech_weights"]["Hand Management"] > profile_json["raw_mech_weights"]["Trick-taking"]

    # 2. In final TF-IDF weighted weights: Trick-taking is elevated above Hand Management!
    # Hand Management: 5.07 * 2.1851 = 11.08
    # Trick-taking: 3.99 * 3.8620 = 15.41
    assert profile_json["mech_weights"]["Hand Management"] == 11.08
    assert profile_json["mech_weights"]["Trick-taking"] == 15.41
    assert profile_json["mech_weights"]["Trick-taking"] > profile_json["mech_weights"]["Hand Management"]

    # 3. Metadata fields verified
    assert profile_json["idf_applied"] is True
    assert profile_json["user_mean_complexity"] == 2.5
    assert "raw_cat_weights" in profile_json


def test_generate_catalog_feature_frequencies_helper():
    from scripts.generate_feature_frequencies import generate_catalog_feature_frequencies

    mock_catalog = pd.DataFrame([
        {"id": "1", "mechanics": ["Dice Rolling", "Hand Management"], "categories": ["Card Game"]},
        {"id": "2", "mechanics": ["Dice Rolling"], "categories": ["Dice"]},
        {"id": "3", "mechanics": ["Trick-taking"], "categories": ["Card Game"]},
        {"id": "4", "mechanics": None, "categories": []}
    ])

    result = generate_catalog_feature_frequencies(mock_catalog)
    assert result["total_games"] == 4
    assert result["mechanics"]["Dice Rolling"] == 2
    assert result["mechanics"]["Hand Management"] == 1
    assert result["mechanics"]["Trick-taking"] == 1
    assert result["categories"]["Card Game"] == 2
    assert result["categories"]["Dice"] == 1

    # Check precomputed IDF values
    # Dice Rolling (2 in 4): ln(1 + 4/2) = ln(3) = 1.0986
    assert abs(result["mechanic_idf"]["Dice Rolling"] - 1.0986) < 0.001
    # Trick-taking (1 in 4): ln(1 + 4/1) = ln(5) = 1.6094
    assert abs(result["mechanic_idf"]["Trick-taking"] - 1.6094) < 0.001
    # Card Game (2 in 4): ln(3) = 1.0986
    assert abs(result["category_idf"]["Card Game"] - 1.0986) < 0.001
