from pathlib import Path

VIEWER_TS = Path(__file__).resolve().parents[1] / 'dashboard' / 'src' / 'avatar-viewer.ts'
MAIN_TS = Path(__file__).resolve().parents[1] / 'dashboard' / 'src' / 'main.ts'
LIVELINESS_TS = Path(__file__).resolve().parents[1] / 'dashboard' / 'src' / 'liveliness-controller.ts'
PLAN_MD = Path(__file__).resolve().parents[1] / 'docs' / 'plans' / '2026-05-13-vrm-avatar-dashboard.md'


def test_liveliness_controller_module_defines_lightweight_behaviors():
    source = LIVELINESS_TS.read_text(encoding='utf-8')

    assert 'createLivelinessController' in source
    assert 'applyAutomaticBlink' in source
    assert 'applyBreathing' in source
    assert 'applySubtleHeadMotion' in source
    assert 'applySpeakingMouthPlaceholder' in source
    assert 'full phoneme lip sync' not in source.lower()


def test_avatar_viewer_wires_liveliness_into_render_loop_and_state():
    source = VIEWER_TS.read_text(encoding='utf-8')

    assert "from './liveliness-controller'" in source
    assert 'const liveliness = createLivelinessController()' in source
    assert 'liveliness.update(currentVrm, elapsed, delta)' in source
    assert 'liveliness.applyState(state)' in source
    assert 'liveliness.noteSpeech' in source


def test_speech_timeline_drives_viewer_speaking_placeholder():
    source = MAIN_TS.read_text(encoding='utf-8')

    assert 'viewerRef.current?.applyState({ speaking: true })' in source
    assert 'viewerRef.current?.applyState({ speaking: false })' in source


def test_plan_marks_task_11_complete_after_liveliness_work():
    source = PLAN_MD.read_text(encoding='utf-8')

    assert '## Task 11: Improve liveliness without overbuilding ✅' in source
    assert 'basic procedural liveliness' in source
