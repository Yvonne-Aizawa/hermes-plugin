# Lumina VRM Avatar Dashboard Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Turn `/lumina` into Lumina's primary embodied interface: a browser chat + Three.js/VRM avatar renderer where conversation text, subtitles, expressions, animations, and ordered multimodal action timelines feel like one coherent companion experience.

**Architecture:** Keep rendering and interaction UI in the browser dashboard plugin, while keeping avatar state/timeline orchestration in the Lumina plugin backend/tool layer. The dashboard tab renders a VRM model in WebGL and should grow a local chat panel for embodied Lumina conversations; that chat panel should act like a Hermes messaging platform/channel, similar in spirit to Telegram or Mattermost, not as a direct model/provider client. `plugin_api.py` exposes renderer-neutral avatar state plus queued avatar events; a Lumina web messaging adapter should submit browser chat messages into the normal Hermes gateway/session pipeline and deliver assistant replies back to the page with avatar choreography metadata. Normal Hermes sessions may keep avatar tools during development/debugging, but the long-term product direction is for avatar-specific tools and context to live primarily in the dedicated Lumina chat surface rather than every general-purpose session.

**Tech Stack:** Hermes dashboard plugin, FastAPI plugin routes, Hermes gateway/messaging platform adapter patterns, Hermes session/chat pipeline, Hermes tools, shared file-backed avatar state, action timeline/event queue, Three.js, `@pixiv/three-vrm`, Vite or esbuild bundle, local plugin assets (`.vrm`, `.vrma` animation clips), browser WebGL, future WebSocket/SSE bridge for dashboard and Meta Quest renderers.

**Date:** 2026-05-13

---

## Current plugin state

Existing plugin path:

```text
~/.hermes/plugins/lumina_plugin/
```

Relevant current files:

```text
plugin.yaml
__init__.py
tools.py
dashboard/manifest.json
dashboard/plugin_api.py
dashboard/dist/index.js
dashboard/dist/style.css
```

Known available local assets:

```text
assets/lumina.vrm
assets/animations/vrma/VRMA_01.vrma  # Show full body
assets/animations/vrma/VRMA_02.vrma  # Greeting
assets/animations/vrma/VRMA_03.vrma  # Peace sign
assets/animations/vrma/VRMA_04.vrma  # Shoot
assets/animations/vrma/VRMA_05.vrma  # Spin
assets/animations/vrma/VRMA_06.vrma  # Model pose
assets/animations/vrma/VRMA_07.vrma  # Squat
assets/animations/Idle.fbx
assets/animations/Waving.fbx
assets/animations/Female-Walk.fbx
```

Current dashboard route:

```text
/lumina
```

Current API route:

```text
/api/plugins/lumina_plugin/hello
```

---

## Target architecture

```text
lumina_plugin/
├── plugin.yaml
├── __init__.py
├── tools.py                         # later: avatar_* tool schemas + handlers
├── avatar_state.py                  # new: shared state model + persistence helper
├── avatar_timeline.py               # new: ordered multimodal action/event queue
├── dashboard/
│   ├── manifest.json
│   ├── plugin_api.py                # avatar state API routes
│   ├── package.json                 # frontend build deps/scripts
│   ├── src/
│   │   ├── main.ts                  # dashboard IIFE entry
│   │   ├── avatar-viewer.ts         # Three.js scene/renderer/model loop
│   │   ├── vrm-loader.ts            # VRM loading helper
│   │   ├── animation-controller.ts  # animation/expression state mapper
│   │   ├── timeline-player.ts       # ordered speech/gesture/pause event playback
│   │   └── api.ts                   # SDK.fetchJSON wrappers
│   ├── dist/
│   │   ├── index.js                 # built bundle served by Hermes
│   │   └── style.css
│   └── assets/                      # optional mirror/symlink/copy target if needed
└── assets/
    ├── lumina.vrm
    └── animations/
        ├── vrma/
        │   ├── VRMA_01.vrma       # Show full body
        │   ├── VRMA_02.vrma       # Greeting / wave candidate
        │   ├── VRMA_03.vrma       # Peace sign
        │   ├── VRMA_04.vrma       # Shoot
        │   ├── VRMA_05.vrma       # Spin
        │   ├── VRMA_06.vrma       # Model pose
        │   └── VRMA_07.vrma       # Squat
        ├── Idle.fbx               # fallback/reference only
        ├── Waving.fbx             # fallback/reference only
        └── Female-Walk.fbx        # fallback/reference only
```

Prefer serving assets from:

```text
/dashboard-plugins/lumina_plugin/../assets/...   # only if supported safely
```

If dashboard static serving cannot leave `dashboard/`, use:

```text
~/.hermes/plugins/lumina_plugin/dashboard/assets/lumina.vrm
~/.hermes/plugins/lumina_plugin/dashboard/assets/animations/vrma/*.vrma
~/.hermes/plugins/lumina_plugin/dashboard/assets/animations/*.fbx  # fallback/reference only
```

Do **not** make backend Python render the model. Python only exposes state and tool endpoints; browser JS owns rendering.

---

## Avatar state and action timeline contracts

The avatar needs **two related contracts**:

1. **State snapshot** — current durable-ish body state, useful for polling, reconnects, overlays, and renderer recovery.
2. **Action timeline** — ordered events inside one assistant turn, useful for choreography like: say hello → wave → pause → ask a question.

Start the state snapshot small and stable:

```json
{
  "mood": "warm",
  "animation": "idle",
  "expression": "neutral",
  "speaking": false,
  "gesture": null,
  "intensity": 0.5,
  "updated_at": "2026-05-13T19:45:00Z"
}
```

Allowed initial values:

- `mood`: `warm`, `focused`, `playful`, `sleepy`
- `animation`: `idle`, `wave`, `walk`
- `expression`: `neutral`, `happy`, `curious`, `thinking`
- `speaking`: boolean
- `gesture`: `null`, `wave`
- `intensity`: float from `0.0` to `1.0`

Keep this schema boring. The renderer can become fancy later; the state API should stay predictable.

### Action timeline contract

Do **not** collapse every response into one final state JSON. That cannot represent natural sequencing like “Hello” → wave → “How are you?”. Instead, Hermes should use avatar/body/speech tools during a turn, and the backend should expose an ordered event stream for renderers.

Example timeline payload:

```json
{
  "turn_id": "2026-05-13T19:45:00Z-001",
  "events": [
    {
      "id": "evt_001",
      "at_ms": 0,
      "type": "speech.say",
      "text": "Hello, darling.",
      "audio_url": null
    },
    {
      "id": "evt_002",
      "at_ms": 150,
      "type": "avatar.animation",
      "name": "wave",
      "loop": false
    },
    {
      "id": "evt_003",
      "at_ms": 900,
      "type": "avatar.expression",
      "name": "happy",
      "intensity": 0.7
    },
    {
      "id": "evt_004",
      "at_ms": 1300,
      "type": "speech.say",
      "text": "How are you feeling?",
      "audio_url": null
    }
  ]
}
```

Allowed initial event types:

- `speech.say`: text and optional generated audio URL
- `speech.pause`: timed silence / beat
- `avatar.animation`: play `idle`, `wave`, or `walk`
- `avatar.expression`: set `neutral`, `happy`, `curious`, or `thinking`
- `avatar.gaze`: look at `user`, `camera`, `away`, or future target id
- `avatar.state`: patch the state snapshot

Renderer behavior:

- Dashboard and future Quest app consume the same timeline semantics.
- Renderers execute events in order by `at_ms`, not by arrival timing alone.
- State snapshots remain the fallback; timeline events provide liveliness and turn choreography.

Mental model:

```text
Hermes reasoning
  -> tool calls: speech.say, avatar.wave, speech.pause, speech.say
  -> backend appends timeline events and updates state
  -> dashboard / Quest renderer receives ordered events
  -> renderer performs speech + gestures locally
```

This keeps the AI/tool layer authoritative while letting each renderer handle embodiment locally.

### Renderer-neutral API contract

Create the API as a **renderer protocol**, not as a dashboard-only API. The dashboard and the future Meta Quest app should consume the same semantic contract:

```text
Hermes tools / Lumina brain
  -> avatar_state.py + avatar_timeline.py
  -> renderer-neutral API
  -> dashboard renderer OR Quest renderer
```

Recommended route shape:

```text
GET  /api/plugins/lumina_plugin/avatar/state
POST /api/plugins/lumina_plugin/avatar/emit
GET  /api/plugins/lumina_plugin/avatar/events?cursor=<event_id>
GET  /api/plugins/lumina_plugin/avatar/protocol
```

Route responsibilities:

- `GET /avatar/state`: current state snapshot for any renderer.
- `POST /avatar/emit`: internal/admin path used by Hermes tools to patch state and append timeline events.
- `GET /avatar/events?cursor=...`: renderer-facing event feed. Dashboard can poll/SSE first; Quest can later use WebSocket with the same event objects.
- `GET /avatar/protocol`: exposes supported schema version, event types, animation names, expression names, TTL policy, and renderer hints.

The dashboard may keep using dashboard-authenticated `SDK.fetchJSON(...)`, but the data it receives should be identical to what a Quest gateway receives. If Quest cannot use dashboard session auth, expose a separate authenticated transport later, but keep the payload schema the same.

---

## Task 1: Verify dashboard asset serving constraints

**Objective:** Confirm where VRM/FBX assets must live for Hermes dashboard plugins.

**Files:**

- Read: `dashboard/manifest.json`
- Read: Hermes dashboard server code if needed: `~/.hermes/hermes-agent/hermes_cli/web_server.py`
- Possibly create: `dashboard/assets/.gitkeep`

**Steps:**

1. Confirm `/dashboard-plugins/lumina_plugin/<path>` only serves files under `dashboard/`.
2. If true, copy or symlink model assets into `dashboard/assets/`.
3. Prefer copying for portability unless large binary duplication becomes annoying.

**Verification:**

Run dashboard and verify asset URL returns `200` with dashboard token:

```bash
curl -I http://127.0.0.1:9119/dashboard-plugins/lumina_plugin/assets/lumina.vrm
```

Expected: `200 OK` when requested from the dashboard/browser session.

**Commit:**

```bash
git add dashboard/assets .gitignore
 git commit -m "chore: prepare avatar dashboard assets"
```

---

## Task 2: Add frontend build setup

**Objective:** Introduce a real JS build step so Three.js and VRM dependencies can be bundled into `dashboard/dist/index.js`.

**Files:**

- Create: `dashboard/package.json`
- Create: `dashboard/src/main.ts`
- Create: `dashboard/src/avatar-viewer.ts`
- Modify: `dashboard/dist/index.js` after build

**Dependencies:**

```bash
cd ~/.hermes/plugins/lumina_plugin/dashboard
npm install three @pixiv/three-vrm
npm install -D vite typescript
```

**Suggested `package.json`:**

```json
{
  "private": true,
  "type": "module",
  "scripts": {
    "build": "vite build"
  },
  "dependencies": {
    "@pixiv/three-vrm": "latest",
    "three": "latest"
  },
  "devDependencies": {
    "typescript": "latest",
    "vite": "latest"
  }
}
```

**Build output requirement:**

The built file must remain loadable as a normal dashboard plugin script from:

```text
/dashboard-plugins/lumina_plugin/dist/index.js
```

Use Vite library/IIFE mode or esbuild IIFE mode. Do not require native ESM imports from the plugin page unless Hermes plugin loader is changed to support `type="module"`.

**Verification:**

```bash
cd ~/.hermes/plugins/lumina_plugin/dashboard
npm run build
```

Expected: `dashboard/dist/index.js` exists and contains bundled Three.js/VRM code.

**Commit:**

```bash
git add dashboard/package.json dashboard/package-lock.json dashboard/src dashboard/dist/index.js
 git commit -m "build: add avatar dashboard frontend bundle"
```

---

## Task 3: Replace hello-world UI with WebGL canvas shell

**Objective:** Render a dashboard page with a full-height avatar canvas and status overlay.

**Files:**

- Modify: `dashboard/src/main.ts`
- Modify: `dashboard/src/avatar-viewer.ts`
- Modify: `dashboard/dist/style.css`

**Implementation notes:**

- Register the plugin component with:

```js
window.__HERMES_PLUGINS__.register("lumina_plugin", LuminaAvatarPage)
```

- The React component should render:
  - a canvas container
  - a small status card: model loaded / API connected / current animation
  - a fallback error message if WebGL or model loading fails

**Verification:**

1. Build frontend.
2. Restart dashboard.
3. Open `/lumina`.
4. Confirm the old hello-world card is gone and the canvas shell appears.

**Commit:**

```bash
git add dashboard/src dashboard/dist
 git commit -m "feat: replace Lumina page with avatar canvas"
```

---

## Task 4: Load and render `lumina.vrm`

**Objective:** Display the VRM model in the canvas with camera, lights, and animation loop.

**Files:**

- Modify: `dashboard/src/vrm-loader.ts`
- Modify: `dashboard/src/avatar-viewer.ts`
- Use asset: `dashboard/assets/lumina.vrm`

**Implementation notes:**

Use Three.js pieces:

- `WebGLRenderer`
- `PerspectiveCamera`
- `Scene`
- `Clock`
- `DirectionalLight`
- `AmbientLight`
- `GLTFLoader`
- `VRMLoaderPlugin` from `@pixiv/three-vrm`

Basic loop:

```ts
function animate() {
  requestAnimationFrame(animate)
  const delta = clock.getDelta()
  currentVrm?.update(delta)
  renderer.render(scene, camera)
}
```

**Verification:**

- `/lumina` shows the 3D model.
- Browser console has no fatal errors.
- Resize works without distorting the canvas.

**Commit:**

```bash
git add dashboard/src dashboard/dist dashboard/assets/lumina.vrm
 git commit -m "feat: render Lumina VRM model"
```

---

## Task 5: Add avatar state and timeline backend

**Objective:** Replace the simple `/hello` API with avatar state and ordered timeline endpoints while preserving `/hello` as a harmless smoke test.

**Files:**

- Create: `avatar_state.py`
- Create: `avatar_timeline.py`
- Modify: `dashboard/plugin_api.py`

**Routes:**

```text
GET  /api/plugins/lumina_plugin/avatar/state
POST /api/plugins/lumina_plugin/avatar/emit
GET  /api/plugins/lumina_plugin/avatar/events?cursor=<event_id>
GET  /api/plugins/lumina_plugin/avatar/protocol

# Optional dashboard/debug aliases only if useful later:
POST /api/plugins/lumina_plugin/avatar/state
GET  /api/plugins/lumina_plugin/avatar/timeline
```

**State storage:**

For MVP, in-memory module state and an in-memory bounded event queue are fine. Later move to profile-aware file storage or per-session queues if needed.

**Verification:**

Use dashboard token or `TestClient`:

```python
from fastapi.testclient import TestClient
import hermes_cli.web_server as ws

client = TestClient(ws.app)
headers = {ws._SESSION_HEADER_NAME: ws._SESSION_TOKEN}
assert client.get('/api/plugins/lumina_plugin/avatar/state', headers=headers).status_code == 200
assert client.get('/api/plugins/lumina_plugin/avatar/events', headers=headers).status_code == 200
assert client.get('/api/plugins/lumina_plugin/avatar/protocol', headers=headers).status_code == 200
```

**Commit:**

```bash
git add avatar_state.py avatar_timeline.py dashboard/plugin_api.py
 git commit -m "feat: add Lumina avatar state and timeline API"
```

---

## Task 6: Connect frontend to avatar state

**Objective:** Make the renderer react to backend state.

**Files:**

- Create: `dashboard/src/api.ts`
- Create: `dashboard/src/timeline-player.ts`
- Modify: `dashboard/src/main.ts`
- Modify: `dashboard/src/animation-controller.ts`

**MVP behavior:**

- Poll `GET /api/plugins/lumina_plugin/avatar/state` every 1 second for fallback/current snapshot.
- Poll `GET /api/plugins/lumina_plugin/avatar/events?cursor=<last_event_id>` every 250ms for MVP event playback, or use SSE/WebSocket later.
- Fetch `GET /api/plugins/lumina_plugin/avatar/protocol` on startup so the renderer knows supported event types, animations, expressions, and schema version.
- Display current state in the overlay.
- Map state fields to simple visual behavior:
  - `animation=idle`: idle stance
  - `animation=wave`: trigger wave animation once if available
  - `expression=happy`: set VRM expression preset if available
- Execute timeline events in order by `at_ms`:
  - `speech.say`: display subtitle now; later play TTS audio URL
  - `speech.pause`: delay the next timeline event
  - `avatar.animation`: trigger animation
  - `avatar.expression`: set expression

**Verification:**

1. Open `/lumina`.
2. Call state update endpoint from TestClient or dashboard dev console.
3. Confirm overlay changes within 1 second.
4. Append a timeline containing `speech.say` → `avatar.animation:wave` → `speech.say`.
5. Confirm the dashboard performs the events in order, not just as one final state.

**Commit:**

```bash
git add dashboard/src dashboard/dist
 git commit -m "feat: bind avatar renderer to plugin state and timeline"
```

---

## Task 7: Add preset VRMA animation support ✅

**Objective:** Load and trigger the local VRM Animation (`.vrma`) motion pack before attempting FBX retargeting.

**Files:**

- Modify: `dashboard/package.json`
- Create: `dashboard/src/vrma-animation-controller.ts`
- Modify: `dashboard/src/avatar-viewer.ts`
- Modify: `avatar_state.py`
- Use assets:
  - `dashboard/assets/animations/vrma/VRMA_01.vrma` — Show full body
  - `dashboard/assets/animations/vrma/VRMA_02.vrma` — Greeting
  - `dashboard/assets/animations/vrma/VRMA_03.vrma` — Peace sign
  - `dashboard/assets/animations/vrma/VRMA_04.vrma` — Shoot
  - `dashboard/assets/animations/vrma/VRMA_05.vrma` — Spin
  - `dashboard/assets/animations/vrma/VRMA_06.vrma` — Model pose
  - `dashboard/assets/animations/vrma/VRMA_07.vrma` — Squat
- Preserve fallback/reference assets:
  - `dashboard/assets/animations/Idle.fbx`
  - `dashboard/assets/animations/Waving.fbx`
  - `dashboard/assets/animations/Female-Walk.fbx`

**Dependencies:**

```bash
cd ~/.hermes/plugins/lumina_plugin/dashboard
npm install @pixiv/three-vrm-animation
```

**Implementation notes:**

- Prefer `VRMAnimationLoaderPlugin` + `createVRMAnimationClip` from `@pixiv/three-vrm-animation`.
- Load `.vrma` files through `GLTFLoader` similarly to the VRM loader, then convert them into `THREE.AnimationClip`s bound to the current VRM.
- Use a single `THREE.AnimationMixer` for the VRM scene.
- Keep an animation registry mapping semantic names to files:
  - `show_full_body` → `VRMA_01.vrma`
  - `greeting` / `wave` → `VRMA_02.vrma`
  - `peace` → `VRMA_03.vrma`
  - `shoot` → `VRMA_04.vrma`
  - `spin` → `VRMA_05.vrma`
  - `model_pose` → `VRMA_06.vrma`
  - `squat` → `VRMA_07.vrma`
- Map existing protocol animation names conservatively:
  - `idle`: keep current static/procedural idle until a dedicated idle `.vrma` exists.
  - `wave`: play `greeting` / `VRMA_02.vrma` once, then return to idle.
  - `walk`: leave unsupported for now unless a VRMA walk clip is added.
- `GET /avatar/protocol` now exposes the VRMA-backed animation names so renderer clients can emit them directly.

**Implemented:**

- Added `@pixiv/three-vrm-animation`.
- Added a VRMA controller using `VRMAnimationLoaderPlugin`, `createVRMAnimationClip`, and a single `THREE.AnimationMixer` bound to the loaded VRM scene.
- Wired `avatar.animation` events and state updates to real VRMA clip playback where a preset exists.
- Kept `idle` and `walk` safe no-ops until dedicated clips exist.
- Extended backend animation validation/protocol names for `greeting`, `peace`, `shoot`, `spin`, `model_pose`, `pose`, and `squat`.

**Important risk:**

VRMA should be more reliable than FBX for VRM avatars, but real files can still vary by spec version. If a `.vrma` fails to load, verify it has GLB magic bytes (`glTF`) and that `@pixiv/three-vrm-animation` accepts its `specVersion`. Keep FBX retargeting as a fallback/reference path only; do not start with FBX unless VRMA fails.

**Verification:**

- `npm run build` succeeds.
- The bundle contains `VRMAnimationLoaderPlugin` and no top-level ESM `import`/`export`.
- `/dashboard-plugins/lumina_plugin/assets/animations/vrma/VRMA_02.vrma` returns bytes starting with `glTF`.
- Triggering `animation=wave` or an `avatar.animation` event named `wave` plays the greeting motion once and returns to idle/static stance.
- Unsupported names such as `walk` fail gracefully or no-op visibly in the overlay rather than throwing fatal console errors.

**Commit:**
```bash
git add dashboard/package.json dashboard/package-lock.json dashboard/src dashboard/dist dashboard/assets/animations assets/animations/vrma docs/plans/2026-05-13-vrm-avatar-dashboard.md
 git commit -m "feat: add Lumina VRMA animation assets"
```


---

## Task 8: Add Hermes avatar control tools ✅

**Status:** Completed in Phase 8. `avatar_get_state` and `avatar_emit` are registered under the `lumina_plugin` toolset, reuse `avatar_state.py` + `avatar_timeline.py`, and return JSON strings for Hermes tool calls. A fresh Hermes session and the dashboard now share file-backed avatar state/events under `~/.hermes/state/lumina_plugin/`, so tool calls from one process are visible to the dashboard process after plugin code has been restarted/reloaded.

**Objective:** Allow Hermes/Lumina to control the avatar from chat/tool calls.

**Files:**

- Modify: `tools.py`
- Modify: `__init__.py`
- Modify: `plugin.yaml`
- Reuse: `avatar_state.py`
- Reuse: `avatar_timeline.py`

**Tool budget:**

Keep the LLM-visible surface tiny to avoid polluting every session's tool context. Do **not** register one tool per gesture unless a strong need appears later.

**MVP tools:**

```text
avatar_get_state
avatar_emit
```

**Why only two tools:**

- `avatar_get_state` is the read/debug/recovery tool.
- `avatar_emit` is the single write/choreography tool. It accepts either a state patch, an ordered event sequence, or both.
- Specific actions like say, pause, wave, expression, gaze, and walk are **event types inside `avatar_emit`**, not separate LLM tools.
- This keeps the tool list compact while preserving expressive turns like `speech.say` → `avatar.animation:wave` → `speech.say`.

**Handler pattern:**

- Use `(args, **kw)` signatures.
- Return JSON strings with `json.dumps(...)`.
- Register under toolset `lumina_plugin`.
- `avatar_emit` should append timeline events and update the state snapshot when appropriate.
- Keep validation strict: reject unknown event types, unknown animation names, and invalid `at_ms` ordering.
- Persist state and timeline events to shared storage rather than process-local globals. The dashboard API and Hermes tool calls may run in separate Python processes, so both layers must read/write the same file-backed store.
- Current shared store path: `~/.hermes/state/lumina_plugin/` unless `LUMINA_AVATAR_STATE_DIR` overrides it for tests.

**Example schema:**

```python
AVATAR_EMIT_SCHEMA = {
    "name": "avatar_emit",
    "description": "Update Lumina's avatar state and/or queue an ordered avatar action timeline. Use this for speech subtitles, gestures, expressions, gaze, and animation choreography.",
    "parameters": {
        "type": "object",
        "properties": {
            "state": {
                "type": "object",
                "description": "Optional patch to the current avatar state snapshot.",
                "additionalProperties": True
            },
            "events": {
                "type": "array",
                "description": "Optional ordered timeline events for this assistant turn.",
                "items": {
                    "type": "object",
                    "properties": {
                        "at_ms": {"type": "integer", "minimum": 0},
                        "type": {
                            "type": "string",
                            "enum": [
                                "speech.say",
                                "speech.pause",
                                "avatar.animation",
                                "avatar.expression",
                                "avatar.gaze",
                                "avatar.state"
                            ]
                        }
                    },
                    "required": ["at_ms", "type"],
                    "additionalProperties": True
                }
            },
            "ttl_ms": {
                "type": "integer",
                "description": "How long timeline events may wait for a renderer before expiring.",
                "default": 30000
            }
        }
    }
}
```

**Example `avatar_emit` input:**

```json
{
  "state": {"mood": "warm", "expression": "happy"},
  "events": [
    {"at_ms": 0, "type": "speech.say", "text": "Hello."},
    {"at_ms": 150, "type": "avatar.animation", "name": "wave", "loop": false},
    {"at_ms": 1200, "type": "speech.say", "text": "How are you?"}
  ],
  "ttl_ms": 30000
}
```

**Non-MVP / avoid unless needed:**

Do not initially add separate tools such as `avatar_say`, `avatar_pause`, `avatar_play_animation`, `avatar_set_expression`, `avatar_queue_event`, or `avatar_clear_timeline`. They are convenient for humans, but expensive in LLM context. Add them later only if real usage shows `avatar_emit` is too awkward.

**Verification:**

- [x] Plugin imports cleanly.
- [x] Registry contains only the compact MVP avatar tools: `avatar_get_state` and `avatar_emit`.
- [x] Tool handlers can read state, validate/patch state, append ordered events, and reject invalid animation names without appending partial events.
- [x] Fresh Hermes session can call `avatar_emit` after plugin reload/session restart.
- [x] Dashboard changes after a state patch in `avatar_emit`.
- [x] Dashboard plays ordered speech/gesture events after an `avatar_emit` sequence.
- [x] Cross-process regression verified: CLI/tool process writes state/events and dashboard/API process reads the same file-backed state.
- [x] Operational caveat captured: plugin code changes require dashboard/gateway restart or reload; normal future `avatar_emit` calls do not.

**Commit:**

```bash
git add tools.py __init__.py plugin.yaml avatar_state.py avatar_timeline.py
 git commit -m "feat: add compact Lumina avatar emit tool"
```

---

## Embodied chat direction: Lumina as a Hermes messaging surface

The `/lumina` chatbox should be a **Hermes-native messaging surface**, not a direct OpenAI/model API client and not a new model provider. Treat it like a local browser messaging platform: user messages originate in the dashboard page, enter the normal Hermes message/session pipeline, and assistant replies are delivered back to the page with optional avatar timeline events.

Target mental model:

```text
/lumina browser page
  -> Lumina web chat transport
  -> Hermes gateway/message dispatcher
  -> normal Hermes agent session
  -> assistant response + tool calls/avatar events
  -> Lumina web chat transport
  -> dashboard message list + subtitles + VRM timeline
```

### Why platform-style instead of provider-style

- Providers are for model backends; `/lumina` is a chat surface.
- The chatbox should inherit Hermes memory, skills, tools, profiles, model routing, and session history.
- The dashboard should not duplicate model/provider configuration or call OpenAI-compatible APIs directly.
- This keeps Telegram, Mattermost, CLI, and `/lumina` conceptually aligned: different surfaces, same Hermes brain.

### Desired Lumina web channel behavior

- Stable platform/source identity, for example `lumina_web` or `lumina:dashboard:default`.
- Stable user/channel identity so sessions can resume instead of creating a new brain every page refresh.
- Browser client posts user text and receives assistant messages through a dashboard-authenticated route or WebSocket/SSE stream.
- Assistant message text should be mirrored into avatar timeline events, at minimum `speech.say` subtitles.
- Later, the assistant or adapter can add expression/animation events without requiring all normal sessions to carry avatar-specific instructions.

### Layout target for the chatbox

Desktop layout:

```text
┌───────────────────────────────┬──────────────────────────┐
│                               │ Chat                     │
│         VRM Avatar            │ ┌──────────────────────┐ │
│                               │ │ user/assistant msgs  │ │
│                               │ └──────────────────────┘ │
│                               │ [message input      ↵]  │
├───────────────────────────────┴──────────────────────────┤
│ subtitle / current speech line                            │
└───────────────────────────────────────────────────────────┘
```

Responsive fallback: avatar on top, chat below. Future Quest/browser-XR layout can make the avatar full-screen and render chat as an overlay panel.

### Implementation discovery result

Hermes already supports plugin-registered gateway platforms via `PluginContext.register_platform(...)` and `gateway.platform_registry.PlatformEntry`. `GatewayRunner._create_adapter(...)` checks the plugin registry before built-in adapters, and `gateway.config.Platform` accepts plugin platform names dynamically. That means Lumina can become a real Hermes messaging surface without adding a new model provider and without calling OpenAI/provider APIs from the dashboard plugin.

Chosen path for the real chat loop:

- Add a `lumina_web` platform adapter inside this plugin.
- Register it from `__init__.py` with `ctx.register_platform(name="lumina_web", ...)`.
- Implement the adapter as a small local HTTP/SSE bridge running in the Hermes gateway process.
- Keep the browser talking to dashboard-authenticated plugin routes; those routes proxy to the local `lumina_web` adapter instead of exposing an unauthenticated browser port.
- Use the normal gateway `MessageEvent` + `SessionSource` path so Hermes sessions, memory, skills, tools, approvals, and final response delivery remain native.

The existing API server adapter is useful reference material, especially `/v1/runs` and SSE events, but it should not be the primary Lumina transport because it presents as `api_server`, not as a dedicated Lumina messaging surface. A temporary dashboard stub remains acceptable for Task 9B UI work only.

---

## Task 9A: Investigate Hermes messaging platform adapter path

**Objective:** Find the correct Hermes-native way for `/lumina` to submit browser messages as a platform/channel, similar to Telegram or Mattermost, without calling a model/provider API directly.

**Files inspected:**

- `~/.hermes/hermes-agent/gateway/platforms/base.py`
  - `BasePlatformAdapter`
  - `MessageEvent`
  - `MessageType`
  - `SendResult`
- `~/.hermes/hermes-agent/gateway/session.py`
  - `SessionSource`
  - `SessionContext`
- `~/.hermes/hermes-agent/gateway/platform_registry.py`
  - `PlatformEntry`
  - plugin platform registry
- `~/.hermes/hermes-agent/hermes_cli/plugins.py`
  - `PluginContext.register_platform(...)`
- `~/.hermes/hermes-agent/gateway/run.py`
  - `GatewayRunner._create_adapter(...)`
  - `_handle_message_with_agent(...)` / message dispatch path
- `~/.hermes/hermes-agent/gateway/platforms/api_server.py`
  - `/v1/runs`, `/v1/runs/{run_id}/events`, session headers, SSE event shape
- `~/.hermes/hermes-agent/hermes_cli/web_server.py`
  - dashboard plugin API mounting under `/api/plugins/<name>/`

**Chosen integration point:**

Implement `lumina_web` as a plugin-registered gateway platform adapter.

**New/modified plugin files:**

- Create: `platform.py`
  - define `LuminaWebAdapter(BasePlatformAdapter)`
  - define `check_lumina_web_requirements() -> bool`
  - local endpoints inside the gateway process:
    - `GET /health`
    - `POST /messages`
    - `GET /events` or `GET /events/{channel_id}` as SSE or long-poll
  - incoming messages create:
    - `SessionSource(platform=Platform("lumina_web"), chat_id="dashboard:default", chat_type="dm", user_id="dashboard", user_name="Yvonne")`
    - `MessageEvent(text=..., message_type=MessageType.TEXT, source=source, message_id=...)`
  - call `self._message_handler(event)` so Hermes owns the run
  - `send(chat_id, content, ...)` appends assistant output to a per-channel queue/store and mirrors `content` into `speech.say` avatar events
- Modify: `__init__.py`
  - keep avatar tools
  - add `ctx.register_platform(name="lumina_web", label="Lumina Web", adapter_factory=lambda cfg: LuminaWebAdapter(cfg), check_fn=check_lumina_web_requirements, emoji="✨", pii_safe=True, platform_hint="Browser-local Lumina embodied chat")`
- Modify: `plugin.yaml`
  - advertise platform capability if the manifest supports it; otherwise rely on runtime registration
- Modify: `dashboard/plugin_api.py`
  - add authenticated proxy routes:
    - `POST /chat/messages` -> local `lumina_web` adapter `POST /messages`
    - `GET /chat/events` -> local `lumina_web` adapter events endpoint, or polling fallback
    - `GET /chat/health` -> adapter health
- Modify: `dashboard/src/api.ts`
  - add chat send/events helpers using dashboard `SDK.fetchJSON(...)` / stream helper
- Modify: `dashboard/src/main.ts`
  - use chat helpers from the UI skeleton

**Configuration shape:**

Add/enable a gateway platform in Hermes config once implemented:

```yaml
platforms:
  lumina_web:
    enabled: true
    extra:
      host: 127.0.0.1
      port: 8765
      channel_id: dashboard:default
```

Keep browser traffic on dashboard routes; do not expose the Lumina adapter directly beyond loopback unless a proper auth layer is added.

**Channel/session identity:**

- Platform: `lumina_web`
- Default chat/channel: `dashboard:default`
- Stable memory/session key target: `lumina_web:dashboard:default`
- Browser tab IDs may be used later for multi-window routing, but v1 should deliberately use one stable default channel so refreshes resume the same embodied conversation.

**Delivery choice:**

- v1: polling or SSE from dashboard plugin route to browser.
- Preferred if easy: SSE, because API server already proves the event shape works for streaming/delta-style UX.
- Fallback: short polling against a file-backed/queue-backed chat event store, matching the avatar timeline’s durable cross-process pattern.

**Acceptance criteria update:**

- `hermes platforms` / gateway startup can discover `lumina_web` as a plugin platform.
- Sending a message through the adapter enters the normal gateway message handler, not a direct model call.
- Assistant replies arrive through `LuminaWebAdapter.send(...)` and appear in browser chat.
- The same reply text is emitted as `speech.say` for subtitles.
- Dashboard routes are only an authenticated proxy/UI bridge; they are not the chat brain.

**Commit:**

```bash
git add docs/plans/2026-05-13-vrm-avatar-dashboard.md
 git commit -m "docs: plan Lumina web chat platform adapter"
```

---

## Task 9B: Build dashboard chatbox UI skeleton ✅

**Status:** Completed. `/lumina` now uses a split desktop layout with the VRM avatar stage on the left and a chat panel on the right, stacking to a single column on narrower screens. The chat panel keeps local stub history, input, send/loading/error UI, and uses the existing avatar emit route to add a stub `speech.say` subtitle event; it does not call any model/provider API directly.

**Objective:** Add the visible chat panel to `/lumina` without depending on the final Hermes platform adapter yet.

**Files:**

- Modify: `dashboard/src/main.ts`
- Modify: `dashboard/src/api.ts`
- Modify: `dashboard/src/styles.css` or the current dashboard stylesheet
- Modify: `dashboard/dist/` after building

**Behavior:**

- Desktop: avatar left, chat panel right.
- Narrow screen: avatar top, chat panel below.
- Chat panel includes message history, input, send button, loading/error state.
- Initial backend may use a temporary stub route only to prove UX, but the code should make the transport easy to swap for the real Lumina web platform route.

**Acceptance criteria:**

- `/lumina` still loads the VRM avatar.
- User can type a message and see it appear in the local chat history.
- Stub assistant response appears in the chat history and emits a `speech.say` subtitle/avatar event.
- The UI does not call any external model/provider API directly.

**Commit:**

```bash
git add dashboard/src dashboard/dist dashboard/plugin_api.py
 git commit -m "feat: add Lumina dashboard chatbox skeleton"
```

---

## Task 9C: Connect chatbox to Hermes-native Lumina web channel ✅

**Objective:** Replace the stub transport with a real Hermes message pipeline integration so `/lumina` behaves like a browser messaging platform.

**Status:** Completed as the MVP polling/file-queue bridge. `lumina_web` is registered as a plugin platform adapter, the dashboard chat panel queues browser messages through plugin API routes, assistant replies are polled back from the adapter outbox, and reply text is mirrored into the avatar timeline as `speech.say`. The active local Hermes profile has `platforms.lumina_web.enabled=true`; other installs still need that config plus a gateway/dashboard restart to activate the adapter in a live process.

**Files:**

- Modify/create: `platform.py` with `LuminaWebAdapter`
- Modify: `__init__.py` to register `lumina_web` via `ctx.register_platform(...)`
- Modify: `plugin.yaml` only if a platform capability field is supported by Hermes plugin manifests
- Modify: `dashboard/plugin_api.py` as the authenticated browser-to-loopback adapter proxy
- Modify: `dashboard/src/api.ts`
- Modify: `dashboard/src/main.ts`
- Modify: `dashboard/dist/`
- Create/update: `docs/lumina-web-chat-platform.md`

**Behavior:**

- Browser sends a user message to the Lumina web channel.
- Hermes handles it as a normal agent turn with memory, skills, and tools.
- Assistant reply is delivered back to the same browser session/channel.
- Reply text is also appended as a `speech.say` avatar timeline event.
- The adapter can later map explicit avatar metadata/tool calls into richer animation/expression events.

**Acceptance criteria:**

- A `/lumina` chat message creates or resumes a Hermes session with stable Lumina channel identity.
- The assistant response appears in the browser chat panel.
- The same response appears as subtitle/speech event in the avatar timeline.
- Existing Telegram/Mattermost behavior is unaffected.
- The implementation has no direct model/provider API calls.

**Commit:**

```bash
git add <changed Hermes/lumina files> docs/lumina-web-chat-platform.md
 git commit -m "feat: connect Lumina chatbox to Hermes messaging pipeline"
```

---

## Task 9D: Scope avatar behavior to Lumina surface ✅

**Status:** Completed for the current milestone. The plugin registers `lumina_web` with a Lumina-specific platform hint, so embodied companion guidance is scoped to the `/lumina` browser surface instead of being imposed on every Hermes platform. `avatar_get_state` and `avatar_emit` intentionally remain available under the `lumina_plugin` toolset for debugging/development now, with a documented future direction to scope them to the web interface once the Lumina surface has a dedicated tool policy.

**Objective:** Reduce pressure on general-purpose Hermes sessions by making `/lumina` the primary embodied chat context while keeping global avatar tools available for debugging.

**Files:**

- Modify: `README.md`
- Create/modify: `docs/avatar-dashboard.md`
- Modify: this plan
- Optional: Hermes profile/toolset config notes

**Behavior:**

- `/lumina` sessions receive embodied/persona/avatar-choreography guidance.
- Normal Telegram/Mattermost/general sessions do not need heavy avatar-specific prompting by default.
- `avatar_get_state` and `avatar_emit` remain available for development/debugging now.
- Later, scope those avatar tools to the Lumina web interface/tool policy once the web surface can own avatar control cleanly.

**Acceptance criteria:**

- [x] Docs explain where avatar-specific interaction should happen.
- [x] General Hermes sessions remain clean and broadly useful by convention: only `lumina_web` receives the embodied platform hint.
- [x] The Lumina page can still drive the avatar without requiring every session to carry the full avatar context.
- [x] Boundary decision recorded: keep `avatar_get_state`/`avatar_emit` globally available for debugging now, but later scope them to the Lumina web interface/tool policy.

**Commit:**

```bash
git add README.md docs/avatar-dashboard.md docs/plans/2026-05-13-vrm-avatar-dashboard.md
git commit -m "docs: scope embodied chat behavior to Lumina surface"
```

---

## Task 10: Add renderer-agnostic event transport notes for Meta Quest ✅

**Status:** Completed as a documentation/architecture guardrail only. This does not implement the Quest app. It records how a future Quest renderer should consume the same state/protocol/events as the dashboard while keeping Hermes/plugin as the brain and avoiding renderer-specific leakage into `avatar_state.py` or `avatar_timeline.py`.

**Objective:** Keep the dashboard implementation aligned with the future Meta Quest app, where Quest renders the body locally while Hermes remains the brain.

**Files:**

- Modify: `docs/avatar-dashboard.md`
- Modify: this plan if transport decisions change
- Create: `docs/xr-quest-bridge.md`

**Design notes:**

- The Quest app should not call every internal Hermes tool directly.
- Quest should send user input/context to a gateway: speech transcript, controller events, gaze target, room/object context.
- Hermes should decide which tools to call.
- The gateway should expose the same renderer-neutral protocol used by the dashboard:
  - `GET /avatar/state`
  - `GET /avatar/events?cursor=...` or equivalent WebSocket event stream
  - `GET /avatar/protocol`
  - event types:
    - `speech.say`
    - `speech.pause`
    - `avatar.animation`
    - `avatar.expression`
    - `avatar.gaze`
    - `avatar.state`
- Start with HTTP polling/SSE for the dashboard; prefer WebSocket or WebRTC data channel for Quest once realtime audio is added.

**Verification:**

- [x] The docs explain the split clearly:
  - Hermes/plugin = brain, tools, state, timeline
  - dashboard/Quest = renderers
  - Quest app = local XR rendering, headset input, spatial embodiment
- [x] No renderer-specific logic leaks into `avatar_state.py` or `avatar_timeline.py`.
- [x] Docs explicitly say Task 10 is not the Quest app implementation.

**Commit:**

```bash
git add docs/avatar-dashboard.md docs/xr-quest-bridge.md docs/plans/2026-05-13-vrm-avatar-dashboard.md
git commit -m "docs: describe Lumina XR avatar event bridge"
```

---

## Task 11: Improve liveliness without overbuilding ✅

**Status:** Completed. The dashboard viewer now has basic procedural liveliness: automatic blinking, tiny breathing motion, subtle head sway toward the camera, a faint neutral idle expression, and a speaking mouth-open placeholder driven by `speaking=true` / `speech.say` events. This intentionally avoids phoneme lip sync, tracking, IK, XR runtime work, or a complex emotion model.

**Files:**

- Modify: `dashboard/src/avatar-viewer.ts`
- Create: `dashboard/src/liveliness-controller.ts`
- Modify: `dashboard/src/main.ts`
- Modify: `dashboard/dist/index.js`

**Candidate behaviors:**

- automatic blinking
- slight breathing motion
- subtle head movement toward camera
- idle expression changes
- speaking mouth-open placeholder driven by `speaking=true`

**Do not add yet:**

- full phoneme lip sync
- webcam face tracking
- IK hand tracking
- XR runtime
- complex emotion model

Those belong after the state/control loop works.

**Verification:**

- [x] Added regression/static tests for the liveliness controller wiring.
- [x] Frontend TypeScript typecheck passes.
- [x] Dashboard bundle builds successfully.
- [x] Plugin Python tests pass.
- Manual/browser checks should still watch the avatar idle for ~2 minutes and confirm CPU/GPU usage remains reasonable in browser devtools.

**Commit:**

```bash
git add dashboard/src dashboard/dist
 git commit -m "feat: add basic Lumina avatar liveliness"
```

---

## Task 12: Document operator workflow ✅

**Status:** Completed. `docs/avatar-dashboard.md` now includes the clone/open operator workflow: local asset paths, frontend install/build, dashboard and gateway restart commands, API routes, Hermes tools, state vs timeline contract, renderer responsibility split, animation constraints, and known limitations.

**Objective:** Make future work obvious.

**Files:**

- Modify: `docs/avatar-dashboard.md`
- Modify: `README.md`
- Modify: this plan if lessons change
- Create: `tests/test_lumina_operator_docs.py`

**Include:**

- how to build frontend
- where model assets live
- how to restart dashboard
- available API routes
- available Hermes tools
- state vs timeline contract
- dashboard renderer vs future Quest renderer responsibilities
- animation asset constraints
- known limitations

**Verification:**

- [x] Someone should be able to clone/open the plugin and follow the doc without asking where the VRM file goes.
- [x] Regression/static doc tests cover the required operator workflow sections.
- [x] Plugin Python tests pass.
- [x] Dashboard TypeScript typecheck and production build pass.

**Commit:**

```bash
git add README.md docs/avatar-dashboard.md docs/plans/2026-05-13-vrm-avatar-dashboard.md tests/test_lumina_operator_docs.py
git commit -m "docs: document Lumina avatar dashboard workflow"
```

---

## Open questions

- Should `assets/lumina.vrm` be committed to git, or stored outside git due to size/licensing?
- Are the current FBX animations compatible with the VRM rig, or should we use `.vrma` / Mixamo retargeting / procedural bone motion?
- Should the avatar live only on `/lumina`, or eventually become a persistent dashboard slot/overlay?
- Should state remain profile-level/global, or should the store add per-session/per-renderer namespaces later?
- Should the first browser reply transport for the Lumina web chat surface be polling, Server-Sent Events, WebSocket, or an existing dashboard event bus?
- Can the Lumina web chat surface be implemented as a user/plugin messaging platform adapter, or does Hermes core need a small gateway extension?
- Should Quest consume the same timeline over WebSocket, or a richer WebRTC channel once realtime audio is needed?

MVP answer: use `/lumina`, profile-level file-backed shared state in `~/.hermes/state/lumina_plugin/`, polling for avatar state/events, local VRM/VRMA assets, reliable semantic animations such as `idle`, `greeting`, `wave`, `dance`, and `spin`, and a Hermes-native `lumina_web` messaging surface for chat rather than a direct provider/API client.

---

## Definition of done for first milestone

The first milestone is complete when:

- `/lumina` renders `lumina.vrm` in a Three.js canvas.
- the dashboard page loads without console errors.
- `GET /api/plugins/lumina_plugin/avatar/state` returns avatar state.
- `GET /api/plugins/lumina_plugin/avatar/events?cursor=...` returns queued renderer events.
- `GET /api/plugins/lumina_plugin/avatar/protocol` returns the renderer-neutral protocol metadata.
- changing state to `animation=wave` makes the avatar visibly wave or perform a procedural fallback.
- queueing `speech.say` → `avatar.animation:wave` → `speech.say` makes the dashboard perform those actions in order.
- there is at least one Hermes tool that can trigger that state change.
- dashboard restart and fresh Hermes session behavior are documented.

## Definition of done for embodied chat milestone

The second milestone is complete when:

- `/lumina` has a visible chat panel integrated with the avatar layout.
- the chat transport is designed as a Hermes messaging surface/channel, not a model provider or direct OpenAI/API client.
- a user message from the browser creates or resumes a stable Lumina Hermes session/channel.
- assistant replies appear in the browser chat panel.
- assistant reply text also appears as `speech.say` subtitles/avatar timeline events.
- the implementation path for streaming/push delivery is documented, even if v1 uses polling.
- normal Telegram/Mattermost/general Hermes sessions remain unaffected.

---

## Recommended next step

Tasks 1–8 and Tasks 9A–12 are complete for the current milestone. Embodied/avatar behavior is scoped to `/lumina` by platform hint and documentation, while `avatar_get_state`/`avatar_emit` stay available globally for debugging until a later pass scopes them to the Lumina web interface/tool policy. The Quest bridge is documented as a future renderer path, not an immediate Quest app build. Task 12 is complete: operators can now find asset paths, build/restart commands, routes, tools, state/timeline behavior, renderer boundaries, and limitations in `docs/avatar-dashboard.md`.
