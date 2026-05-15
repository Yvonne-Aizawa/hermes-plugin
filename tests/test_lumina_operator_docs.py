from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / 'docs' / 'avatar-dashboard.md'
PLAN = Path(__file__).resolve().parents[1] / 'docs' / 'plans' / '2026-05-13-vrm-avatar-dashboard.md'
README = Path(__file__).resolve().parents[1] / 'README.md'


def test_operator_workflow_covers_required_runtime_steps():
    source = DOC.read_text(encoding='utf-8')
    required = [
        '## Operator workflow',
        'npm install',
        'npm run build',
        'dashboard/assets/lumina.vrm',
        'dashboard/assets/animations/vrma/',
        'hermes dashboard --stop',
        'hermes dashboard --host 0.0.0.0 --insecure --no-open',
        'systemctl --user restart hermes-gateway.service',
        '/api/plugins/lumina_plugin/avatar/state',
        '/api/plugins/lumina_plugin/chat/messages',
        'avatar_get_state',
        'avatar_emit',
        'state vs timeline',
        'dashboard renderer',
        'future Quest renderer',
        'Known limitations',
    ]
    for text in required:
        assert text in source


def test_readme_points_operators_to_workflow_doc_and_current_roadmap():
    source = README.read_text(encoding='utf-8')
    assert 'docs/avatar-dashboard.md' in source
    assert 'operator workflow' in source
    assert 'subtle liveliness' in source
    assert 'Document operator workflow' not in source


def test_plan_marks_task_12_complete():
    source = PLAN.read_text(encoding='utf-8')
    assert '## Task 12: Document operator workflow ✅' in source
    assert 'Someone should be able to clone/open the plugin' in source
    assert 'Task 12 is complete' in source
