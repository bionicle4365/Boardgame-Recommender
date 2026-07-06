import os
import sys
import json
from unittest.mock import MagicMock, patch
import pytest
import pandas as pd
from botocore.exceptions import ClientError

# Mock boto3.client before importing narration to avoid bedrock-runtime UnknownServiceError
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
import narration

def test_build_weight_context():
    weights = {
        'w_mech': 0.8,
        'w_cat': 0.2,
        'w_pop': 0.5,
        'w_hot': 0.5,
        'w_comp': 0.4,
        'w_des': 0.3,
        'w_pub': 0.1
    }
    qp = {
        'player_count': '3',
        'duration_pref': 'medium',
        'complexity_pref': 'heavy'
    }

    ctx = narration.build_weight_context(qp, weights)
    assert "Mechanics Similarity Weight: 80%" in ctx
    assert "Categories Similarity Weight: 20%" in ctx
    assert "Target Session Player Count: 3 players" in ctx
    assert "Target Play Time Preference: Medium length games" in ctx
    assert "Target Complexity/Weight Preference: Heavy weight games" in ctx
    assert "The user is highly interested in currently trending or hot releases" in ctx
    assert "The user places strong emphasis on games sharing similar play styles and mechanics" in ctx
    assert "The user places strong emphasis on games sharing similar themes and categories" not in ctx

def test_build_fallback_recommendations():
    candidates = [
        {'id': '1', 'name': 'Catan', 'rating': 7.2, 'complexity': 2.3, 'mechanics': ['Trading', 'Dice']},
        {'id': '2', 'name': 'Carcassonne', 'rating': 7.4, 'complexity': 1.9, 'mechanics': ['Tile Placement']},
        {'id': '3', 'name': 'Ticket to Ride', 'rating': 7.4, 'complexity': 1.6, 'mechanics': ['Route Building']}
    ]
    recs = narration.build_fallback_recommendations(candidates)
    assert len(recs) == 3
    assert recs[0]['name'] == 'Catan'
    assert recs[0]['reason'] == 'Highly recommended match sharing mechanics: Trading, Dice.'
    assert recs[1]['name'] == 'Carcassonne'
    assert recs[1]['reason'] == 'Highly recommended match sharing mechanics: Tile Placement.'

@patch('narration._bedrock')
def test_narrate_recommendations_success(mock_bedrock_func):
    mock_bedrock = MagicMock()
    mock_bedrock_func.return_value = mock_bedrock

    # Mock successful Bedrock response returning valid JSON
    mock_response = {
        'output': {
            'message': {
                'content': [
                    {
                        'text': json.dumps({
                            'recommendations': [
                                {'name': 'Catan', 'reason': 'Great trading mechanics matching your taste.'},
                                {'name': 'Carcassonne', 'reason': 'Love the tile placement, just like your favorite games.'}
                            ]
                        })
                    }
                ]
            }
        }
    }
    mock_bedrock.converse.return_value = mock_response

    candidates = [
        {'id': '1', 'name': 'Catan', 'rating': 7.2, 'complexity': 2.3, 'mechanics': ['Trading', 'Dice']},
        {'id': '2', 'name': 'Carcassonne', 'rating': 7.4, 'complexity': 1.9, 'mechanics': ['Tile Placement']}
    ]

    recs = narration.narrate_recommendations(candidates, "Liked games list", "Weight context", {})
    assert recs is not None
    assert len(recs) == 2
    assert recs[0]['name'] == 'Catan'
    assert recs[0]['reason'] == 'Great trading mechanics matching your taste.'
    assert recs[1]['name'] == 'Carcassonne'
    assert recs[1]['reason'] == 'Love the tile placement, just like your favorite games.'

@patch('narration._bedrock')
def test_narrate_recommendations_markdown_json(mock_bedrock_func):
    mock_bedrock = MagicMock()
    mock_bedrock_func.return_value = mock_bedrock

    # Mock response wrapped in markdown json block
    markdown_text = """```json
{
  "recommendations": [
    {"name": "Catan", "reason": "Reason 1"}
  ]
}
```"""
    mock_response = {
        'output': {
            'message': {
                'content': [{'text': markdown_text}]
            }
        }
    }
    mock_bedrock.converse.return_value = mock_response

    candidates = [
        {'id': '1', 'name': 'Catan', 'rating': 7.2, 'complexity': 2.3, 'mechanics': ['Trading']}
    ]

    recs = narration.narrate_recommendations(candidates, "Liked games", "Weights", {})
    assert recs is not None
    assert len(recs) == 1
    assert recs[0]['name'] == 'Catan'
    assert recs[0]['reason'] == 'Reason 1'

@patch('narration._bedrock')
def test_narrate_recommendations_malformed_json(mock_bedrock_func):
    mock_bedrock = MagicMock()
    mock_bedrock_func.return_value = mock_bedrock

    # Malformed JSON
    mock_response = {
        'output': {
            'message': {
                'content': [{'text': '{"recommendations": [{"name": "Catan", "reason": "Reason"}'}] # missing closing braces
            }
        }
    }
    mock_bedrock.converse.return_value = mock_response

    candidates = [
        {'id': '1', 'name': 'Catan', 'rating': 7.2, 'complexity': 2.3}
    ]

    recs = narration.narrate_recommendations(candidates, "Liked games", "Weights", {})
    # Should handle error gracefully and return None
    assert recs is None

@patch('narration._bedrock')
def test_narrate_recommendations_name_matching_fallbacks(mock_bedrock_func):
    mock_bedrock = MagicMock()
    mock_bedrock_func.return_value = mock_bedrock

    # LLM returned name with casing difference or partial match
    mock_response = {
        'output': {
            'message': {
                'content': [
                    {
                        'text': json.dumps({
                            'recommendations': [
                                {'name': 'catan', 'reason': 'exact match lowercase'},
                                {'name': 'Catan: Second Edition', 'reason': 'partial match fallback'},
                                {'name': 'Unknown Game', 'reason': 'no match'}
                            ]
                        })
                    }
                ]
            }
        }
    }
    mock_bedrock.converse.return_value = mock_response

    candidates = [
        {'id': '1', 'name': 'Catan', 'rating': 7.2, 'complexity': 2.3, 'mechanics': ['Trading']}
    ]

    recs = narration.narrate_recommendations(candidates, "Liked games", "Weights", {})
    # Only Catan should resolve (lowercase 'catan' is exact match, 'Catan: Second Edition' partial matches but is duplicate of ID 1, 'Unknown Game' excluded)
    assert len(recs) == 1
    assert recs[0]['id'] == '1'
    assert recs[0]['name'] == 'Catan'
    assert recs[0]['reason'] == 'exact match lowercase'

@patch('narration._bedrock')
def test_narrate_recommendations_fill_in_logic(mock_bedrock_func):
    mock_bedrock = MagicMock()
    mock_bedrock_func.return_value = mock_bedrock

    # LLM returned only 8 recommendations (meeting the threshold original_count >= 8), we fill in to 10
    recs_list = [{'name': f'Game {i}', 'reason': f'Reason {i}'} for i in range(1, 9)]
    mock_response = {
        'output': {
            'message': {
                'content': [
                    {
                        'text': json.dumps({
                            'recommendations': recs_list
                        })
                    }
                ]
            }
        }
    }
    mock_bedrock.converse.return_value = mock_response

    # 11 candidates
    candidates = [{'id': str(i), 'name': f'Game {i}', 'rating': 7.0, 'complexity': 2.0, 'mechanics': ['Mech']} for i in range(1, 12)]

    recs = narration.narrate_recommendations(candidates, "Liked games", "Weights", {})
    assert len(recs) == 10
    # The first 8 are from LLM
    for i in range(8):
        assert recs[i]['id'] == str(i + 1)
        assert recs[i]['reason'] == f'Reason {i + 1}'
    # The next 2 are filled in from remaining candidates
    assert recs[8]['id'] == '9'
    assert recs[8]['reason'] == 'Highly ranked catalog match sharing key mechanics: Mech.'
    assert recs[9]['id'] == '10'
