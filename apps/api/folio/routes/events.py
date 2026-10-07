from __future__ import annotations

import asyncio
import contextlib
from urllib.parse import urlparse

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from ..config import get_settings
from ..db import SessionLocal
from ..security.sessions import SESSION_COOKIE, resolve_session
from ..services import events
from ..services.documents import get_owned_document
from ..services.errors import NotFound

router = APIRouter(tags=["events"])


def _origin_allowed(websocket: WebSocket) -> bool:
    """Cookies ride along on cross-site WebSocket handshakes, so the Origin must match."""
    origin = websocket.headers.get("origin")
    if origin is None:
        return True  # non-browser clients
    host = websocket.headers.get("host", "")
    allowed = {urlparse(get_settings().public_url).netloc, host}
    return urlparse(origin).netloc in allowed


@router.websocket("/api/v1/documents/{document_id}/events")
async def document_events(websocket: WebSocket, document_id: str) -> None:
    if not _origin_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    with SessionLocal() as db:
        resolved = resolve_session(db, websocket.cookies.get(SESSION_COOKIE))
        if resolved is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        try:
            document = get_owned_document(db, resolved[1], document_id)
        except NotFound:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        hello = {"event": "hello", "document_id": document.id, "revision": document.current_revision,
                 "status": document.status.value}
    await websocket.accept()
    await websocket.send_json(hello)

    async def pump() -> None:
        async for message in events.subscribe(document_id):
            await websocket.send_json(message)

    task = asyncio.create_task(pump())
    try:
        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await websocket.send_json({"event": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
