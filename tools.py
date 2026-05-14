"""Lumina avatar tools.

This plugin is intentionally focused on the embodied Lumina dashboard/avatar
surface. General utility tools live in the separate ``utility_tools`` plugin.
"""

from __future__ import annotations

import json
from typing import Any, Dict

try:
    from .avatar_state import get_state, patch_state, validate_state_patch
    from .avatar_timeline import append_events, get_events, last_event_id, protocol, validate_event
except ImportError:  # pragma: no cover - direct script/test imports
    from avatar_state import get_state, patch_state, validate_state_patch
    from avatar_timeline import append_events, get_events, last_event_id, protocol, validate_event


AVATAR_GET_STATE_SCHEMA = {
    "name": "avatar_get_state",
    "description": "Return Lumina's current renderer-neutral avatar state and protocol metadata.",
    "parameters": {
        "type": "object",
        "properties": {
            "include_events": {
                "type": "boolean",
                "default": False,
                "description": "Include currently queued avatar events in the response.",
            },
            "cursor": {
                "type": "string",
                "description": "Optional numeric event cursor; when include_events is true, only events after this id are returned.",
            },
        },
    },
}


AVATAR_EMIT_SCHEMA = {
    "name": "avatar_emit",
    "description": "Update Lumina's avatar state and/or queue ordered renderer events such as speech, expressions, gaze, and VRMA animations. Use this one compact choreography tool instead of many tiny gesture tools.",
    "parameters": {
        "type": "object",
        "properties": {
            "state": {
                "type": "object",
                "description": "Optional avatar state patch: mood, animation, expression, speaking, gesture, or intensity.",
            },
            "events": {
                "type": "array",
                "description": "Optional ordered timeline events. Supported types: speech.say, speech.pause, avatar.animation, avatar.expression, avatar.gaze, avatar.state.",
                "items": {"type": "object"},
            },
            "ttl_ms": {
                "type": "number",
                "description": "Optional event TTL in milliseconds before renderers stop receiving queued events.",
            },
        },
    },
}


def _check_avatar_available() -> tuple[bool, str]:
    """Avatar state/timeline tools are in-process and always available."""
    return True, ""


def _handle_avatar_get_state(args: Dict, **kw) -> str:
    """Return the current avatar snapshot and renderer protocol metadata."""
    try:
        include_events = bool(args.get("include_events", False))
        cursor = args.get("cursor")
        result: Dict[str, Any] = {
            "success": True,
            "state": get_state(),
            "protocol": protocol(),
            "last_event_id": last_event_id(),
        }
        if include_events:
            result["events"] = get_events(cursor)
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": f"avatar_get_state failed: {e}"})


def _handle_avatar_emit(args: Dict, **kw) -> str:
    """Patch avatar state and/or append ordered avatar timeline events."""
    try:
        if not isinstance(args, dict):
            raise ValueError("args must be an object")
        state_patch = args.get("state")
        events = args.get("events")
        ttl_ms = args.get("ttl_ms")

        if state_patch is None and not events:
            raise ValueError("provide state, events, or both")

        # Validate before mutating state or appending events so bad choreography
        # does not leave partial visible changes behind.
        if state_patch is not None:
            validate_state_patch(state_patch)
        if events is not None:
            if not isinstance(events, list):
                raise ValueError("events must be an array")
            for event in events:
                validate_event(event)

        state = patch_state(state_patch)
        appended = append_events(events, ttl_ms=ttl_ms)
        return json.dumps(
            {
                "success": True,
                "state": state,
                "events": appended,
                "last_event_id": last_event_id(),
                "protocol": protocol(),
            }
        )
    except Exception as e:
        return json.dumps({"success": False, "error": f"avatar_emit failed: {e}"})
