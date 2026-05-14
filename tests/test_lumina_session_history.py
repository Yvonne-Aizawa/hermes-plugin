import json
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

PLUGIN_PARENT = Path('/home/lumina/.hermes/plugins')
AGENT_ROOT = Path('/home/lumina/.hermes/hermes-agent')
for path in (PLUGIN_PARENT, AGENT_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hermes_state import SessionDB
from lumina_plugin.dashboard.plugin_api import router
from lumina_plugin.platform import (
    LUMINA_CHAT_ID,
    _chat_state_dir,
    _message_filename,
    _queue_outbound_message,
    create_browser_message,
    get_chat_messages,
    get_lumina_session_id,
)


def write_session_index(home: Path, session_id: str) -> None:
    sessions_dir = home / 'sessions'
    sessions_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        f'agent:main:lumina_web:dm:{LUMINA_CHAT_ID}': {
            'session_id': session_id,
            'platform': 'lumina_web',
            'chat_id': LUMINA_CHAT_ID,
            'chat_type': 'dm',
        }
    }
    (sessions_dir / 'sessions.json').write_text(json.dumps(payload), encoding='utf-8')


def create_db_session(home: Path, session_id: str = 'session-lumina') -> SessionDB:
    db = SessionDB(db_path=home / 'state.db')
    db.create_session(session_id=session_id, source='lumina_web', model='test-model')
    db.append_message(session_id, 'user', 'hello from session db')
    db.append_message(session_id, 'assistant', 'reply from session db')
    return db


def test_resolves_lumina_session_id_from_gateway_session_index(tmp_path, monkeypatch):
    home = tmp_path / 'hermes'
    monkeypatch.setenv('HERMES_HOME', str(home))
    write_session_index(home, 'session-lumina')

    assert get_lumina_session_id() == 'session-lumina'


def test_chat_history_uses_sessiondb_not_stale_processed_or_outbox(tmp_path, monkeypatch):
    home = tmp_path / 'hermes'
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setenv('LUMINA_CHAT_STATE_DIR', str(tmp_path / 'chat_state'))
    write_session_index(home, 'session-lumina')
    create_db_session(home, 'session-lumina')

    stale_user = create_browser_message('stale processed user')
    inbox_path = _chat_state_dir() / 'inbox' / _message_filename(stale_user['id'])
    inbox_path.replace(_chat_state_dir() / 'processed' / inbox_path.name)
    _queue_outbound_message('stale outbox assistant')

    messages = get_chat_messages()

    assert [m['text'] for m in messages] == ['hello from session db', 'reply from session db']
    assert all(m.get('metadata', {}).get('source') == 'session' for m in messages)

    os.remove(home / 'sessions' / 'sessions.json')
    assert get_chat_messages() == []


def test_chat_history_overlays_pending_inbox_messages_but_not_processed(tmp_path, monkeypatch):
    home = tmp_path / 'hermes'
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setenv('LUMINA_CHAT_STATE_DIR', str(tmp_path / 'chat_state'))
    write_session_index(home, 'session-lumina')
    create_db_session(home, 'session-lumina')

    create_browser_message('pending browser message')
    processed = create_browser_message('processed browser message')
    (_chat_state_dir() / 'inbox' / _message_filename(processed['id'])).replace(
        _chat_state_dir() / 'processed' / _message_filename(processed['id'])
    )

    messages = get_chat_messages()

    assert [m['text'] for m in messages] == [
        'hello from session db',
        'reply from session db',
        'pending browser message',
    ]


def test_chat_api_uses_session_history(tmp_path, monkeypatch):
    home = tmp_path / 'hermes'
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setenv('LUMINA_CHAT_STATE_DIR', str(tmp_path / 'chat_state'))
    write_session_index(home, 'session-lumina')
    create_db_session(home, 'session-lumina')

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get('/chat/messages')
    assert response.status_code == 200
    data = response.json()
    assert [m['text'] for m in data['messages']] == ['hello from session db', 'reply from session db']


def test_chat_history_includes_tool_calls_and_results_from_sessiondb(tmp_path, monkeypatch):
    home = tmp_path / 'hermes'
    monkeypatch.setenv('HERMES_HOME', str(home))
    monkeypatch.setenv('LUMINA_CHAT_STATE_DIR', str(tmp_path / 'chat_state'))
    write_session_index(home, 'session-lumina')
    db = SessionDB(db_path=home / 'state.db')
    db.create_session(session_id='session-lumina', source='lumina_web', model='test-model')
    db.append_message('session-lumina', 'user', 'please check the files')
    db.append_message(
        'session-lumina',
        'assistant',
        '',
        tool_calls=[{
            'id': 'call_search',
            'type': 'function',
            'function': {'name': 'search_files', 'arguments': '{"pattern":"*.py","target":"files"}'},
        }],
    )
    db.append_message(
        'session-lumina',
        'tool',
        '{"total_count": 2, "files": ["platform.py", "plugin_api.py"]}',
        tool_call_id='call_search',
        tool_name='search_files',
    )
    db.append_message('session-lumina', 'assistant', 'I found two Python files.')

    messages = get_chat_messages()

    assert [m['role'] for m in messages] == ['user', 'tool', 'tool', 'assistant']
    assert messages[1]['text'] == 'Calling search_files'
    assert messages[1]['metadata']['kind'] == 'tool_call'
    assert messages[1]['metadata']['tool_name'] == 'search_files'
    assert messages[1]['metadata']['tool_call_id'] == 'call_search'
    assert messages[1]['metadata']['arguments'] == {"pattern": "*.py", "target": "files"}
    assert messages[2]['text'] == '{"total_count": 2, "files": ["platform.py", "plugin_api.py"]}'
    assert messages[2]['metadata']['kind'] == 'tool_result'
    assert messages[2]['metadata']['tool_name'] == 'search_files'
    assert messages[2]['metadata']['tool_call_id'] == 'call_search'
