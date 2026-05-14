# Lumina web chat platform

`/lumina` is a Hermes-native browser messaging surface. It is **not** a model provider and it does not call OpenAI/provider APIs directly.

## Architecture

- Dashboard UI posts user text to `POST /api/plugins/lumina_plugin/chat/messages`.
- `dashboard/plugin_api.py` validates the request and writes a file-backed inbound message under `~/.hermes/state/lumina_plugin/chat/inbox/`.
- The plugin registers a gateway platform named `lumina_web` from `platform.py` via `ctx.register_platform(...)`.
- `LuminaWebAdapter` polls the inbox, converts records into normal Hermes `MessageEvent`s, and lets the gateway create/resume the stable Lumina session.
- Assistant replies are sent back through `LuminaWebAdapter.send(...)`, which writes short-lived browser delivery messages under `~/.hermes/state/lumina_plugin/chat/outbox/`.
- The dashboard polls `GET /api/plugins/lumina_plugin/chat/messages?after=...`; durable reload history comes from Hermes `SessionDB` for the stable `lumina_web` session, while only pending `inbox/` and `processing/` transport messages are overlaid for immediate send feedback. `processed/` and `outbox/` files are not durable UI history.
- Session-backed history includes `user`, `assistant`, `system`, and browser-visible `tool` entries. Assistant `tool_calls` become `Tool call` cards with parsed arguments; `tool` rows become `Tool result` cards with scrollable output previews.
- The browser settings modal stores display preferences in `localStorage` under `lumina.chat.settings`. Tool call display modes are `full` (names, arguments, results), `compact` (tool names only), and `none` (hide tool entries).
- The same assistant reply text is mirrored into the avatar timeline as `speech.say` plus a light expression event.

## Stable channel identity

Current MVP channel identity:

- platform: `lumina_web`
- chat id: `dashboard:default`
- chat name: `Lumina dashboard`
- chat type: `dm`
- user id: `browser-user`

This gives the browser chat a stable Hermes session key without coupling the dashboard to any model/provider implementation.

## Enabling the platform

The plugin registers `lumina_web`, but the gateway must be configured to enable it like any other Hermes messaging platform. Minimal profile/config shape:

```yaml
platforms:
  lumina_web:
    enabled: true
    gateway_restart_notification: false
    extra:
      poll_interval_ms: 250
```

After changing plugin platform code or gateway config, restart the Hermes gateway/dashboard process so the new adapter registration is loaded.

## API endpoints

### Queue browser message

`POST /api/plugins/lumina_plugin/chat/messages`

```json
{
  "text": "hello Lumina",
  "client_id": "dashboard:default",
  "user_id": "browser-user",
  "user_name": "Browser user"
}
```

Response:

```json
{
  "success": true,
  "message": {
    "id": "lumina_in_...",
    "role": "user",
    "text": "hello Lumina"
  }
}
```

### Poll assistant replies

`GET /api/plugins/lumina_plugin/chat/messages?after=<last_message_id>`

Response:

```json
{
  "success": true,
  "after": "lumina_out_...",
  "messages": [],
  "last_message_id": "lumina_out_..."
}
```

## Limitations

- MVP uses polling and file-backed queues; SSE/WebSocket can replace polling later.
- Browser messages will queue even if the gateway is not currently running `lumina_web`; replies only appear after the adapter is enabled and draining the inbox.
- `platform.py` includes a stdlib import guard because the file intentionally shares a name with Python’s standard `platform` module.
