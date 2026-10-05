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
