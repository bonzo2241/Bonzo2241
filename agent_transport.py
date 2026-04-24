from __future__ import annotations

import asyncio
from typing import Any


def _ensure_cmdop_timeouterror() -> None:
    """Compatibility shim for OpenClaw builds that expect cmdop.exceptions.TimeoutError."""
    try:
        import cmdop.exceptions as cmdop_exc
    except Exception:
        return

    if not hasattr(cmdop_exc, "TimeoutError"):
        class _CmdopTimeoutError(Exception):
            pass

        cmdop_exc.TimeoutError = _CmdopTimeoutError


class AgentTransport:
    async def send(self, channel: str, payload: dict[str, Any]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    async def recv(self, channel: str, timeout: int = 10) -> dict[str, Any] | None:  # pragma: no cover - interface
        raise NotImplementedError


class LocalQueueTransport(AgentTransport):
    def __init__(self, channels: list[str]):
        self._queues: dict[str, asyncio.Queue] = {c: asyncio.Queue() for c in channels}

    async def send(self, channel: str, payload: dict[str, Any]) -> None:
        queue = self._queues.get(channel)
        if queue is None:
            raise KeyError(f"Unknown channel: {channel}")
        await queue.put(payload)

    async def recv(self, channel: str, timeout: int = 10) -> dict[str, Any] | None:
        queue = self._queues.get(channel)
        if queue is None:
            raise KeyError(f"Unknown channel: {channel}")
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None


class OpenClawTransport(AgentTransport):
    """Best-effort OpenClaw adapter.

    It supports common client method names (`publish` / `send` / `emit` and
    `subscribe`) and buffers messages into asyncio queues per channel.
    """

    def __init__(self, base_url: str, channels: list[str]):
        _ensure_cmdop_timeouterror()
        try:
            from openclaw import OpenClawClient
        except ModuleNotFoundError as exc:
            if exc.name == "tenacity":
                raise ModuleNotFoundError(
                    "OpenClaw dependency missing: tenacity. Run: pip install tenacity"
                ) from exc
            raise
        except ImportError as exc:
            if "cmdop.exceptions" in str(exc) and "TimeoutError" in str(exc):
                raise ImportError(
                    "Incompatible cmdop version: TimeoutError is missing in cmdop.exceptions. "
                    "Try: pip install -U cmdop"
                ) from exc
            raise

        self._client = OpenClawClient(base_url=base_url)
        self._buffers: dict[str, asyncio.Queue] = {c: asyncio.Queue() for c in channels}
        self._subscribed: set[str] = set()

    async def send(self, channel: str, payload: dict[str, Any]) -> None:
        for method_name in ("publish", "send", "emit"):
            method = getattr(self._client, method_name, None)
            if method is None:
                continue
            result = method(channel, payload)
            if asyncio.iscoroutine(result):
                await result
            return
        raise RuntimeError("OpenClawClient has no supported send method (publish/send/emit)")

    async def recv(self, channel: str, timeout: int = 10) -> dict[str, Any] | None:
        await self._ensure_subscription(channel)
        try:
            return await asyncio.wait_for(self._buffers[channel].get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def _ensure_subscription(self, channel: str) -> None:
        if channel in self._subscribed:
            return

        subscribe = getattr(self._client, "subscribe", None)
        if subscribe is None:
            raise RuntimeError("OpenClawClient has no supported subscribe method")

        async def _on_message(message: Any):
            if isinstance(message, dict):
                await self._buffers[channel].put(message)
            else:
                await self._buffers[channel].put({"type": "unknown", "payload": message})

        maybe = subscribe(channel, _on_message)
        if asyncio.iscoroutine(maybe):
            await maybe

        self._subscribed.add(channel)
