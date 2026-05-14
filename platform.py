"""Lumina web messaging platform adapter.

The `/lumina` dashboard is a Hermes-owned browser messaging surface, not a
model/provider client.  Browser requests enqueue local messages through the
plugin API; a gateway-loaded LuminaWebAdapter drains that queue into the normal
Hermes gateway pipeline and writes assistant replies back for browser polling.
"""

from __future__ import annotations

# This plugin module is intentionally named platform.py to match the Lumina
# plan, but Python also has a stdlib module named platform.  When commands are
# run from the plugin root, stdlib imports such as uuid -> platform could pick
# up this file as top-level `platform`.  In that mode, behave exactly like the
# stdlib module and do not execute Lumina adapter code.
if __name__ == "platform" and not __package__:
    import importlib.util as _importlib_util
    import os as _os
    import sys as _sys
    import sysconfig as _sysconfig

    _stdlib_platform = _os.path.join(_sysconfig.get_path("stdlib"), "platform.py")
    _spec = _importlib_util.spec_from_file_location("platform", _stdlib_platform)
    if _spec is None or _spec.loader is None:
        raise ImportError("Unable to load stdlib platform module")
    _module = _importlib_util.module_from_spec(_spec)
    _sys.modules[__name__] = _module
    _spec.loader.exec_module(_module)
    globals().update(_module.__dict__)
else:
    import asyncio
    import json
    import os
    import time
    import uuid
    from datetime import datetime, timezone
    from pathlib import Path
    from typing import Any, Iterable

    try:  # Hermes runtime imports
        from gateway.config import Platform, PlatformConfig
        from gateway.platforms.base import BasePlatformAdapter, MessageEvent, MessageType, SendResult
        from gateway.session import SessionSource
    except ImportError:  # pragma: no cover - surfaced explicitly in check_fn
        Platform = None  # type: ignore[assignment]
        PlatformConfig = object  # type: ignore[assignment]
        BasePlatformAdapter = object  # type: ignore[assignment]
        MessageEvent = None  # type: ignore[assignment]
        MessageType = None  # type: ignore[assignment]
        SendResult = None  # type: ignore[assignment]
        SessionSource = None  # type: ignore[assignment]

    try:
        from hermes_constants import get_hermes_home
    except Exception:  # pragma: no cover - fallback for standalone dashboard imports
        def get_hermes_home() -> Path:  # type: ignore[no-redef]
            return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))

    try:
        from .avatar_timeline import append_events
    except ImportError:  # dashboard/plugin_api.py can import this module standalone
        from avatar_timeline import append_events  # type: ignore[no-redef]

    PLATFORM_NAME = "lumina_web"
    LUMINA_CHAT_ID = "dashboard:default"
    LUMINA_CHAT_NAME = "Lumina dashboard"
    DEFAULT_USER_ID = "browser-user"
    DEFAULT_USER_NAME = "Browser user"
    DEFAULT_POLL_INTERVAL_MS = 250


    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


    def _chat_state_dir() -> Path:
        override = os.environ.get("LUMINA_CHAT_STATE_DIR")
        if override:
            root = Path(override).expanduser()
        else:
            root = Path(get_hermes_home()) / "state" / "lumina_plugin" / "chat"
        for subdir in ("inbox", "processing", "processed", "outbox"):
            (root / subdir).mkdir(parents=True, exist_ok=True)
        return root


    def _safe_json_load(path: Path) -> dict[str, Any] | None:
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError):
            return None


    def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, sort_keys=True)
        os.replace(tmp, path)


    def _message_filename(message_id: str) -> str:
        return f"{message_id}.json"


    def create_browser_message(
        text: str,
        *,
        client_id: str = LUMINA_CHAT_ID,
        user_id: str = DEFAULT_USER_ID,
        user_name: str = DEFAULT_USER_NAME,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Queue a browser-originated message for the Lumina gateway adapter."""

        cleaned = str(text or "").strip()
        if not cleaned:
            raise ValueError("text is required")
        message_id = f"lumina_in_{int(time.time() * 1000)}_{uuid.uuid4().hex[:10]}"
        record: dict[str, Any] = {
            "id": message_id,
            "role": "user",
            "text": cleaned,
            "chat_id": LUMINA_CHAT_ID,
            "client_id": client_id or LUMINA_CHAT_ID,
            "user_id": user_id or DEFAULT_USER_ID,
            "user_name": user_name or DEFAULT_USER_NAME,
            "created_at": _now_iso(),
            "metadata": metadata or {},
        }
        _atomic_write_json(_chat_state_dir() / "inbox" / _message_filename(message_id), record)
        return record


    def get_outbound_messages(after: str | None = None, *, limit: int = 100) -> list[dict[str, Any]]:
        """Return browser-visible assistant/system messages after an optional id."""

        root = _chat_state_dir() / "outbox"
        messages: list[dict[str, Any]] = []
        for path in sorted(root.glob("*.json")):
            record = _safe_json_load(path)
            if record:
                messages.append(record)
        messages.sort(key=lambda item: (str(item.get("created_at") or ""), str(item.get("id") or "")))
        if after:
            seen = False
            filtered: list[dict[str, Any]] = []
            for message in messages:
                if seen:
                    filtered.append(message)
                elif message.get("id") == after:
                    seen = True
            messages = filtered if seen else [m for m in messages if str(m.get("id") or "") > after]
        return messages[: max(1, min(int(limit or 100), 500))]


    def _queue_outbound_message(
        text: str,
        *,
        role: str = "assistant",
        chat_id: str = LUMINA_CHAT_ID,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        message_id = f"lumina_out_{int(time.time() * 1000)}_{uuid.uuid4().hex[:10]}"
        record: dict[str, Any] = {
            "id": message_id,
            "role": role,
            "text": str(text or ""),
            "chat_id": chat_id,
            "reply_to": reply_to,
            "created_at": _now_iso(),
            "metadata": metadata or {},
        }
        _atomic_write_json(_chat_state_dir() / "outbox" / _message_filename(message_id), record)
        return record


    def _iter_claimable_inbox() -> Iterable[tuple[Path, Path, dict[str, Any]]]:
        root = _chat_state_dir()
        for path in sorted((root / "inbox").glob("*.json")):
            record = _safe_json_load(path)
            if not record:
                continue
            claimed = root / "processing" / path.name
            try:
                os.replace(path, claimed)
            except FileNotFoundError:
                continue
            except OSError:
                continue
            yield claimed, root / "processed" / path.name, record


    def _platform_available() -> bool:
        return Platform is not None and MessageEvent is not None and SessionSource is not None and SendResult is not None


    def _lumina_platform():
        """Return the dynamic Platform member for lumina_web.

        In production, PluginContext.register_platform registers the name before
        the gateway asks the factory for an adapter.  Unit tests may instantiate
        the adapter directly, so create the same enum pseudo-member defensively.
        """

        try:
            return Platform(PLATFORM_NAME)
        except ValueError:
            pseudo = object.__new__(Platform)
            pseudo._value_ = PLATFORM_NAME
            pseudo._name_ = PLATFORM_NAME.upper()
            Platform._value2member_map_[PLATFORM_NAME] = pseudo
            Platform._member_map_[pseudo._name_] = pseudo
            return pseudo


    class LuminaWebAdapter(BasePlatformAdapter):
        """Local file-queue backed browser messaging adapter for `/lumina`."""

        def __init__(self, config: PlatformConfig):
            if not _platform_available():  # pragma: no cover
                raise RuntimeError("Hermes gateway platform modules are unavailable")
            super().__init__(config, _lumina_platform())
            self._poll_task: asyncio.Task | None = None
            self._poll_interval = max(
                0.05,
                float(getattr(config, "extra", {}).get("poll_interval_ms", DEFAULT_POLL_INTERVAL_MS)) / 1000.0,
            )

        @property
        def name(self) -> str:
            return "Lumina Web"

        async def connect(self) -> bool:
            _chat_state_dir()
            self._mark_connected()
            self._poll_task = asyncio.create_task(self._poll_inbox_loop())
            return True

        async def disconnect(self) -> None:
            self._mark_disconnected()
            if self._poll_task:
                self._poll_task.cancel()
                try:
                    await self._poll_task
                except asyncio.CancelledError:
                    pass
                self._poll_task = None

        async def send(
            self,
            chat_id: str,
            content: str,
            reply_to: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> SendResult:
            record = _queue_outbound_message(
                content,
                role="assistant",
                chat_id=chat_id or LUMINA_CHAT_ID,
                reply_to=reply_to,
                metadata=metadata,
            )
            # Mirror assistant replies into the renderer-neutral avatar timeline.
            if content:
                try:
                    append_events(
                        [
                            {"type": "speech.say", "text": content},
                            {"type": "avatar.expression", "name": "happy", "intensity": 0.68},
                        ],
                        30000,
                    )
                except Exception:
                    # Chat delivery should not fail just because the avatar timeline
                    # backing store is temporarily unavailable.
                    pass
            return SendResult(success=True, message_id=record["id"], raw_response=record)

        async def get_chat_info(self, chat_id: str) -> dict[str, Any]:
            return {
                "id": chat_id or LUMINA_CHAT_ID,
                "name": LUMINA_CHAT_NAME,
                "type": "dm",
            }

        async def _poll_inbox_loop(self) -> None:
            while self.is_connected:
                await self._drain_once()
                await asyncio.sleep(self._poll_interval)

        async def _drain_once(self) -> None:
            if not self._message_handler:
                return
            for claimed, processed, record in _iter_claimable_inbox():
                event = self._event_from_record(record)
                await self.handle_message(event)
                try:
                    os.replace(claimed, processed)
                except OSError:
                    pass

        def _event_from_record(self, record: dict[str, Any]) -> MessageEvent:
            message_id = str(record.get("id") or f"lumina_in_{uuid.uuid4().hex}")
            source = SessionSource(
                platform=_lumina_platform(),
                chat_id=LUMINA_CHAT_ID,
                chat_name=LUMINA_CHAT_NAME,
                chat_type="dm",
                user_id=str(record.get("user_id") or DEFAULT_USER_ID),
                user_name=str(record.get("user_name") or DEFAULT_USER_NAME),
                message_id=message_id,
            )
            return MessageEvent(
                text=str(record.get("text") or ""),
                message_type=MessageType.TEXT,
                source=source,
                raw_message=record,
                message_id=message_id,
            )


    def validate_config(config: PlatformConfig) -> bool:
        return bool(getattr(config, "enabled", False))


    def make_adapter(config: PlatformConfig) -> LuminaWebAdapter:
        return LuminaWebAdapter(config)
