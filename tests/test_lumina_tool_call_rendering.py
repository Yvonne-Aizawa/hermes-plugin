from pathlib import Path

MAIN_TS = Path(__file__).resolve().parents[1] / 'dashboard' / 'src' / 'main.ts'
STYLE = Path(__file__).resolve().parents[1] / 'dashboard' / 'dist' / 'style.css'
API_TS = Path(__file__).resolve().parents[1] / 'dashboard' / 'src' / 'api.ts'


def test_lumina_chat_message_type_accepts_tool_role_and_metadata():
    api = API_TS.read_text(encoding='utf-8')
    main = MAIN_TS.read_text(encoding='utf-8')

    assert "role: 'assistant' | 'user' | 'system' | 'tool'" in main
    assert "role: 'assistant' | 'user' | 'system' | 'tool' | string" in api
    assert 'metadata?: Record<string, unknown>' in main


def test_lumina_chat_renders_tool_calls_with_distinct_label_and_details():
    main = MAIN_TS.read_text(encoding='utf-8')

    assert 'renderChatMessage(message)' in main
    assert "message.role === 'tool'" in main
    assert "kind === 'tool_call'" in main
    assert "kind === 'tool_result'" in main
    assert "Tool call" in main
    assert "Tool result" in main
    assert 'lumina-chat-tool-details' in main


def test_lumina_tool_call_css_exists():
    css = STYLE.read_text(encoding='utf-8')

    assert '.lumina-chat-message-tool' in css
    assert '.lumina-chat-tool-details' in css
    assert '.lumina-chat-tool-output' in css
