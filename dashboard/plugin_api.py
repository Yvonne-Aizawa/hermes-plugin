"""Lumina dashboard plugin — backend API routes.

Mounted at /api/plugins/lumina_plugin/ by the Hermes dashboard plugin system.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

# The Hermes dashboard can import this file either as part of the plugin package
# or as a standalone module from inside dashboard/.  Prefer relative imports when
# package context exists; fall back to a local sys.path entry for standalone load.
try:
    from ..avatar_state import get_state, patch_state
    from ..avatar_timeline import append_events, get_events, last_event_id, protocol
    from ..platform import create_browser_message, get_chat_messages
except ImportError:
    _PLUGIN_ROOT = Path(__file__).resolve().parents[1]
    if str(_PLUGIN_ROOT) not in sys.path:
        sys.path.insert(0, str(_PLUGIN_ROOT))
    try:
        from avatar_state import get_state, patch_state
        from avatar_timeline import append_events, get_events, last_event_id, protocol
        import importlib.util

        _PLATFORM_SPEC = importlib.util.spec_from_file_location("lumina_plugin_platform", _PLUGIN_ROOT / "platform.py")
        if _PLATFORM_SPEC is None or _PLATFORM_SPEC.loader is None:
            raise ImportError("Unable to load Lumina platform module")
        _PLATFORM_MODULE = importlib.util.module_from_spec(_PLATFORM_SPEC)
        _PLATFORM_SPEC.loader.exec_module(_PLATFORM_MODULE)
        create_browser_message = _PLATFORM_MODULE.create_browser_message
        get_chat_messages = _PLATFORM_MODULE.get_chat_messages
    except ImportError as exc:  # pragma: no cover - import failure should be explicit.
        raise RuntimeError(f"Unable to import Lumina avatar helpers: {exc}") from exc

router = APIRouter()


@router.get("/hello")
async def hello() -> dict[str, str]:
    """Simple greeting endpoint used by Lumina's dashboard page."""
    return {
        "message": "Hello from Lumina's plugin API ✨",
        "plugin": "lumina_plugin",
        "version": "1.0.0",
    }


@router.get("/avatar/state")
async def avatar_state() -> dict[str, Any]:
    """Return the current renderer-neutral avatar state snapshot."""

    return get_state()


@router.post("/avatar/emit")
async def avatar_emit(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """Patch avatar state and append ordered renderer-neutral timeline events.

    Expected payload:
        {"state": {...}, "events": [...], "ttl_ms": 30000}
    """

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")

    unknown = sorted(set(payload) - {"state", "events", "ttl_ms"})
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown field(s): {', '.join(unknown)}")

    try:
        state = patch_state(payload.get("state"))
        appended = append_events(payload.get("events"), payload.get("ttl_ms"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "success": True,
        "state": state,
        "events": len(appended),
        "last_event_id": appended[-1]["id"] if appended else last_event_id(),
    }


@router.get("/avatar/events")
async def avatar_events(cursor: str | None = Query(default=None)) -> dict[str, Any]:
    """Return non-expired avatar timeline events after an optional cursor."""

    try:
        events = get_events(cursor)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "success": True,
        "cursor": cursor,
        "events": events,
        "last_event_id": events[-1]["id"] if events else last_event_id(),
    }


@router.get("/avatar/protocol")
async def avatar_protocol() -> dict[str, Any]:
    """Return the phase-one renderer-neutral avatar protocol descriptor."""

    return protocol()


@router.post("/chat/messages")
async def chat_send(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
    """Queue a browser chat message for the Lumina Hermes platform adapter."""

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="payload must be a JSON object")
    unknown = sorted(set(payload) - {"text", "client_id", "user_id", "user_name", "metadata"})
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown field(s): {', '.join(unknown)}")
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is required")
    metadata = payload.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="metadata must be a JSON object")
    try:
        message = create_browser_message(
            text,
            client_id=str(payload.get("client_id") or "dashboard:default"),
            user_id=str(payload.get("user_id") or "browser-user"),
            user_name=str(payload.get("user_name") or "Browser user"),
            metadata=metadata or {},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "message": message}


@router.get("/chat/messages")
async def chat_messages(after: str | None = Query(default=None), limit: int = Query(default=100, ge=1, le=500)) -> dict[str, Any]:
    """Return browser-visible Lumina web channel conversation history."""

    messages = get_chat_messages(after, limit=limit)
    return {
        "success": True,
        "after": after,
        "messages": messages,
        "last_message_id": messages[-1]["id"] if messages else after,
    }
