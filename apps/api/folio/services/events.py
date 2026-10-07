"""Realtime document events (architecture §29).

Workers and the API publish to Valkey channel ``folio:doc:<id>``; the API's WebSocket endpoint
relays to the document owner's open editors. Without Valkey (dev/test) an in-process bus is used.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)


def channel(document_id: str) -> str:
    return f"folio:doc:{document_id}"


class _LocalBus:
    """Single-process bus for dev/test. Publishers may run on worker threads, so delivery is
    scheduled onto each subscriber's event loop."""

    def __init__(self) -> None:
        self.queues: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = defaultdict(set)
        self.history: list[tuple[str, dict]] = []  # inspected by tests

    def publish(self, name: str, message: dict) -> None:
        self.history.append((name, message))
        del self.history[:-500]
        for loop, queue in list(self.queues.get(name, ())):
            try:
                loop.call_soon_threadsafe(queue.put_nowait, message)
            except RuntimeError:  # loop closed
                self.queues[name].discard((loop, queue))


local_bus = _LocalBus()
_redis = None


def _sync_client():
    global _redis
    url = get_settings().valkey_url
    if not url:
        return None
    if _redis is None:
        import redis

        _redis = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
    return _redis


def publish(document_id: str, event: str, **data: Any) -> None:
    message = {"event": event, "document_id": document_id, "at": datetime.now(UTC).isoformat(), **data}
    client = _sync_client()
    if client is None:
        local_bus.publish(channel(document_id), message)
        return
    try:
        client.publish(channel(document_id), json.dumps(message, default=str))
    except Exception as exc:  # noqa: BLE001 - events are best-effort; state lives in the DB
        log.warning("event publish failed: %s", exc)


async def subscribe(document_id: str) -> AsyncIterator[dict]:
    url = get_settings().valkey_url
    name = channel(document_id)
    if not url:
        entry = (asyncio.get_running_loop(), asyncio.Queue(maxsize=200))
        local_bus.queues[name].add(entry)
        try:
            while True:
                yield await entry[1].get()
        finally:
            local_bus.queues[name].discard(entry)
        return
    import redis.asyncio as aioredis

    client = aioredis.Redis.from_url(url)
    pubsub = client.pubsub()
    await pubsub.subscribe(name)
    try:
        async for item in pubsub.listen():
            if item.get("type") == "message":
                try:
                    yield json.loads(item["data"])
                except (TypeError, ValueError):
                    continue
    finally:
        await pubsub.unsubscribe(name)
        await pubsub.aclose()
        await client.aclose()
