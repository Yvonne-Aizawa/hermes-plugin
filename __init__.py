"""Lumina Plugin — embodied avatar/dashboard integration for Hermes."""

from __future__ import annotations

from . import platform, tools

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
    """Register Lumina avatar tools and the Lumina web platform adapter."""
    ctx.register_platform(
        name=platform.PLATFORM_NAME,
        label="Lumina Web",
        adapter_factory=platform.make_adapter,
        check_fn=platform._platform_available,
        validate_config=platform.validate_config,
        emoji="✨",
        platform_hint=(
            "You are chatting through the /lumina embodied browser interface. "
            "Reply naturally for a companion chat surface; assistant replies are mirrored "
            "into Lumina's avatar speech timeline by the platform adapter."
        ),
        pii_safe=True,
        allow_update_command=False,
    )

    for tool_def in _TOOLS:
        ctx.register_tool(
            name=tool_def["name"],
            toolset="lumina_plugin",
            schema=tool_def["schema"],
            handler=tool_def["handler"],
            check_fn=tool_def["check_fn"],
            emoji=tool_def["emoji"],
        )
