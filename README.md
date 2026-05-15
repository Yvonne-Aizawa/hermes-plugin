# Lumina Hermes Plugin

Lumina is a user plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent). It provides `/lumina`, an embodied browser chat surface with a VRM avatar renderer, renderer-neutral state, and ordered timeline events.

The current focus is keeping `/lumina` as the primary embodied Lumina interface while normal Hermes surfaces such as Telegram, Mattermost, and CLI stay general-purpose by default.

## Features

- **Dashboard avatar renderer** at `/lumina`
  - Three.js + `@pixiv/three-vrm`
  - local `lumina.vrm` model asset supplied by the operator
  - optional VRMA animation playback using semantic names such as `idle`, `greeting`, `wave`, `dance`, and `spin`
- **Renderer-neutral avatar protocol**
  - state snapshot: mood, animation, expression, speaking, gesture, intensity
  - ordered timeline events: `speech.say`, `speech.pause`, `avatar.animation`, `avatar.expression`, `avatar.gaze`, `avatar.state`
- **Hermes avatar tools**
  - `avatar_get_state`
  - `avatar_emit`
- **Hermes-native Lumina chat surface**
  - browser messages enter Hermes through the `lumina_web` gateway platform
  - visible history is backed by Hermes `SessionDB`, not stale plugin queue files
  - assistant replies are mirrored into the avatar timeline as `speech.say` events
- **Shared state across processes**
  - avatar state/events are persisted under `~/.hermes/state/lumina_plugin/`
  - this lets Hermes tool sessions and the dashboard API process see the same state

## Repository layout

```text
.
├── plugin.yaml                    # Hermes plugin manifest
├── __init__.py                    # tool registration entry point
├── tools.py                       # Hermes tool schemas and handlers
├── avatar_state.py                # file-backed avatar state snapshot
├── avatar_timeline.py             # file-backed avatar event queue/protocol
├── assets/                        # source model/animation assets
├── dashboard/
│   ├── manifest.json              # dashboard tab metadata
│   ├── plugin_api.py              # dashboard API routes
│   ├── src/                       # TypeScript dashboard source
│   ├── dist/                      # built dashboard bundle
│   └── assets/                    # dashboard-served model/animation assets
└── docs/                          # operator docs, chat notes, plans
```

## Installation

Clone or copy this repository into your Hermes plugins directory:

```bash
mkdir -p ~/.hermes/plugins
git clone <repo-url> ~/.hermes/plugins/lumina_plugin
```

Enable the plugin in `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - lumina_plugin
```

Then restart Hermes sessions that should see the plugin tools. For dashboard changes, restart the dashboard process as well:

```bash
hermes dashboard --stop
hermes dashboard --host 0.0.0.0 --insecure --no-open
```

Tool and plugin availability is snapshotted at process/session startup, so code/config changes usually require a fresh session or process restart.

## Dashboard development

The dashboard frontend lives in `dashboard/src/` and builds with Vite:

```bash
cd dashboard
npm install
npm run build
```

The built files are committed in `dashboard/dist/` because Hermes serves the compiled dashboard bundle from the plugin directory.

## Avatar API

Dashboard routes are exposed under the Hermes dashboard plugin API prefix:

```text
GET  /api/plugins/lumina_plugin/avatar/state
POST /api/plugins/lumina_plugin/avatar/emit
GET  /api/plugins/lumina_plugin/avatar/events?cursor=<event_id>
GET  /api/plugins/lumina_plugin/avatar/protocol
```

The same payloads are intended to be renderer-neutral so a future Quest/XR renderer can consume the same state and event protocol.

## Avatar tools

Avatar tools are intentionally compact and primarily support the `/lumina` embodied surface. They may remain enabled in general Hermes sessions for development/debugging, but ordinary Telegram/Mattermost/CLI chats should not assume the user is watching the avatar unless they explicitly ask for avatar control.

### `avatar_get_state`

Returns current avatar state and protocol metadata. Optionally includes queued events:

```json
{
  "include_events": true,
  "cursor": "12"
}
```

### `avatar_emit`

Patches avatar state and/or queues timeline events:

```json
{
  "state": {
    "mood": "playful",
    "animation": "dance",
    "expression": "happy",
    "speaking": true,
    "intensity": 0.9
  },
  "events": [
    {"type": "avatar.animation", "name": "dance", "loop": false},
    {"type": "speech.say", "text": "Dashboard state is live."}
  ],
  "ttl_ms": 120000
}
```

## Environment variables

- `LUMINA_AVATAR_STATE_DIR` — optional override for the file-backed avatar state directory, mostly useful for tests

General-purpose HTTP, ntfy, and Transmute tools live in a separate `utility_tools` plugin.

## Embodied surface scope

`/lumina` is the primary place for avatar-specific interaction: companion-style chat, subtitles, expressions, gestures, VRMA animations, and future XR renderer alignment. Other Hermes platforms should remain broadly useful and avoid carrying heavy avatar-specific behavior by default.

The plugin currently scopes this by:

- registering `lumina_web` as a Hermes gateway platform with a Lumina-specific platform hint;
- keeping dashboard rendering and avatar protocol docs under the Lumina plugin;
- leaving `avatar_get_state` and `avatar_emit` available under the `lumina_plugin` toolset for debugging/development now, with a later goal of scoping them to the Lumina web interface/tool policy.

See `docs/avatar-dashboard.md` for the current operator workflow and boundary decisions.

## Public repo checklist

Before making this repository public, verify:

- no `.env`, config files, tokens, cookies, or private session data are committed
- model/animation assets are allowed to be redistributed
- third-party asset licenses are included
- local runtime state under `~/.hermes/state/lumina_plugin/` is not copied into the repo

## Local avatar assets

Avatar binaries are intentionally ignored by git. For local development, provide your own model and animation files at these paths:

```text
dashboard/assets/lumina.vrm
dashboard/assets/animations/vrma/idle_loop.vrma
dashboard/assets/animations/vrma/greeting.vrma
dashboard/assets/animations/vrma/peaceSign.vrma
dashboard/assets/animations/vrma/shoot.vrma
dashboard/assets/animations/vrma/spin.vrma
dashboard/assets/animations/vrma/modelPose.vrma
dashboard/assets/animations/vrma/squat.vrma
dashboard/assets/animations/vrma/showFullBody.vrma
dashboard/assets/animations/vrma/dance.vrma
```

The matching `assets/` directory can be used for source copies, but the dashboard serves files from `dashboard/assets/`.

### Where to get assets

- **VRM model:** Create your own avatar in [VRoid Studio](https://vroid.com/en/studio), then export it as a `.vrm` file and place it at `dashboard/assets/lumina.vrm`.
- **VRMA animations:** This project expects the Amica animation filenames from [`semperai/amica/public/animations`](https://github.com/semperai/amica/tree/master/public/animations). Copy the needed `.vrma` files into `dashboard/assets/animations/vrma/`.

The controller currently looks for these Amica-style filenames:

```text
idle_loop.vrma
greeting.vrma
peaceSign.vrma
shoot.vrma
spin.vrma
modelPose.vrma
squat.vrma
showFullBody.vrma
dance.vrma
```

The included placeholder README files explain the expected paths. Check the license metadata of your VRM and animation files before sharing them.

## Roadmap

- Keep normal Hermes sessions general-purpose while `/lumina` becomes the primary embodied Lumina interface.
- Add subtle liveliness: blinking, breathing, speaking placeholder, and softer idle behavior.
- Document a Quest/XR renderer bridge that consumes the same avatar protocol.
