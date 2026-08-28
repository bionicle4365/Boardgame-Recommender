"""
bgg_recommender/sessions.py

Asynchronous Game Night Voting & Veto Session Engine.
Handles session creation, vote submissions, deadline enforcement,
and consensus scoring with hard veto disqualification.
"""

from __future__ import annotations
import os
import json
import secrets
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Any, Optional, Union

logger = logging.getLogger(__name__)

# Scoring constants
POINTS_YES = 2
POINTS_NEUTRAL = 1
POINTS_VETO = -99

SESSIONS_TABLE_NAME = os.environ.get("SESSIONS_TABLE", "bgg-game-night-sessions")


def floats_to_decimals(obj: Any) -> Any:
    """Recursively converts all float instances to Decimal for DynamoDB storage."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: floats_to_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [floats_to_decimals(v) for v in obj]
    return obj


def decimals_to_floats(obj: Any) -> Any:
    """Recursively converts Decimal instances back to float/int for JSON serialization."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: decimals_to_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decimals_to_floats(v) for v in obj]
    return obj


def get_dynamodb_table():
    """Initializes and returns the DynamoDB Sessions table resource."""
    import boto3
    dynamodb = boto3.resource('dynamodb', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
    return dynamodb.Table(SESSIONS_TABLE_NAME)


def calculate_consensus(candidates: List[Dict[str, Any]], votes: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """
    Computes consensus score for each candidate game based on participants' votes.
    
    Scoring:
      - 👍 'yes': +2 points
      - 😐 'neutral': +1 point
      - ❌ 'veto': -99 points (Hard veto: disqualified from winning)
      
    Tie-breaking:
      - Preserves original candidate shortlist rank order in case of tied scores.
    """
    candidate_map = {str(c.get('id', '')): c for c in candidates}
    rankings = []
    vetoed_games = []

    total_voters = len(votes)

    for idx, cand in enumerate(candidates):
        cand_id = str(cand.get('id', ''))
        cand_name = cand.get('name', 'Unknown Game')
        
        score = 0
        yes_count = 0
        neutral_count = 0
        veto_count = 0
        voters_yes = []
        voters_neutral = []
        voters_veto = []

        for voter_name, voter_ballot in votes.items():
            vote = str(voter_ballot.get(cand_id, '')).lower().strip()
            if vote in ('yes', 'want', 'like', 'thumbs_up'):
                score += POINTS_YES
                yes_count += 1
                voters_yes.append(voter_name)
            elif vote in ('neutral', 'fine', 'meh', 'indifferent'):
                score += POINTS_NEUTRAL
                neutral_count += 1
                voters_neutral.append(voter_name)
            elif vote in ('veto', 'no', 'dislike', 'thumbs_down'):
                score += POINTS_VETO
                veto_count += 1
                voters_veto.append(voter_name)

        is_vetoed = veto_count > 0
        if is_vetoed:
            vetoed_games.append(cand_id)

        rankings.append({
            'id': cand_id,
            'name': cand_name,
            'original_rank': idx,
            'score': score,
            'yes_count': yes_count,
            'neutral_count': neutral_count,
            'veto_count': veto_count,
            'is_vetoed': is_vetoed,
            'voters_yes': voters_yes,
            'voters_neutral': voters_neutral,
            'voters_veto': voters_veto,
            'candidate': cand
        })

    # Sort rankings: non-vetoed first with highest score, tie-break by original_rank (ascending)
    rankings.sort(
        key=lambda x: (
            0 if not x['is_vetoed'] else 1,  # Non-vetoed first
            -x['score'],                     # Highest score first
            x['original_rank']               # Original rank tie-break
        )
    )

    winner = None
    if rankings and not rankings[0]['is_vetoed'] and (total_voters > 0 and rankings[0]['score'] > 0 or total_voters == 0):
        winner = rankings[0]['candidate']
    elif rankings and not rankings[0]['is_vetoed']:
        winner = rankings[0]['candidate']

    return {
        'total_voters': total_voters,
        'winner': winner,
        'rankings': rankings,
        'vetoed_games': vetoed_games
    }


def create_session(
    creator_id: str,
    group_name: str,
    candidates: List[Dict[str, Any]],
    duration_hours: float = 24.0,
    roster: Optional[List[str]] = None,
    creator_name: Optional[str] = None,
    table=None
) -> Dict[str, Any]:
    """
    Creates a new async voting session and persists to DynamoDB.
    """
    if not candidates:
        raise ValueError("Candidates list cannot be empty.")
    if duration_hours <= 0:
        duration_hours = 24.0

    session_id = secrets.token_hex(4)  # 8-char unique alphanumeric ID
    now = datetime.now(timezone.utc)
    closes_at = now + timedelta(hours=duration_hours)
    expires_at = int((closes_at + timedelta(days=60)).timestamp())  # TTL after 60 days

    norm_creator_id = 'Host' if (not creator_id or creator_id == 'anonymous_host') else creator_id
    norm_creator_name = 'Host' if (not creator_name or creator_name == 'anonymous_host') else creator_name

    item = {
        'session_id': session_id,
        'creator_id': norm_creator_id,
        'creator_name': norm_creator_name or norm_creator_id,
        'group_name': group_name or 'Game Night',
        'created_at': now.isoformat(),
        'closes_at': closes_at.isoformat(),
        'duration_hours': duration_hours,
        'candidates': candidates,
        'roster': roster or [],
        'votes': {},
        'expires_at': expires_at
    }

    if table is None:
        table = get_dynamodb_table()

    dynamo_item = floats_to_decimals(item)
    table.put_item(Item=dynamo_item)
    logger.info(f"Created voting session {session_id} for creator {item['creator_name']}, closes at {item['closes_at']}")

    # Calculate initial consensus
    item['is_closed'] = False
    item['consensus'] = calculate_consensus(candidates, {})
    return item


def get_session(session_id: str, table=None) -> Optional[Dict[str, Any]]:
    """
    Fetches a session by ID and computes the live consensus.
    """
    if table is None:
        table = get_dynamodb_table()

    resp = table.get_item(Key={'session_id': session_id})
    raw_item = resp.get('Item')
    if not raw_item:
        return None

    item = decimals_to_floats(raw_item)
    if item.get('creator_name') == 'anonymous_host':
        item['creator_name'] = 'Host'
    if item.get('creator_id') == 'anonymous_host':
        item['creator_id'] = 'Host'

    now = datetime.now(timezone.utc)
    closes_at = datetime.fromisoformat(item['closes_at'].replace('Z', '+00:00'))
    is_closed = now >= closes_at
    item['is_closed'] = is_closed

    # Compute consensus
    item['consensus'] = calculate_consensus(item.get('candidates', []), item.get('votes', {}))
    return item


def submit_vote(
    session_id: str,
    participant_name: str,
    votes_map: Dict[str, str],
    table=None
) -> Dict[str, Any]:
    """
    Submits or updates a participant's vote on a session if the poll is still open.
    """
    participant_name = participant_name.strip()
    if not participant_name:
        raise ValueError("Participant name cannot be empty.")

    if table is None:
        table = get_dynamodb_table()

    # Load session to check deadline
    session = get_session(session_id, table=table)
    if not session:
        raise KeyError(f"Session '{session_id}' not found.")

    if session['is_closed']:
        raise ValueError("Voting has ended for this session.")

    # Sanitize votes map
    valid_choices = {'yes', 'neutral', 'veto'}
    clean_votes = {}
    for cand in session.get('candidates', []):
        cand_id = str(cand.get('id', ''))
        choice = str(votes_map.get(cand_id, 'neutral')).lower().strip()
        if choice not in valid_choices:
            choice = 'neutral'
        clean_votes[cand_id] = choice

    # Update votes in DynamoDB
    table.update_item(
        Key={'session_id': session_id},
        UpdateExpression="SET #v.#p = :vote_data",
        ExpressionAttributeNames={
            '#v': 'votes',
            '#p': participant_name
        },
        ExpressionAttributeValues={
            ':vote_data': clean_votes
        }
    )

    logger.info(f"Recorded vote for participant '{participant_name}' in session {session_id}")

    # Return updated session with recalculated consensus
    session['votes'][participant_name] = clean_votes
    session['consensus'] = calculate_consensus(session['candidates'], session['votes'])
    return session


def list_creator_sessions(creator_id: Optional[Union[str, List[str]]] = None, table=None) -> List[Dict[str, Any]]:
    """
    Lists past and active sessions created by creator_id (or a list of candidate identifiers:
    BGG username, Cognito email, Cognito sub UUID, roster member) via GSI query or scan fallback.
    If creator_id is omitted, lists all recent sessions.
    """
    if table is None:
        table = get_dynamodb_table()

    # Normalize candidate identifiers
    candidate_ids = []
    if isinstance(creator_id, list):
        candidate_ids = [str(cid).strip() for cid in creator_id if cid]
    elif isinstance(creator_id, str) and creator_id.strip():
        candidate_ids = [cid.strip() for cid in creator_id.split(',') if cid.strip()]

    items_dict = {}

    if candidate_ids:
        for cid in candidate_ids:
            try:
                from boto3.dynamodb.conditions import Key
                resp = table.query(
                    IndexName='creator_id-created_at-index',
                    KeyConditionExpression=Key('creator_id').eq(cid),
                    ScanIndexForward=False
                )
                items_list = resp.get('Items', []) if isinstance(resp, dict) else []
                if isinstance(items_list, list):
                    for itm in items_list:
                        if isinstance(itm, dict) and 'session_id' in itm:
                            items_dict[itm['session_id']] = itm
            except Exception as e:
                logger.debug(f"GSI query for '{cid}' not found or failed: {e}")

        # Scan fallback only if GSI returned no items or to match sessions by creator_name, email, or roster membership
        if not items_dict:
            try:
                resp = table.scan()
                all_items = resp.get('Items', []) if isinstance(resp, dict) else []
                if isinstance(all_items, list):
                    cid_lower_set = {str(cid).lower() for cid in candidate_ids}
                    for itm in all_items:
                        if not isinstance(itm, dict):
                            continue
                        c_id = str(itm.get('creator_id') or '').lower()
                        c_name = str(itm.get('creator_name') or '').lower()
                        raw_roster = itm.get('roster') or []
                        roster = [str(r).lower() for r in raw_roster if r] if isinstance(raw_roster, list) else []

                        # Match if any candidate identifier matches creator_id, creator_name, or roster
                        if c_id in cid_lower_set or c_name in cid_lower_set or any(r in cid_lower_set for r in roster):
                            if 'session_id' in itm:
                                items_dict[itm['session_id']] = itm
            except Exception as scan_err:
                logger.error(f"Scan fallback failed: {scan_err}")

        items = list(items_dict.values())
        items.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
    else:
        try:
            resp = table.scan()
            raw_items = resp.get('Items', []) if isinstance(resp, dict) else []
            items = [i for i in raw_items if isinstance(i, dict)]
            items.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
            items = items[:50]
        except Exception as scan_err:
            logger.error(f"Scan failed: {scan_err}")
            items = []

    items = decimals_to_floats(items)
    now = datetime.now(timezone.utc)
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get('creator_name') == 'anonymous_host':
            item['creator_name'] = 'Host'
        if item.get('creator_id') == 'anonymous_host':
            item['creator_id'] = 'Host'
        try:
            closes_at = datetime.fromisoformat(str(item['closes_at']).replace('Z', '+00:00'))
            item['is_closed'] = now >= closes_at
        except Exception:
            item['is_closed'] = False
        item['consensus'] = calculate_consensus(item.get('candidates', []), item.get('votes', {}))

    return items


def close_session(session_id: str, table=None) -> Dict[str, Any]:
    """
    Closes a voting session immediately by setting its deadline to the current time.
    """
    if not session_id:
        raise ValueError("session_id is required.")

    if table is None:
        table = get_dynamodb_table()

    now_iso = datetime.now(timezone.utc).isoformat()
    table.update_item(
        Key={'session_id': session_id},
        UpdateExpression="SET closes_at = :now",
        ExpressionAttributeValues={':now': now_iso}
    )
    logger.info(f"Closed session {session_id} at {now_iso}")
    session = get_session(session_id, table=table)
    if not session:
        raise KeyError(f"Session '{session_id}' not found.")
    return session


def cancel_session(session_id: str, table=None) -> bool:
    """
    Cancels and deletes a voting session from DynamoDB.
    """
    if not session_id:
        raise ValueError("session_id is required.")

    if table is None:
        table = get_dynamodb_table()

    table.delete_item(Key={'session_id': session_id})
    logger.info(f"Deleted / cancelled session {session_id}")
    return True
