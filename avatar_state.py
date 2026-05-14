"""Renderer-neutral Lumina avatar state helpers.

This module owns the small, boring avatar snapshot consumed by any renderer
(dashboard now, Quest or other clients later).  It intentionally avoids tying
state to a specific rendering backend.

State is persisted to a tiny JSON file so Hermes tool calls and the dashboard
plugin API can share one avatar brain even when they run in separate processes.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

MOODS = ("warm", "focused", "playful", "sleepy")
ANIMATIONS = (
    "idle",
    "walk",
    "wave",
    "greeting",
    "peace",
    "shoot",
    "spin",
    "model_pose",
    "pose",
    "squat",
    "show_full_body",
    "dance",
)
EXPRESSIONS = ("neutral", "happy", "curious", "thinking")
GESTURES = (None, "wave")

_STATE_FIELDS = {
    "mood",
    "animation",
    "expression",
    "speaking",
    "gesture",
    "intensity",
    "updated_at",
}

_DEFAULT_STATE: dict[str, Any] = {
    "mood": "warm",
    "animation": "idle",
    "expression": "neutral",
    "speaking": False,
    "gesture": None,
    "intensity": 0.5,
    "updated_at": None,
}

_state_lock = RLock()
_avatar_state: dict[str, Any] = {}


def utc_now_iso() -> str:
    """Return a compact UTC timestamp suitable for JSON snapshots."""

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _initial_state() -> dict[str, Any]:
    state = deepcopy(_DEFAULT_STATE)
    state["updated_at"] = utc_now_iso()
    return state


def _state_dir() -> Path:
    configured = os.getenv("LUMINA_AVATAR_STATE_DIR")
    if configured:
        return Path(os.path.expandvars(os.path.expanduser(configured)))
    return Path.home() / ".hermes" / "state" / "lumina_plugin"


def _state_path() -> Path:
    return _state_dir() / "avatar_state.json"


def _write_state_file(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _read_state_file() -> dict[str, Any] | None:
    path = _state_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        normalized = _initial_state()
        normalized.update(validate_state_patch(data))
        if isinstance(data.get("updated_at"), str):
            normalized["updated_at"] = data["updated_at"]
        return normalized
    except ValueError:
        return None


def _load_state() -> dict[str, Any]:
    state = _read_state_file() or _initial_state()
    _avatar_state.clear()
    _avatar_state.update(state)
    if not _state_path().exists():
        _write_state_file(state)
    return deepcopy(state)


def validate_state_patch(patch: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a partial avatar state patch.

    Raises:
        ValueError: if unknown fields or invalid values are supplied.
    """

    if not isinstance(patch, dict):
        raise ValueError("state patch must be an object")

    unknown = sorted(set(patch) - _STATE_FIELDS)
    if unknown:
        raise ValueError(f"unknown state field(s): {', '.join(unknown)}")

    validated: dict[str, Any] = {}

    if "mood" in patch:
        if patch["mood"] not in MOODS:
            raise ValueError(f"mood must be one of: {', '.join(MOODS)}")
        validated["mood"] = patch["mood"]

    if "animation" in patch:
        if patch["animation"] not in ANIMATIONS:
            raise ValueError(f"animation must be one of: {', '.join(ANIMATIONS)}")
        validated["animation"] = patch["animation"]

    if "expression" in patch:
        if patch["expression"] not in EXPRESSIONS:
            raise ValueError(f"expression must be one of: {', '.join(EXPRESSIONS)}")
        validated["expression"] = patch["expression"]

    if "speaking" in patch:
        if not isinstance(patch["speaking"], bool):
            raise ValueError("speaking must be a boolean")
        validated["speaking"] = patch["speaking"]

    if "gesture" in patch:
        if patch["gesture"] not in GESTURES:
            raise ValueError("gesture must be null or 'wave'")
        validated["gesture"] = patch["gesture"]

    if "intensity" in patch:
        value = patch["intensity"]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("intensity must be a number from 0.0 to 1.0")
        value = float(value)
        if not 0.0 <= value <= 1.0:
            raise ValueError("intensity must be from 0.0 to 1.0")
        validated["intensity"] = value

    if "updated_at" in patch:
        value = patch["updated_at"]
        if value is not None and not isinstance(value, str):
            raise ValueError("updated_at must be an ISO timestamp string or null")
        # The authoritative update timestamp is set by patch_state(); accepting
        # the key keeps full snapshots round-trippable without trusting clients.

    return validated


def get_state() -> dict[str, Any]:
    """Return a copy of the current avatar state snapshot."""

    with _state_lock:
        return _load_state()


def patch_state(patch: dict[str, Any] | None) -> dict[str, Any]:
    """Apply a validated partial state patch and return the new snapshot."""

    with _state_lock:
        state = _load_state()
        if patch is not None:
            validated = validate_state_patch(patch)
            if validated:
                state.update(validated)
        state["updated_at"] = utc_now_iso()
        _avatar_state.clear()
        _avatar_state.update(state)
        _write_state_file(state)
        return deepcopy(state)


def reset_state() -> dict[str, Any]:
    """Reset persisted and in-memory state. Intended for tests/debugging only."""

    with _state_lock:
        state = _initial_state()
        _avatar_state.clear()
        _avatar_state.update(state)
        _write_state_file(state)
        return deepcopy(state)
