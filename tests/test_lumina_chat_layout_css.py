from pathlib import Path

STYLE = Path(__file__).resolve().parents[1] / 'dashboard' / 'dist' / 'style.css'


def css_block(selector: str) -> str:
    css = STYLE.read_text(encoding='utf-8')
    start = css.index(selector)
    end = css.index('}', start)
    return css[start:end]


def test_chat_panel_bounds_its_height_to_viewport():
    block = css_block('.lumina-chat-panel')

    assert 'height: min(78vh, 58rem);' in block
    assert 'max-height: min(78vh, 58rem);' in block
    assert 'min-height: 0;' in block
    assert 'overflow: hidden;' in block


def test_chat_history_is_the_only_scroll_container():
    block = css_block('.lumina-chat-history')

    assert 'flex: 1 1 auto;' in block
    assert 'min-height: 0;' in block
    assert 'max-height:' not in block
    assert 'overflow-y: auto;' in block
    assert 'overscroll-behavior: contain;' in block
    assert 'scrollbar-gutter: stable;' in block


def test_chat_message_text_wraps_instead_of_widening_layout():
    block = css_block('.lumina-chat-message p')

    assert 'overflow-wrap: anywhere;' in block
    assert 'word-break: break-word;' in block
