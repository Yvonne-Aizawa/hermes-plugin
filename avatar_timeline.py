"""In-memory/file-backed renderer-neutral Lumina avatar timeline.

The queue is intentionally small and bounded for phase one. It provides stable
ordered event payloads that can be consumed by the dashboard today and future
renderers (for example a Meta Quest app) without changing the schema.

Events are persisted to a tiny JSON file so Hermes tool calls and the dashboard
plugin API can share one timeline even when they run in separate processes.
"""

from __future__ import annotations

import json
import os
from collections import deque
from copy import deepcopy
from pathlib import Path
from threading import RLock
from time import time
from typing import Any

try:  # Package import when loaded as lumina_plugin.avatar_timeline.
    from .avatar_state import ANIMATIONS, EXPRESSIONS, validate_state_patch, utc_now_iso
except ImportError:  # Standalone import from dashboard/plugin_api.py sys.path handling.
    from avatar_state import ANIMATIONS, EXPRESSIONS, validate_state_patch, utc_now_iso

SCHEMA_VERSION = "avatar.v1"
DEFAULT_TTL_MS = 30_000
MAX_EVENTS = 256
EVENT_TYPES = (
    "speech.say",
    "speech.pause",
    "avatar.animation",
    "avatar.expression",
    "avatar.gaze",
    "avatar.state",
)
GAZE_TARGETS = ("user", "camera", "away")

_queue_lock = RLock()
_events: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTS)


def _state_dir() -> Path:
    configured = os.getenv("LUMINA_AVATAR_STATE_DIR")
    if configured:
        return Path(os.path.expandvars(os.path.expanduser(configured)))
    return Path.home() / ".hermes" / "state" / "lumina_plugin"


def _events_path() -> Path:
    return _state_dir() / "avatar_events.json"


def _event_id_value(event_id: str | int | None) -> int | None:
    if event_id is None or event_id == "":
        return None
    try:
        value = int(event_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("cursor must be a numeric event id") from exc
    if value < 0:
        raise ValueError("cursor must be nonnegative")
    return value


def _validate_nonnegative_number(value: Any, field_name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a nonnegative number")
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative")
    return value


def _validate_intensity(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("intensity must be a number from 0.0 to 1.0")
    intensity = float(value)
    if not 0.0 <= intensity <= 1.0:
        raise ValueError("intensity must be from 0.0 to 1.0")
    return intensity


def _load_events() -> list[dict[str, Any]]:
    path = _events_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    valid = [event for event in data if isinstance(event, dict) and "id" in event]
    return valid[-MAX_EVENTS:]


def _save_events(events: list[dict[str, Any]]) -> None:
    path = _events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(events[-MAX_EVENTS:], sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _sync_from_disk() -> None:
    _events.clear()
    _events.extend(_load_events())


def _next_event_id() -> str:
    highest = 0
    for event in _events:
        try:
            highest = max(highest, int(event.get("id", 0)))
        except (TypeError, ValueError):
            continue
    return str(highest + 1)


def validate_event(event: dict[str, Any]) -> dict[str, Any]:
    """Validate a single event and return a normalized copy without id metadata."""

    if not isinstance(event, dict):
        raise ValueError("each event must be an object")

    event_type = event.get("type")
    if event_type not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {event_type!r}")

    at_ms = _validate_nonnegative_number(event.get("at_ms", 0), "at_ms")
    normalized: dict[str, Any] = {"at_ms": at_ms, "type": event_type}

    if "turn_id" in event:
        turn_id = event["turn_id"]
        if turn_id is not None and not isinstance(turn_id, str):
            raise ValueError("turn_id must be a string or null")
        normalized["turn_id"] = turn_id

    if event_type == "speech.say":
        text = event.get("text")
        if not isinstance(text, str) or not text:
            raise ValueError("speech.say requires nonempty text")
        audio_url = event.get("audio_url")
        if audio_url is not None and not isinstance(audio_url, str):
            raise ValueError("audio_url must be a string or null")
        normalized.update({"text": text, "audio_url": audio_url})

    elif event_type == "speech.pause":
        duration_ms = event.get("duration_ms", 0)
        normalized["duration_ms"] = _validate_nonnegative_number(duration_ms, "duration_ms")

    elif event_type == "avatar.animation":
        name = event.get("name")
        if name not in ANIMATIONS:
            raise ValueError(f"avatar.animation name must be one of: {', '.join(ANIMATIONS)}")
        loop = event.get("loop", False)
        if not isinstance(loop, bool):
            raise ValueError("loop must be a boolean")
        normalized.update({"name": name, "loop": loop})

    elif event_type == "avatar.expression":
        name = event.get("name")
        if name not in EXPRESSIONS:
            raise ValueError(f"avatar.expression name must be one of: {', '.join(EXPRESSIONS)}")
        normalized["name"] = name
        if "intensity" in event:
            normalized["intensity"] = _validate_intensity(event["intensity"])

    elif event_type == "avatar.gaze":
        target = event.get("target")
        if not isinstance(target, str) or not target:
            raise ValueError("avatar.gaze requires a nonempty target string")
        normalized["target"] = target

    elif event_type == "avatar.state":
        state_patch = event.get("state")
        if state_patch is None:
            state_patch = event.get("patch")
        if not isinstance(state_patch, dict):
            raise ValueError("avatar.state requires a state object")
        normalized["state"] = validate_state_patch(state_patch)

    return normalized


def purge_expired() -> None:
    """Remove events whose TTL has elapsed."""

    now = time()
    with _queue_lock:
        _sync_from_disk()
        kept = [event for event in _events if event.get("expires_at_epoch", 0) > now]
        if len(kept) != len(_events):
            _events.clear()
            _events.extend(kept)
            _save_events(kept)


def append_events(events: list[dict[str, Any]] | None, ttl_ms: int | float | None = None) -> list[dict[str, Any]]:
    """Validate and append events, preserving at_ms ordering within the batch."""

    if not events:
        return []
    if not isinstance(events, list):
        raise ValueError("events must be an array")

    ttl = DEFAULT_TTL_MS if ttl_ms is None else ttl_ms
    ttl = _validate_nonnegative_number(ttl, "ttl_ms")

    validated = [validate_event(event) for event in events]
    validated.sort(key=lambda item: item["at_ms"])

    now = time()
    created_at = utc_now_iso()
    expires_at = now + (ttl / 1000.0)
    appended: list[dict[str, Any]] = []

    with _queue_lock:
        _sync_from_disk()
        kept = [event for event in _events if event.get("expires_at_epoch", 0) > now]
        _events.clear()
        _events.extend(kept)
        for event in validated:
            stored = deepcopy(event)
            stored["id"] = _next_event_id()
            stored["created_at"] = created_at
            stored["ttl_ms"] = ttl
            stored["expires_at_epoch"] = expires_at
            _events.append(stored)
            appended.append(_public_event(stored))
        _save_events(list(_events))

    return appended


def _public_event(event: dict[str, Any]) -> dict[str, Any]:
    public = deepcopy(event)
    public.pop("expires_at_epoch", None)
    return public


def get_events(cursor: str | int | None = None) -> list[dict[str, Any]]:
    """Return non-expired events after cursor, ordered by event id."""

    cursor_value = _event_id_value(cursor)
    purge_expired()
    with _queue_lock:
        result = []
        for event in _events:
            event_id = int(event["id"])
            if cursor_value is None or event_id > cursor_value:
                result.append(_public_event(event))
        return result


def last_event_id() -> str | None:
    purge_expired()
    with _queue_lock:
        return _events[-1]["id"] if _events else None


def reset_events() -> None:
    """Clear the persisted and in-memory timeline. Intended for tests/debugging only."""

    with _queue_lock:
        _events.clear()
        _save_events([])


def protocol() -> dict[str, Any]:
    """Return the phase-one renderer protocol descriptor."""

    return {
        "schema_version": SCHEMA_VERSION,
        "event_types": list(EVENT_TYPES),
        "moods": ["warm", "focused", "playful", "sleepy"],
        "animations": list(ANIMATIONS),
        "expressions": list(EXPRESSIONS),
        "gestures": [None, "wave"],
        "gaze_targets": list(GAZE_TARGETS),
        "default_ttl_ms": DEFAULT_TTL_MS,
        "max_events": MAX_EVENTS,
    }
