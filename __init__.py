"""Lumina Plugin — embodied avatar/dashboard integration for Hermes."""

from __future__ import annotations

from . import tools

_TOOLS = [
    {
        "name": "avatar_get_state",
        "schema": tools.AVATAR_GET_STATE_SCHEMA,
        "handler": tools._handle_avatar_get_state,
        "check_fn": tools._check_avatar_available,
        "emoji": "✨",
    },
    {
        "name": "avatar_emit",
        "schema": tools.AVATAR_EMIT_SCHEMA,
        "handler": tools._handle_avatar_emit,
        "check_fn": tools._check_avatar_available,
        "emoji": "💃",
    },
]


def register(ctx) -> None:
    """Register Lumina avatar tools. Called once by the plugin loader."""
    for tool_def in _TOOLS:
        ctx.register_tool(
            name=tool_def["name"],
            toolset="lumina_plugin",
            schema=tool_def["schema"],
            handler=tool_def["handler"],
            check_fn=tool_def["check_fn"],
            emoji=tool_def["emoji"],
        )
