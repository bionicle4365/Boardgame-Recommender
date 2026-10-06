"""
BGG Recommender - Session Route Handlers.

Handles voting session CRUD operations:
- POST /session           → create_session
- GET  /session?session_id → get_session
- POST /session/vote      → vote_session
- POST /session/close     → close_session
- DELETE /session         → delete_session
- GET  /sessions          → list_sessions
"""
import json
import base64
from datetime import datetime, timezone, timedelta
from cache_utils import logger
import sessions


def _cors_headers(content_type='application/json'):
    return {
        'Content-Type': content_type
    }


def _handle_create_session(body_params, event):
    claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
    creator_id = claims.get('sub') or claims.get('username') or body_params.get('creator_id') or 'Host'
    creator_name = body_params.get('creator_name') or claims.get('cognito:username') or claims.get('email') or body_params.get('creator_id') or 'Host'
    group_name = body_params.get('group_name', 'Game Night')
    candidates = body_params.get('candidates', [])
    duration_hours = float(body_params.get('duration_hours', 24.0))
    roster = body_params.get('roster', [])

    if not candidates:
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'candidates array is required and cannot be empty'})
        }

    try:
        session = sessions.create_session(
            creator_id=creator_id,
            group_name=group_name,
            candidates=candidates,
            duration_hours=duration_hours,
            roster=roster,
            creator_name=creator_name
        )
        return {
            'statusCode': 201,
            'headers': _cors_headers(),
            'body': json.dumps(session)
        }
    except Exception as e:
        logger.error(f"Error creating voting session: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': _cors_headers(),
            'body': json.dumps({'error': str(e)})
        }


def _handle_cafe_vote_start(body_params, event):
    """
    POST /cafe/vote/start
    Single-tap table voting session initialization prepopulated with candidate games.
    Formats group_name = "{Cafe Name} - Table {Table Number}".
    """
    claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
    
    cafe_id = body_params.get('cafe_id') or 'cafe'
    raw_table = body_params.get('table') or body_params.get('table_number') or '1'
    table_num = str(raw_table).strip()
    
    raw_name = body_params.get('cafe_name') or body_params.get('name') or cafe_id.replace('-', ' ').title()
    cafe_name = str(raw_name).strip()
    
    group_name = f"{cafe_name} - Table {table_num}"
    
    candidates = body_params.get('candidates', [])
    if not candidates:
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'candidates array is required and cannot be empty'})
        }

    # Limit to top candidate games (e.g. top 4 for quick voting consensus, or all if <= 6)
    shortlist = candidates[:6] if len(candidates) > 6 else candidates
    
    # Sanitize candidates
    sanitized_candidates = []
    for c in shortlist:
        if isinstance(c, dict):
            cand_dict = {
                'id': str(c.get('id', '')),
                'name': c.get('name', 'Unknown Game'),
                'thumbnail': c.get('thumbnail', ''),
                'rating': c.get('rating', 0),
                'complexity': c.get('complexity', 0),
                'playing_time': c.get('playing_time', 0),
                'min_players': c.get('min_players', 0),
                'max_players': c.get('max_players', 0),
                'shelf_location': c.get('shelf_location', '')
            }
            sanitized_candidates.append(cand_dict)

    duration_hours = float(body_params.get('duration_hours', 0.25))
    creator_id = claims.get('sub') or body_params.get('creator_id') or f"cafe_{cafe_id}_table_{table_num}"
    creator_name = body_params.get('creator_name') or f"Table {table_num}"

    try:
        session = sessions.create_session(
            creator_id=creator_id,
            group_name=group_name,
            candidates=sanitized_candidates,
            duration_hours=duration_hours,
            creator_name=creator_name
        )
        session['vote_url'] = f"/vote/?session_id={session['session_id']}"
        session['table_number'] = table_num
        session['cafe_id'] = cafe_id
        session['cafe_name'] = cafe_name

        return {
            'statusCode': 201,
            'headers': _cors_headers(),
            'body': json.dumps(session)
        }
    except Exception as e:
        logger.error(f"Error starting cafe table vote: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': _cors_headers(),
            'body': json.dumps({'error': str(e)})
        }



def _handle_get_session(params):
    session_id = params.get('session_id') or params.get('id')
    if not session_id:
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'session_id is required'})
        }

    try:
        session = sessions.get_session(session_id)
        if not session:
            return {
                'statusCode': 404,
                'headers': _cors_headers(),
                'body': json.dumps({'error': f"Session '{session_id}' not found"})
            }
        return {
            'statusCode': 200,
            'headers': _cors_headers(),
            'body': json.dumps(session)
        }
    except Exception as e:
        logger.error(f"Error getting voting session {session_id}: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': _cors_headers(),
            'body': json.dumps({'error': str(e)})
        }


def _handle_vote_session(body_params):
    session_id = body_params.get('session_id') or body_params.get('id')
    participant_name = body_params.get('participant_name') or body_params.get('participant')
    votes = body_params.get('votes', {})

    if not session_id or not participant_name:
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'session_id and participant_name are required'})
        }

    try:
        updated_session = sessions.submit_vote(
            session_id=session_id,
            participant_name=participant_name,
            votes_map=votes
        )
        return {
            'statusCode': 200,
            'headers': _cors_headers(),
            'body': json.dumps(updated_session)
        }
    except KeyError:
        return {
            'statusCode': 404,
            'headers': _cors_headers(),
            'body': json.dumps({'error': f"Session '{session_id}' not found"})
        }
    except ValueError as ve:
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': str(ve)})
        }
    except Exception as e:
        logger.error(f"Error submitting vote for session {session_id}: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': _cors_headers(),
            'body': json.dumps({'error': str(e)})
        }


def _handle_close_session(params):
    session_id = params.get('session_id') or params.get('id')
    if not session_id:
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'session_id is required'})
        }

    try:
        updated_session = sessions.close_session(session_id)
        return {
            'statusCode': 200,
            'headers': _cors_headers(),
            'body': json.dumps(updated_session)
        }
    except KeyError:
        return {
            'statusCode': 404,
            'headers': _cors_headers(),
            'body': json.dumps({'error': f"Session '{session_id}' not found"})
        }
    except Exception as e:
        logger.error(f"Error closing session {session_id}: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': _cors_headers(),
            'body': json.dumps({'error': str(e)})
        }


def _handle_delete_session(params):
    session_id = params.get('session_id') or params.get('id')
    if not session_id:
        return {
            'statusCode': 400,
            'headers': _cors_headers(),
            'body': json.dumps({'error': 'session_id is required'})
        }

    try:
        sessions.delete_session(session_id)
        return {
            'statusCode': 200,
            'headers': _cors_headers(),
            'body': json.dumps({'message': 'Session deleted successfully', 'session_id': session_id})
        }
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': _cors_headers(),
            'body': json.dumps({'error': str(e)})
        }


def _handle_list_sessions(query_params, event):
    claims = event.get('requestContext', {}).get('authorizer', {}).get('jwt', {}).get('claims', {})
    
    candidates = []
    if claims.get('sub'): candidates.append(claims['sub'])
    if claims.get('cognito:username'): candidates.append(claims['cognito:username'])
    if claims.get('username'): candidates.append(claims['username'])
    if claims.get('email'): candidates.append(claims['email'])

    auth_header = (event.get('headers') or {}).get('authorization') or (event.get('headers') or {}).get('Authorization', '')
    if auth_header.startswith('Bearer '):
        try:
            token_parts = auth_header.split(' ')[1].split('.')
            if len(token_parts) >= 2:
                payload_b64 = token_parts[1]
                payload_b64 += '=' * (-len(payload_b64) % 4)
                payload_json = json.loads(base64.b64decode(payload_b64).decode('utf-8'))
                for k in ['sub', 'cognito:username', 'username', 'email']:
                    if payload_json.get(k):
                        candidates.append(payload_json[k])
        except Exception as jwt_err:
            logger.debug(f"Could not parse JWT in authorization header: {jwt_err}")

    for qk in ['creator_id', 'username', 'bgg_username', 'email']:
        if query_params.get(qk):
            candidates.extend(query_params[qk].split(','))

    # Deduplicate while preserving order
    seen = set()
    unique_candidates = [c.strip() for c in candidates if c and str(c).strip() and not (c.strip() in seen or seen.add(c.strip()))]

    try:
        session_list = sessions.list_creator_sessions(unique_candidates if unique_candidates else None)
        return {
            'statusCode': 200,
            'headers': _cors_headers(),
            'body': json.dumps({'sessions': session_list})
        }
    except Exception as e:
        logger.error(f"Error listing sessions: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': _cors_headers(),
            'body': json.dumps({'error': str(e)})
        }
