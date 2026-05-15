# Lumina XR / Quest Event Bridge Notes

Task 10 is an architecture guardrail for the future Quest renderer. It does **not** build the Quest app yet.

## Purpose

Keep the current dashboard/avatar protocol renderer-neutral so a later Meta Quest app can render Lumina locally while Hermes remains the brain.

The current dashboard proves the important pieces first:

- stable Hermes messaging surface: `lumina_web`
- renderer-neutral avatar state snapshot
- ordered avatar event timeline
- compact internal avatar tools: `avatar_get_state` and `avatar_emit`
- VRM/VRMA asset and animation semantics

The Quest app should consume the same concepts over a transport suitable for XR/realtime use.

## Responsibility split

```text
Hermes / Lumina plugin
  - conversation brain
  - tools and memory
  - avatar state snapshot
  - ordered renderer event timeline
  - protocol/capability metadata

Dashboard renderer
  - browser VRM rendering
  - chat panel
  - subtitles and debug overlay
  - polling/SDK-authenticated plugin routes

Future Quest renderer
  - local XR rendering
  - headset/controller/gaze/spatial input capture
  - local audio playback and animation timing
  - consumes avatar state/events from a gateway
```

The Quest app should not call every internal Hermes tool directly. It should send user input/context to Hermes and render the resulting state/events locally.

## Input direction: Quest to Hermes

A future Quest client should send normalized input/context such as:

- speech transcript or text input
- optional push-to-talk / wake state
- controller actions
- gaze target or attention hints
- room/world/object context when available
- renderer identity/capabilities if needed

These inputs should enter Hermes through a gateway/platform channel or purpose-built bridge, not by bypassing the Hermes session/memory/tool pipeline.

## Output direction: Hermes to Quest

The Quest renderer should consume the same renderer-neutral output contract used by the dashboard:

```text
GET /avatar/state
GET /avatar/events?cursor=<event_id>
GET /avatar/protocol
```

Or transport-equivalent forms such as:

```text
WebSocket: avatar.state, avatar.events, avatar.protocol
WebRTC data channel: avatar.state, avatar.events, avatar.protocol
```

The payload vocabulary should remain renderer-neutral:

- `speech.say`
- `speech.pause`
- `avatar.animation`
- `avatar.expression`
- `avatar.gaze`
- `avatar.state`

Do not leak browser-only implementation details into `avatar_state.py`, `avatar_timeline.py`, or event payloads.

## Transport guidance

Current dashboard MVP:

- HTTP polling via dashboard plugin API
- good enough for browser proof-of-control
- easy to debug and test

Likely future Quest bridge:

- WebSocket for state/events once a headset renderer exists
- WebRTC data channel when realtime audio, interruption, or low-latency co-presence matters
- HTTP polling only as a fallback/debug mode

Keep the event schema stable even if the transport changes.

## Non-goals for now

This task does not include:

- Unity project setup
- OpenXR/Quest build configuration
- headset networking implementation
- realtime STT/TTS/audio streaming
- IK, hand tracking, face tracking, or spatial anchoring
- publishing a Quest app

Those belong after the dashboard control loop is solid.

## Design constraints to preserve now

- Keep avatar state/timeline files renderer-neutral.
- Keep event names semantic, not asset-path-specific.
- Keep animation names protocol-level (`wave`, `greeting`, `dance`) instead of renderer-only clip internals.
- Keep Hermes as the decision maker; renderers perform local playback.
- Keep the LLM-visible tool surface compact.

## First future Quest milestone

When it becomes time to build the Quest side, a sane first milestone is:

1. Unity + OpenXR scene with a placeholder/VRM avatar.
2. Connect to a local bridge endpoint.
3. Fetch `/avatar/protocol` and `/avatar/state`.
4. Consume `/avatar/events` over WebSocket or polling.
5. Render `speech.say` subtitles and one animation event such as `wave`.
6. Send a text transcript into a Hermes-owned channel and display the assistant response.

That would validate the XR bridge without committing to full realtime voice, IK, or spatial interaction too early.
