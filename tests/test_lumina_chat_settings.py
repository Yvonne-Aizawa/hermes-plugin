from pathlib import Path

MAIN_TS = Path(__file__).resolve().parents[1] / 'dashboard' / 'src' / 'main.ts'
STYLE = Path(__file__).resolve().parents[1] / 'dashboard' / 'dist' / 'style.css'


def test_tool_call_mode_is_persisted_in_browser_storage():
    main = MAIN_TS.read_text(encoding='utf-8')

    assert 'type ToolCallMode = \'full\' | \'compact\' | \'none\'' in main
    assert "const LUMINA_SETTINGS_STORAGE_KEY = 'lumina.chat.settings'" in main
    assert 'loadLuminaChatSettings()' in main
    assert 'saveLuminaChatSettings' in main
    assert 'window.localStorage.getItem(LUMINA_SETTINGS_STORAGE_KEY)' in main
    assert 'window.localStorage.setItem(LUMINA_SETTINGS_STORAGE_KEY' in main


def test_settings_modal_exposes_three_tool_call_modes():
    main = MAIN_TS.read_text(encoding='utf-8')

    assert 'chatSettingsOpen' in main
    assert 'lumina-chat-settings-modal' in main
    assert 'Tool call display' in main
    assert "value: 'full'" in main
    assert "value: 'compact'" in main
    assert "value: 'none'" in main
    assert 'Full' in main
    assert 'Compact' in main
    assert 'None' in main


def test_tool_call_rendering_respects_full_compact_and_none_modes():
    main = MAIN_TS.read_text(encoding='utf-8')

    assert 'visibleChatMessages = chatMessages.filter' in main
    assert "toolCallMode !== 'none'" in main
    assert 'renderChatMessage(message, toolCallMode)' in main
    assert "toolCallMode === 'compact'" in main
    assert "toolCallMode === 'full'" in main
    assert "kind === 'tool_result'" in main


def test_settings_modal_css_exists():
    css = STYLE.read_text(encoding='utf-8')

    assert '.lumina-chat-settings-button' in css
    assert '.lumina-chat-settings-backdrop' in css
    assert '.lumina-chat-settings-modal' in css
    assert '.lumina-chat-settings-option' in css
