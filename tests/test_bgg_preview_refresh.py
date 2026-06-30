import os
import sys
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
import urllib.error

# Add the lambda dir to python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_preview_refresh'))
import bgg_preview_refresh

@pytest.fixture
def mock_s3_fixture():
    with patch('bgg_preview_refresh.s3') as mock_s3:
        yield mock_s3

def test_auto_discovery_and_pull(mock_s3_fixture):
    # Setup S3 mock for config and games download
    mock_previews = [
        {
            "convention_id": "gencon2026",
            "name": "Gen Con 2026 Preview",
            "date": "2026-08-01",
            "previewid": 92
        }
    ]
    mock_games = {
        "gencon2026": ["123", "456"]
    }
    
    def side_effect(bucket, key, local_path):
        if "active_previews_games.json" in key:
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(mock_games, f)
        elif "active_previews.json" in key:
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(mock_previews, f)
                
    mock_s3_fixture.download_file.side_effect = side_effect
    
    # We want to mock current time to be 2026-06-30 (Gen Con 92 is active)
    fixed_now = datetime(2026, 6, 30, tzinfo=timezone.utc)
    
    # Mock urlopen calls
    # 1. Check ID 93 details: active!
    # 2. Check ID 94 details: 404!
    # 3. Fetch ID 92 items (page 1 has item 123, 456; page 2 is empty)
    # 4. Fetch ID 93 items (page 1 has item 789; page 2 is empty)
    
    def urlopen_mock(req, timeout=10):
        url = req.full_url
        mock_res = MagicMock()
        mock_res.getcode.return_value = 200
        mock_res.status = 200
        mock_res.__enter__.return_value = mock_res
        
        if "api/geekpreview/93" in url:
            data = {
                "previewid": "93",
                "title": "Essen Spiel 2026 Preview",
                "end_date": "2026-10-25",
                "linkname": "essen-spiel-2026-preview"
            }
            mock_res.read.return_value = json.dumps(data).encode('utf-8')
            return mock_res
        elif "api/geekpreview/94" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        elif "previewid=92" in url:
            if "pageid=1" in url:
                data = [{"objectid": "123"}, {"objectid": "456"}]
                mock_res.read.return_value = json.dumps(data).encode('utf-8')
                return mock_res
            else:
                mock_res.read.return_value = b"[]"
                return mock_res
        elif "previewid=93" in url:
            if "pageid=1" in url:
                data = [{"objectid": "789"}]
                mock_res.read.return_value = json.dumps(data).encode('utf-8')
                return mock_res
            else:
                mock_res.read.return_value = b"[]"
                return mock_res
                
        raise ValueError(f"Unexpected url: {url}")
        
    with patch('urllib.request.urlopen', side_effect=urlopen_mock), \
         patch('bgg_preview_refresh.datetime') as mock_datetime:
         
        mock_datetime.now.return_value = fixed_now
        mock_datetime.strptime = datetime.strptime
        
        event = {}
        context = None
        res = bgg_preview_refresh.lambda_handler(event, context)
        
        assert res['statusCode'] == 200
        
        # Verify uploads
        # Check config upload
        config_uploaded = False
        games_uploaded = False
        
        for call in mock_s3_fixture.upload_file.call_args_list:
            local_path = call[0][0]
            key = call[0][2]
            with open(local_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            if "active_previews.json" in key:
                config_uploaded = True
                assert len(content) == 2
                assert content[0]["convention_id"] == "gencon2026"
                assert content[1]["convention_id"] == "essenspiel2026"
                assert content[1]["previewid"] == 93
                assert content[1]["date"] == "2026-10-25"
            elif "active_previews_games.json" in key:
                games_uploaded = True
                assert content["gencon2026"] == ["123", "456"]
                assert content["essenspiel2026"] == ["789"]
                
        assert config_uploaded
        assert games_uploaded

def test_passed_conventions_cleanup_with_seed(mock_s3_fixture):
    # Setup mock active_previews.json: both 92 and 93 are passed.
    mock_previews = [
        {
            "convention_id": "gencon2026",
            "name": "Gen Con 2026 Preview",
            "date": "2026-08-01",
            "previewid": 92
        },
        {
            "convention_id": "essenspiel2026",
            "name": "Essen Spiel 2026 Preview",
            "date": "2026-09-28",
            "previewid": 93
        }
    ]
    mock_games = {
        "gencon2026": ["123", "456"],
        "essenspiel2026": ["789"]
    }
    
    def side_effect(bucket, key, local_path):
        if "active_previews_games.json" in key:
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(mock_games, f)
        elif "active_previews.json" in key:
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(mock_previews, f)
                
    mock_s3_fixture.download_file.side_effect = side_effect
    
    # We want to mock current time to be 2026-10-01 (Both 92 and 93 are past/passed)
    fixed_now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    
    # Mock urlopen calls
    # 1. Check ID 94 details: 404!
    # No preview items should be fetched because all existing conventions are passed
    # and no new ones are discovered.
    def urlopen_mock(req, timeout=10):
        url = req.full_url
        if "api/geekpreview/94" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        raise ValueError(f"No other URL should be requested. Got: {url}")
        
    with patch('urllib.request.urlopen', side_effect=urlopen_mock), \
         patch('bgg_preview_refresh.datetime') as mock_datetime:
         
        mock_datetime.now.return_value = fixed_now
        mock_datetime.strptime = datetime.strptime
        
        event = {}
        context = None
        res = bgg_preview_refresh.lambda_handler(event, context)
        
        assert res['statusCode'] == 200
        
        # Verify uploads
        config_uploaded = False
        games_uploaded = False
        
        for call in mock_s3_fixture.upload_file.call_args_list:
            local_path = call[0][0]
            key = call[0][2]
            with open(local_path, 'r', encoding='utf-8') as f:
                content = json.load(f)
            if "active_previews.json" in key:
                config_uploaded = True
                # Must keep exactly one (the latest) seed: essenspiel2026 (93)
                assert len(content) == 1
                assert content[0]["convention_id"] == "essenspiel2026"
                assert content[0]["previewid"] == 93
            elif "active_previews_games.json" in key:
                games_uploaded = True
                # All games for passed conventions must be deleted
                assert content == {}
                
        assert config_uploaded
        assert games_uploaded
