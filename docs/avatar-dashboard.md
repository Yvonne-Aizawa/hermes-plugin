# Lumina Avatar Dashboard

`/lumina` is Lumina's primary embodied chat surface for Hermes. It combines a browser chat panel with the VRM avatar renderer, and it is the place where avatar-specific behavior should be concentrated.

## Scope

- **Primary embodied surface:** `/lumina`
  - Receives Lumina-specific companion/chat guidance through the `lumina_web` platform registration.
  - Displays the VRM renderer, subtitles, expressions, animations, and chat history together.
  - Routes browser messages through the normal Hermes gateway/session pipeline.

- **General Hermes surfaces:** Telegram, Mattermost, CLI, and other platforms
  - Stay general-purpose by default.
  - Should not need heavy avatar-specific prompting or UI assumptions.
  - May still use `avatar_get_state` and `avatar_emit` for development/debugging when the `lumina_plugin` toolset is enabled.

This split keeps ordinary Hermes sessions clean while letting `/lumina` become richer and more embodied over time.

## Chat architecture

`/lumina` is a messaging surface, not a model provider.

```text
/lumina browser page
  -> dashboard plugin API
  -> lumina_web gateway adapter
  -> normal Hermes agent session
  -> assistant response + optional tool calls/avatar events
  -> lumina_web adapter outbox
  -> browser chat panel + avatar timeline
```

The dashboard does not call OpenAI-compatible/model-provider APIs directly. It submits messages to Hermes and renders whatever the Hermes session returns.

## Avatar control contract

The renderer-neutral avatar API lives under:

```text
GET  /api/plugins/lumina_plugin/avatar/state
POST /api/plugins/lumina_plugin/avatar/emit
GET  /api/plugins/lumina_plugin/avatar/events?cursor=<event_id>
GET  /api/plugins/lumina_plugin/avatar/protocol
```

The compact Hermes tool surface is intentionally only:

```text
avatar_get_state
avatar_emit
```

Use `avatar_emit` for speech subtitles, gestures, expressions, gaze, state patches, and VRMA animation events. Do not add one tool per gesture unless real usage proves the compact choreography tool is too awkward.

## Renderer-agnostic Quest/XR alignment

The dashboard is the current renderer, but the protocol should stay usable by a future Meta Quest app. The split is:

- **Hermes/plugin:** brain, memory, tools, state, ordered timeline, protocol metadata.
- **Dashboard renderer:** browser VRM rendering, chat panel, subtitles, debug overlay.
- **Future Quest renderer:** local XR rendering, headset/controller/gaze input, local audio and animation playback.

A Quest renderer should not call every internal Hermes tool directly. It should send normalized input/context into a Hermes-owned channel and consume renderer-facing state/events from a bridge.

Dashboard v1 uses HTTP polling. A future Quest bridge should prefer WebSocket for state/events, and WebRTC data channels once realtime audio/interruption/co-presence becomes important. The event schema should remain the same even when the transport changes.

See `docs/xr-quest-bridge.md` for the Quest bridge guardrails and non-goals.

## Session and history behavior

Durable visible chat history comes from Hermes `SessionDB` for the stable Lumina channel:

```text
platform: lumina_web
chat_id: dashboard:default
session key: agent:main:lumina_web:dm:dashboard:default
```

Plugin queue files under `~/.hermes/state/lumina_plugin/chat/` are transport state only:

- `inbox/`: browser messages waiting for gateway pickup
- `processing/`: claimed messages while the gateway handles them
- `processed/`: debug/dedupe retention, not durable UI history
- `outbox/`: browser delivery queue for assistant replies, not durable UI history

If the Hermes session is deleted, `/lumina` should reload without resurrecting stale processed/outbox files.

## Operator workflow

After changing plugin Python, platform registration, dashboard routes, or config:

```bash
hermes dashboard --stop
hermes dashboard --host 0.0.0.0 --insecure --no-open
systemctl --user restart hermes-gateway.service
```

After changing frontend code:

```bash
cd ~/.hermes/plugins/lumina_plugin/dashboard
npm run build
```

After changing tool schemas or tool registration, start a fresh Hermes session so tool availability is resampled.

## Current boundary decision

For now, avatar behavior is **scoped by convention and platform hint** rather than hard-isolated:

- `/lumina` gets the embodied platform hint from `ctx.register_platform(..., platform_hint=...)`.
- Avatar tools remain available under the `lumina_plugin` toolset for debugging and development now.
- General Telegram/Mattermost conversations should not assume the user is looking at the avatar unless they explicitly ask for avatar control.

Later, once the Lumina web surface has a dedicated tool policy, scope `avatar_get_state` and `avatar_emit` to the web interface so avatar control primarily happens from `/lumina` rather than every general-purpose Hermes surface.
