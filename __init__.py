"""Lumina Plugin — general-purpose Hermes extensions.

This plugin is the home for Lumina's custom Hermes tools and helpers. It began
as the narrow http_tools plugin, but is intentionally structured so more tools
can be added without creating a new plugin for each capability.
"""

from __future__ import annotations

from . import tools

_TOOLS = [
    {
        "name": "http_request",
        "schema": tools.HTTP_REQUEST_SCHEMA,
        "handler": tools._handle_http_request,
        "check_fn": tools._check_http_available,
        "emoji": "🌐"
    },
    {
        "name": "send_notification",
        "schema": tools.SEND_NOTIFICATION_SCHEMA,
        "handler": tools._handle_send_notification,
        "check_fn": tools._check_notification_available,
        "emoji": "🔔"
    },
    {
        "name": "transmute_file_conversions",
        "schema": tools.TRANSMUTE_FILE_CONVERSIONS_SCHEMA,
        "handler": tools._handle_transmute_file_conversions,
        "check_fn": tools._check_transmute_available,
        "emoji": "🧪"
    },
    {
        "name": "transmute_convert_file",
        "schema": tools.TRANSMUTE_CONVERT_FILE_SCHEMA,
        "handler": tools._handle_transmute_convert_file,
        "check_fn": tools._check_transmute_available,
        "emoji": "🔄"
    },
    {
        "name": "avatar_get_state",
        "schema": tools.AVATAR_GET_STATE_SCHEMA,
        "handler": tools._handle_avatar_get_state,
        "check_fn": tools._check_avatar_available,
        "emoji": "✨"
    },
    {
        "name": "avatar_emit",
        "schema": tools.AVATAR_EMIT_SCHEMA,
        "handler": tools._handle_avatar_emit,
        "check_fn": tools._check_avatar_available,
        "emoji": "💃"
    }
]


def register(ctx) -> None:
    """Register all Lumina plugin tools. Called once by the plugin loader."""
    for tool_def in _TOOLS:
        ctx.register_tool(
            name=tool_def["name"],
            toolset="lumina_plugin",
            schema=tool_def["schema"],
            handler=tool_def["handler"],
            check_fn=tool_def["check_fn"],
            emoji=tool_def["emoji"],
        )
