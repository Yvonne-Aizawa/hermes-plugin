# Session-Backed Lumina Chat History Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make `/lumina` reload history come from Hermes sessions instead of the plugin's file-backed transport queues.

**Architecture:** Keep plugin JSON files as ephemeral transport queues only: browser `POST` writes to `inbox/`, gateway drains it, adapter `send(...)` writes short-lived `outbox/` replies for browser polling. Durable UI history comes from Hermes `SessionDB` by resolving the stable Lumina gateway session key `agent:main:lumina_web:dm:dashboard:default` to the active session ID and mapping `user`/`assistant` message rows into chat records. Pending inbox/outbox messages may be overlaid on top only until SessionDB contains them.

**Tech Stack:** Python FastAPI plugin API, Hermes `gateway.session.SessionStore`/`build_session_key`, Hermes `hermes_state.SessionDB`, React/TypeScript dashboard bundle, pytest, Vite.

---

## Acceptance Criteria

- Deleting the Hermes `lumina_web` session removes old messages from the `/lumina` UI after reload.
- Reloading `/lumina` shows conversation rows from Hermes `SessionDB`, not stale files in `~/.hermes/state/lumina_plugin/chat/processed` or `outbox`.
- Fresh browser messages still appear immediately as pending/sent in the UI.
- Assistant replies still appear through the existing polling flow.
- Queue files do not become a permanent mirror-store.
- Existing avatar `speech.say` mirroring still works.

---

## Important Existing Files

- Modify: `platform.py`
  - Current queue helpers and adapter implementation.
  - Current problematic `get_chat_messages(...)` reads `processed`, `processing`, `inbox`, and `outbox`.
- Modify: `dashboard/plugin_api.py`
  - Current `GET /chat/messages` calls `get_chat_messages(...)`.
- Modify: `dashboard/src/main.ts`
  - Current chat polling/merge cursor behavior.
- Modify generated: `dashboard/dist/index.js`
  - Rebuilt by `npm run build`.
- Modify docs: `docs/lumina-web-chat-platform.md`
- Add/extend tests under temporary or repo test location depending project convention.

---

## Design Notes

### Source of truth

Use Hermes session data for durable history. The deterministic source identity in `platform.py` is:

```python
PLATFORM_NAME = "lumina_web"
LUMINA_CHAT_ID = "dashboard:default"
LUMINA_CHAT_NAME = "Lumina dashboard"
DEFAULT_USER_ID = "browser-user"
```

For DM sessions, `gateway.session.build_session_key(...)` creates:

```text
agent:main:lumina_web:dm:dashboard:default
```

The session mapping is stored by the gateway in:

```text
~/.hermes/sessions/sessions.json
```

The actual transcript lives in Hermes `SessionDB`:

```python
from hermes_state import SessionDB
messages = SessionDB().get_messages(session_id)
```

### Transport queues

Keep these directories, but stop treating them as durable history:

```text
~/.hermes/state/lumina_plugin/chat/inbox/       # pending browser messages not yet drained
~/.hermes/state/lumina_plugin/chat/processing/  # temporary claim/lock files
~/.hermes/state/lumina_plugin/chat/processed/   # optional short-term debug/dedupe only
~/.hermes/state/lumina_plugin/chat/outbox/      # browser delivery queue for assistant replies
```

### Recommended cursor model

Do not use one cursor for both DB history and transport outbox if it causes dropped messages. Prefer a response shape like:

```json
{
  "success": true,
  "messages": [...],
  "session_id": "20260514_...",
  "history_cursor": 123,
  "queue_cursor": "lumina_out_..."
}
```

But for minimal change, keep `last_message_id` as a UI-level cursor only if IDs are consistently prefixed and merge logic dedupes by ID.

---

## Task 1: Add failing tests for session-backed reload behavior

**Objective:** Prove that `/chat/messages` uses `SessionDB` history and does not depend on stale plugin queue files.

**Files:**
- Create or update: `tests/lumina_plugin/test_chat_session_history.py` if repo tests are available, otherwise create temporary tests first and later move them.
- Modify later: `dashboard/plugin_api.py`, `platform.py`

**Step 1: Write failing test for deleted session clearing UI**

Create a test that:
1. Sets `HERMES_HOME` or isolates `SessionDB` using a temp home.
2. Creates a fake Lumina session mapping for `agent:main:lumina_web:dm:dashboard:default`.
3. Inserts one user and one assistant message into `SessionDB`.
4. Writes stale files into `processed/` and `outbox/`.
5. Calls the history helper/API and confirms DB messages appear.
6. Deletes/removes the DB session or mapping.
7. Calls the history helper/API again and confirms stale queue files do **not** appear.

Pseudo-test:

```python
def test_chat_history_comes_from_sessiondb_not_queue_files(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setenv("LUMINA_CHAT_STATE_DIR", str(tmp_path / "chat_state"))

    # Arrange: create session mapping + SessionDB rows for lumina_web.
    session_id = create_lumina_session_with_messages(
        user_text="hello from db",
        assistant_text="reply from db",
    )

    # Arrange: stale transport files should not leak into durable history.
    write_processed_queue_file("stale user")
    write_outbox_queue_file("stale assistant")

    messages = get_session_backed_chat_messages()
    assert [m["text"] for m in messages] == ["hello from db", "reply from db"]

    delete_session_from_db(session_id)
    messages = get_session_backed_chat_messages()
    assert messages == []
```

**Step 2: Run test to verify failure**

Run:

```bash
/home/lumina/.hermes/hermes-agent/venv/bin/python -m pytest -q tests/lumina_plugin/test_chat_session_history.py
```

Expected: FAIL because current helper reads `processed/` and `outbox` files directly.

**Step 3: Commit test if using repo tests**

```bash
git add tests/lumina_plugin/test_chat_session_history.py
git commit -m "test: capture Lumina session-backed chat history behavior"
```

---

## Task 2: Add a helper to resolve the Lumina session ID

**Objective:** Resolve the current Lumina gateway session ID from Hermes session mapping instead of guessing.

**Files:**
- Modify: `platform.py`
- Test: same test file from Task 1

**Step 1: Add helper constants and imports**

In `platform.py`, add guarded imports near existing Hermes runtime imports:

```python
try:
    from gateway.session import build_session_key
except ImportError:
    build_session_key = None  # type: ignore[assignment]
```

Add a helper:

```python
def _lumina_session_key() -> str:
    if build_session_key and Platform is not None:
        source = SessionSource(
            platform=_lumina_platform(),
            chat_id=LUMINA_CHAT_ID,
            chat_name=LUMINA_CHAT_NAME,
            chat_type="dm",
            user_id=DEFAULT_USER_ID,
            user_name=DEFAULT_USER_NAME,
        )
        return build_session_key(source)
    return f"agent:main:{PLATFORM_NAME}:dm:{LUMINA_CHAT_ID}"
```

**Step 2: Add mapping reader**

Add:

```python
def _sessions_index_path() -> Path:
    return Path(get_hermes_home()) / "sessions" / "sessions.json"


def get_lumina_session_id() -> str | None:
    index = _safe_json_load(_sessions_index_path())
    if not index:
        return None
    entry = index.get(_lumina_session_key())
    if not isinstance(entry, dict):
        return None
    session_id = entry.get("session_id")
    return str(session_id) if session_id else None
```

**Step 3: Test helper**

Test that a temp `sessions.json` with key `agent:main:lumina_web:dm:dashboard:default` resolves the expected session ID.

**Step 4: Run focused test**

```bash
/home/lumina/.hermes/hermes-agent/venv/bin/python -m pytest -q tests/lumina_plugin/test_chat_session_history.py::test_resolves_lumina_session_id
```

Expected: PASS.

---

## Task 3: Add SessionDB transcript reader and mapper

**Objective:** Convert Hermes DB messages into Lumina chat UI records.

**Files:**
- Modify: `platform.py`
- Test: `tests/lumina_plugin/test_chat_session_history.py`

**Step 1: Add DB import helper**

Avoid importing `hermes_state` at module import time if dashboard loads without full runtime. Add lazy import:

```python
def _session_db():
    try:
        from hermes_state import SessionDB
        return SessionDB()
    except Exception:
        return None
```

**Step 2: Add content normalizer**

Hermes message content can be string or structured. Add:

```python
def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if value:
                    parts.append(str(value))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts).strip()
    if content is None:
        return ""
    return str(content)
```

**Step 3: Add row mapper**

```python
def _chat_message_from_db_row(row: dict[str, Any]) -> dict[str, Any] | None:
    role = row.get("role")
    if role not in {"user", "assistant", "system"}:
        return None
    text = _message_text(row.get("content")).strip()
    if not text:
        return None
    return {
        "id": f"session_{row.get('id')}",
        "role": role,
        "text": text,
        "chat_id": LUMINA_CHAT_ID,
        "created_at": row.get("timestamp") or "",
        "metadata": {"source": "session", "session_id": row.get("session_id")},
    }
```

**Step 4: Add session-backed helper**

```python
def get_session_chat_messages(after: str | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
    session_id = get_lumina_session_id()
    if not session_id:
        return []
    db = _session_db()
    if not db:
        return []
    rows = db.get_messages(session_id)
    messages = [m for row in rows if (m := _chat_message_from_db_row(row))]
    messages = _messages_after(messages, after)
    return messages[: max(1, min(int(limit or 100), 500))]
```

**Step 5: Run tests**

```bash
/home/lumina/.hermes/hermes-agent/venv/bin/python -m pytest -q tests/lumina_plugin/test_chat_session_history.py
```

Expected: PASS for mapper/helper tests.

---

## Task 4: Change `/chat/messages` to use SessionDB history plus pending overlay

**Objective:** Make the API return durable session messages, with only pending queue messages overlaid.

**Files:**
- Modify: `platform.py`
- Modify: `dashboard/plugin_api.py`
- Test: `tests/lumina_plugin/test_chat_session_history.py` and existing API tests

**Step 1: Replace current history function semantics**

Change `get_chat_messages(...)` in `platform.py` from this:

```python
for subdir in ("processed", "processing", "inbox", "outbox"):
    messages.extend(_load_messages_from_subdir(subdir))
```

to this:

```python
def get_chat_messages(after: str | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
    messages = get_session_chat_messages(after=None, limit=limit)
    messages.extend(get_pending_transport_messages())
    messages = _dedupe_chat_messages(_sort_chat_messages(messages))
    messages = _messages_after(messages, after)
    return messages[: max(1, min(int(limit or 100), 500))]
```

**Step 2: Only overlay truly pending files**

Implement:

```python
def get_pending_transport_messages() -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    # User messages not yet in DB.
    for subdir in ("inbox", "processing"):
        messages.extend(_load_messages_from_subdir(subdir))
    # Assistant replies not yet picked up by browser; optional. Keep outbox only
    # if SessionDB does not already contain same text/reply timestamp.
    messages.extend(_load_messages_from_subdir("outbox"))
    return messages
```

Do **not** include `processed/` in UI history.

**Step 3: Add dedupe helper**

Deduping should prefer session-backed rows over transport rows:

```python
def _dedupe_chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_ids: set[str] = set()
    result: list[dict[str, Any]] = []
    for msg in messages:
        msg_id = str(msg.get("id") or "")
        if msg_id and msg_id in seen_ids:
            continue
        if msg_id:
            seen_ids.add(msg_id)
        result.append(msg)
    return result
```

Optionally add fuzzy dedupe by `(role, text)` for outbox replies once SessionDB has the same reply.

**Step 4: Keep `dashboard/plugin_api.py` simple**

It should keep importing/calling:

```python
from ..platform import create_browser_message, get_chat_messages
```

No route contract change unless implementing separate cursors.

**Step 5: Run API tests**

```bash
/home/lumina/.hermes/hermes-agent/venv/bin/python -m pytest -q \
  tests/lumina_plugin/test_chat_session_history.py \
  /tmp/test_lumina_plugin_api_chat.py
```

Expected: PASS.

---

## Task 5: Stop making `processed/` a durable archive

**Objective:** Ensure processed user queue files do not live forever as a second history store.

**Files:**
- Modify: `platform.py`
- Test: adapter tests

**Step 1: Decide retention**

Use one of these policies:

- Preferred: delete claimed file after successful `handle_message(event)`.
- Debug-friendly: move to `processed/` but prune old files aggressively by count/age and never read them for UI.

Recommended minimal implementation: keep moving to `processed/` for debugging, but add prune.

**Step 2: Add prune helper**

```python
def prune_processed_messages(*, max_age_seconds: int = 3600, max_files: int = 100) -> None:
    root = _chat_state_dir() / "processed"
    paths = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    now = time.time()
    for index, path in enumerate(paths):
        try:
            too_old = now - path.stat().st_mtime > max_age_seconds
            too_many = index >= max_files
            if too_old or too_many:
                path.unlink()
        except OSError:
            pass
```

Call after moving a file to `processed/` in `_drain_once`.

**Step 3: Add test**

Test that `get_chat_messages()` does not read `processed/` even when files exist.

**Step 4: Run adapter tests**

```bash
/home/lumina/.hermes/hermes-agent/venv/bin/python -m pytest -q /tmp/test_lumina_web_adapter.py tests/lumina_plugin/test_chat_session_history.py
```

Expected: PASS.

---

## Task 6: Add optional clear transport endpoint, not clear history endpoint

**Objective:** Give the UI/developer a way to clear stale transport files without pretending it deletes the real conversation.

**Files:**
- Modify: `platform.py`
- Modify: `dashboard/plugin_api.py`
- Test: API tests

**Step 1: Add helper**

```python
def clear_transport_messages() -> int:
    count = 0
    root = _chat_state_dir()
    for subdir in ("inbox", "processing", "processed", "outbox"):
        for path in (root / subdir).glob("*.json"):
            try:
                path.unlink()
                count += 1
            except OSError:
                pass
    return count
```

**Step 2: Add route**

In `dashboard/plugin_api.py`:

```python
@router.delete("/chat/transport")
async def chat_clear_transport() -> dict[str, Any]:
    deleted = clear_transport_messages()
    return {"success": True, "deleted": deleted}
```

Do **not** call this “clear chat history”; it only clears transport queues.

**Step 3: Test route**

Assert JSON files are removed and session DB messages remain returned by `/chat/messages`.

---

## Task 7: Update dashboard frontend if response contract changes

**Objective:** Keep `/lumina` UI polling compatible with session-backed history.

**Files:**
- Modify: `dashboard/src/api.ts`
- Modify: `dashboard/src/main.ts`
- Generated: `dashboard/dist/index.js`

**Step 1: If keeping existing contract**

No API type changes needed beyond comments/names. Keep:

```ts
fetchLuminaChatMessages(sdk.fetchJSON, chatCursorRef.current)
```

Ensure `mergeChatMessages` handles `session_123` IDs.

**Step 2: If adding separate cursors**

Update API types:

```ts
export interface LuminaChatMessagesResponse {
  success: boolean
  messages: LuminaChatMessage[]
  history_cursor?: number
  queue_cursor?: string | null
  session_id?: string | null
}
```

Store cursors separately in refs:

```ts
const historyCursorRef = useRef<number | null>(null)
const queueCursorRef = useRef<string | null>(null)
```

**Step 3: Run TypeScript check**

```bash
cd dashboard
npx tsc --noEmit --target ES2022 --module ESNext --moduleResolution Bundler src/main.ts
```

Expected: no errors.

---

## Task 8: Update docs

**Objective:** Document the new source-of-truth model clearly.

**Files:**
- Modify: `docs/lumina-web-chat-platform.md`
- Modify: `docs/plans/2026-05-13-vrm-avatar-dashboard.md` if task tracking needs an addendum

**Step 1: Replace old wording**

Replace any claim that `/chat/messages` reads persistent history from plugin queue files.

New wording:

```markdown
The plugin queue under `~/.hermes/state/lumina_plugin/chat/` is transport state only. Durable visible conversation history comes from Hermes `SessionDB` for the stable `lumina_web` session. Deleting that Hermes session removes the conversation from `/lumina` after reload. Pending inbox/outbox files may be overlaid briefly until the gateway and browser acknowledge them.
```

**Step 2: Add troubleshooting note**

```markdown
If stale messages appear after deleting a session, check whether they are pending transport files with `DELETE /api/plugins/lumina_plugin/chat/transport` or by inspecting `~/.hermes/state/lumina_plugin/chat/`. They should not appear as durable history once the session-backed endpoint is active.
```

---

## Task 9: Full verification

**Objective:** Prove behavior end-to-end.

**Files:**
- All touched files

**Step 1: Run Python tests**

```bash
/home/lumina/.hermes/hermes-agent/venv/bin/python -m pytest -q \
  tests/lumina_plugin/test_chat_session_history.py \
  /tmp/test_lumina_plugin_api_chat.py \
  /tmp/test_lumina_web_adapter.py
```

Expected: all pass.

**Step 2: Run frontend checks**

```bash
cd /home/lumina/.hermes/plugins/lumina_plugin/dashboard
npx tsc --noEmit --target ES2022 --module ESNext --moduleResolution Bundler src/main.ts
npm run build
```

Expected: TypeScript passes and Vite build succeeds.

**Step 3: Restart dashboard**

```bash
# Find listener if needed
ss -ltnp 'sport = :9119' || true

# Restart dashboard from plugin root
~/.local/bin/hermes dashboard --host 0.0.0.0 --insecure --no-open
```

Use background/process tooling if running from Hermes.

**Step 4: Browser verification**

1. Open `http://127.0.0.1:9119/lumina`.
2. Send a test message.
3. Wait for Lumina reply.
4. Reload page.
5. Confirm both sides show from session-backed history.
6. Delete the Lumina Hermes session using the dashboard Sessions UI or CLI.
7. Reload `/lumina`.
8. Confirm old messages are gone.
9. Confirm stale JSON files in `processed/`/`outbox/` do not resurrect messages.

**Step 5: Commit**

```bash
git add platform.py dashboard/plugin_api.py dashboard/src/api.ts dashboard/src/main.ts dashboard/dist/index.js docs/lumina-web-chat-platform.md docs/plans/2026-05-14-session-backed-lumina-chat-history.md

git commit -m "fix: use Hermes sessions for Lumina chat history"
git push
```

---

## Risks / Pitfalls

- **Dashboard process staleness:** After changing plugin API routes/helpers, restart the dashboard. Otherwise the SPA shell can make API fetches look like `200 text/html` instead of JSON.
- **Session mapping drift:** If `sessions.json` is deleted but DB rows remain, the API may not know which session to show. That is acceptable: no active session mapping means no durable UI history.
- **Compression/child sessions:** If Lumina sessions can be compressed/forked, use `SessionDB.resolve_resume_session_id(session_id)` before reading messages.
- **Role noise:** `SessionDB` contains tool/system messages too. UI should show only `user`, `assistant`, and maybe intentional `system`; exclude `tool`.
- **Duplicate assistant replies:** An outbox file may contain the same reply already persisted in SessionDB. Prefer DB rows and dedupe transport overlays.
- **Deleted session UX:** If a new message is sent after session deletion, the gateway should create a fresh session; the UI should start clean except for the newly pending message.

---

## Definition of Done

- `/lumina` durable history is session-backed.
- Plugin transport files are no longer a permanent UI history source.
- Deleting the Hermes session clears reload history.
- Pending message UX still works.
- Tests cover stale queue files not leaking into history.
- Docs explain the split between SessionDB history and transport queues.
