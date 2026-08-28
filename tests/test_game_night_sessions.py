import os
import sys
import json
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'bgg_recommender'))

from sessions import (
    calculate_consensus,
    create_session,
    get_session,
    submit_vote,
    list_creator_sessions,
    POINTS_YES,
    POINTS_NEUTRAL,
    POINTS_VETO
)
import bgg_recommender


@pytest.fixture
def sample_candidates():
    return [
        {
            "id": "1",
            "name": "Dune: Imperium",
            "thumbnail": "https://example.com/dune.jpg",
            "rating": 8.4,
            "complexity": 3.0
        },
        {
            "id": "2",
            "name": "Brass: Birmingham",
            "thumbnail": "https://example.com/brass.jpg",
            "rating": 8.6,
            "complexity": 3.9
        },
        {
            "id": "3",
            "name": "Catan",
            "thumbnail": "https://example.com/catan.jpg",
            "rating": 7.1,
            "complexity": 2.3
        }
    ]


def test_calculate_consensus_basic_scoring(sample_candidates):
    # Player 1 votes: Dune (yes), Brass (neutral), Catan (neutral)
    # Player 2 votes: Dune (yes), Brass (yes), Catan (neutral)
    votes = {
        "Alice": {"1": "yes", "2": "neutral", "3": "neutral"},
        "Bob": {"1": "yes", "2": "yes", "3": "neutral"}
    }
    
    result = calculate_consensus(sample_candidates, votes)
    
    assert result['total_voters'] == 2
    assert result['winner']['id'] == "1"  # Dune has 4 pts (2+2), Brass has 3 pts (1+2), Catan has 2 pts (1+1)
    
    rankings = result['rankings']
    assert rankings[0]['id'] == "1"
    assert rankings[0]['score'] == 4
    assert rankings[0]['yes_count'] == 2
    
    assert rankings[1]['id'] == "2"
    assert rankings[1]['score'] == 3
    
    assert rankings[2]['id'] == "3"
    assert rankings[2]['score'] == 2
    assert len(result['vetoed_games']) == 0


def test_calculate_consensus_hard_veto_disqualification(sample_candidates):
    # Brass gets 1 yes + 1 neutral, but Charlie vetoes it!
    # Dune gets 2 neutral. Dune should win over Brass because Brass is vetoed!
    votes = {
        "Alice": {"1": "neutral", "2": "yes", "3": "neutral"},
        "Charlie": {"1": "neutral", "2": "veto", "3": "neutral"}
    }
    
    result = calculate_consensus(sample_candidates, votes)
    assert result['winner']['id'] == "1"  # Dune wins
    assert "2" in result['vetoed_games']  # Brass was vetoed
    
    # Check Brass ranking properties
    brass_rank = next(r for r in result['rankings'] if r['id'] == "2")
    assert brass_rank['is_vetoed'] is True
    assert brass_rank['veto_count'] == 1
    assert "Charlie" in brass_rank['voters_veto']


def test_calculate_consensus_all_vetoed(sample_candidates):
    votes = {
        "GrumpyGamer": {"1": "veto", "2": "veto", "3": "veto"}
    }
    result = calculate_consensus(sample_candidates, votes)
    assert len(result['vetoed_games']) == 3
    assert result['winner'] is None or all(r['is_vetoed'] for r in result['rankings'])


def test_calculate_consensus_tie_breaking(sample_candidates):
    # Both Dune (#1) and Brass (#2) get 2 points. Dune was higher in original shortlist rank.
    votes = {
        "Alice": {"1": "yes", "2": "yes", "3": "neutral"}
    }
    result = calculate_consensus(sample_candidates, votes)
    assert result['rankings'][0]['id'] == "1"
    assert result['rankings'][1]['id'] == "2"


def test_create_session(sample_candidates):
    mock_table = MagicMock()
    
    session = create_session(
        creator_id="user_123",
        group_name="Friday Board Game Night",
        candidates=sample_candidates,
        duration_hours=6.0,
        roster=["Alice", "Bob", "Charlie"],
        table=mock_table
    )
    
    assert len(session['session_id']) == 8
    assert session['creator_id'] == "user_123"
    assert session['group_name'] == "Friday Board Game Night"
    assert session['duration_hours'] == 6.0
    assert session['is_closed'] is False
    assert len(session['candidates']) == 3
    assert session['roster'] == ["Alice", "Bob", "Charlie"]
    
    mock_table.put_item.assert_called_once()
    saved_item = mock_table.put_item.call_args[1]['Item']
    assert saved_item['session_id'] == session['session_id']
    assert 'expires_at' in saved_item


def test_get_session_active_and_expired(sample_candidates):
    mock_table = MagicMock()
    
    # Active session
    now = datetime.now(timezone.utc)
    future = (now + timedelta(hours=5)).isoformat()
    mock_table.get_item.return_value = {
        'Item': {
            'session_id': 'sess1234',
            'creator_id': 'user_123',
            'group_name': 'Weekend Warriors',
            'created_at': now.isoformat(),
            'closes_at': future,
            'candidates': sample_candidates,
            'votes': {}
        }
    }
    
    active_sess = get_session('sess1234', table=mock_table)
    assert active_sess['is_closed'] is False
    assert active_sess['session_id'] == 'sess1234'
    
    # Expired session
    past = (now - timedelta(hours=1)).isoformat()
    mock_table.get_item.return_value = {
        'Item': {
            'session_id': 'sess_old',
            'creator_id': 'user_123',
            'group_name': 'Past Game Night',
            'created_at': (now - timedelta(hours=25)).isoformat(),
            'closes_at': past,
            'candidates': sample_candidates,
            'votes': {}
        }
    }
    
    expired_sess = get_session('sess_old', table=mock_table)
    assert expired_sess['is_closed'] is True


def test_submit_vote_success_and_expiration(sample_candidates):
    mock_table = MagicMock()
    now = datetime.now(timezone.utc)
    
    # 1. Successful vote submission
    mock_table.get_item.return_value = {
        'Item': {
            'session_id': 'sess1234',
            'creator_id': 'user_123',
            'group_name': 'Active Night',
            'created_at': now.isoformat(),
            'closes_at': (now + timedelta(hours=2)).isoformat(),
            'candidates': sample_candidates,
            'votes': {}
        }
    }
    
    updated = submit_vote(
        session_id='sess1234',
        participant_name='Alice',
        votes_map={'1': 'yes', '2': 'veto', '3': 'neutral'},
        table=mock_table
    )
    
    assert updated['votes']['Alice']['1'] == 'yes'
    assert updated['votes']['Alice']['2'] == 'veto'
    assert updated['consensus']['rankings'][0]['id'] == '1'
    mock_table.update_item.assert_called_once()
    
    # 2. Rejection on closed session
    mock_table.get_item.return_value = {
        'Item': {
            'session_id': 'sess1234',
            'creator_id': 'user_123',
            'group_name': 'Closed Night',
            'created_at': (now - timedelta(hours=5)).isoformat(),
            'closes_at': (now - timedelta(hours=1)).isoformat(),
            'candidates': sample_candidates,
            'votes': {}
        }
    }
    
    with pytest.raises(ValueError, match="Voting has ended"):
        submit_vote('sess1234', 'Bob', {'1': 'yes'}, table=mock_table)


def test_list_creator_sessions(sample_candidates):
    mock_table = MagicMock()
    now = datetime.now(timezone.utc)
    
    mock_table.query.return_value = {
        'Items': [
            {
                'session_id': 'sess1',
                'creator_id': 'host_123',
                'group_name': 'Group A',
                'created_at': now.isoformat(),
                'closes_at': (now + timedelta(hours=24)).isoformat(),
                'candidates': sample_candidates,
                'votes': {'Alice': {'1': 'yes'}}
            }
        ]
    }
    
    sessions = list_creator_sessions('host_123', table=mock_table)
    assert len(sessions) == 1
    assert sessions[0]['session_id'] == 'sess1'
    assert sessions[0]['consensus']['total_voters'] == 1


@patch('bgg_recommender.sessions.create_session')
def test_lambda_handler_create_session_route(mock_create, sample_candidates):
    mock_create.return_value = {
        'session_id': 'abc12345',
        'group_name': 'Friday Games',
        'candidates': sample_candidates
    }
    
    event = {
        'rawPath': '/session',
        'httpMethod': 'POST',
        'body': json.dumps({
            'group_name': 'Friday Games',
            'candidates': sample_candidates,
            'duration_hours': 12
        })
    }
    
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 201
    body = json.loads(response['body'])
    assert body['session_id'] == 'abc12345'


@patch('bgg_recommender.sessions.get_session')
def test_lambda_handler_get_session_route(mock_get, sample_candidates):
    mock_get.return_value = {
        'session_id': 'abc12345',
        'group_name': 'Friday Games',
        'candidates': sample_candidates,
        'is_closed': False
    }
    
    event = {
        'rawPath': '/session',
        'httpMethod': 'GET',
        'queryStringParameters': {
            'session_id': 'abc12345'
        }
    }
    
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert body['session_id'] == 'abc12345'


@patch('bgg_recommender.sessions.submit_vote')
def test_lambda_handler_vote_route(mock_vote):
    mock_vote.return_value = {
        'session_id': 'abc12345',
        'votes': {'Alice': {'1': 'yes'}}
    }
    
    event = {
        'rawPath': '/session/vote',
        'httpMethod': 'POST',
        'body': json.dumps({
            'session_id': 'abc12345',
            'participant_name': 'Alice',
            'votes': {'1': 'yes'}
        })
    }
    
    response = bgg_recommender.lambda_handler(event, None)
    assert response['statusCode'] == 200
    body = json.loads(response['body'])
    assert 'Alice' in body['votes']


def test_decimal_serialization_roundtrip(sample_candidates):
    from decimal import Decimal
    from sessions import floats_to_decimals, decimals_to_floats
    
    mock_table = MagicMock()
    session = create_session(
        creator_id="user_123",
        group_name="Friday Games",
        candidates=sample_candidates,
        duration_hours=24.0,
        table=mock_table
    )
    
    # Check that saved item contains Decimals instead of floats
    saved_item = mock_table.put_item.call_args[1]['Item']
    assert isinstance(saved_item['duration_hours'], Decimal)
    assert isinstance(saved_item['candidates'][0]['rating'], Decimal)
    assert isinstance(saved_item['candidates'][0]['complexity'], Decimal)
    
    # Check that decimals_to_floats converts it back cleanly for JSON serialization
    converted = decimals_to_floats(saved_item)
    assert isinstance(converted['duration_hours'], (float, int))
    assert isinstance(converted['candidates'][0]['rating'], float)
    
    # Check JSON serializability
    json_str = json.dumps(converted)
    assert "Dune: Imperium" in json_str


def test_close_session(sample_candidates):
    from sessions import close_session
    mock_table = MagicMock()
    
    # Mock get_item returning the updated closed session
    now = datetime.now(timezone.utc).isoformat()
    mock_table.get_item.return_value = {
        'Item': {
            'session_id': 'close123',
            'creator_id': 'user_123',
            'creator_name': 'HostAlice',
            'group_name': 'Euro Night',
            'created_at': now,
            'closes_at': now,
            'candidates': sample_candidates,
            'votes': {}
        }
    }
    
    res = close_session('close123', table=mock_table)
    mock_table.update_item.assert_called_once()
    assert res['session_id'] == 'close123'
    assert res['is_closed'] is True


def test_cancel_session():
    from sessions import cancel_session
    mock_table = MagicMock()
    
    res = cancel_session('del123', table=mock_table)
    mock_table.delete_item.assert_called_once_with(Key={'session_id': 'del123'})
    assert res is True


def test_lambda_handler_close_and_delete_session(monkeypatch):
    import bgg_recommender
    import sessions
    
    mock_close = MagicMock(return_value={'session_id': 'sess99', 'is_closed': True})
    mock_cancel = MagicMock(return_value=True)
    monkeypatch.setattr(sessions, 'close_session', mock_close)
    monkeypatch.setattr(sessions, 'cancel_session', mock_cancel)
    
    # Test POST /session/close
    close_event = {
        'rawPath': '/session/close',
        'httpMethod': 'POST',
        'body': json.dumps({'session_id': 'sess99'})
    }
    resp_close = bgg_recommender.lambda_handler(close_event, None)
    assert resp_close['statusCode'] == 200
    mock_close.assert_called_once_with('sess99')
    
    # Test DELETE /session
    del_event = {
        'rawPath': '/session',
        'httpMethod': 'DELETE',
        'queryStringParameters': {'session_id': 'sess99'}
    }
    resp_del = bgg_recommender.lambda_handler(del_event, None)
    assert resp_del['statusCode'] == 200
    mock_cancel.assert_called_once_with('sess99')
