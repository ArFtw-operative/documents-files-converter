"""Runs document-engine work inline (dev/test) or in the sandboxed CPU worker (production).

Untrusted PDFs are only parsed where ``engine_mode`` says: in production the API process never
opens a PDF; it calls the worker's tasks and waits for the (small, JSON) result.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings

# Priorities on the Valkey broker: lower number = served first (architecture §21).
P0_EDIT, P1_VISIBLE, P2_NEARBY, P3_BACKGROUND, P4_THUMBNAIL, P5_MAINTENANCE = 0, 1, 2, 3, 4, 5


class EngineUnavailable(Exception):
    pass


def run(task_name: str, *args: Any, queue: str, priority: int, wait: bool = True) -> Any:
    from .. import tasks

    if get_settings().engine_mode == "inline":
        return getattr(tasks, task_name).run(*args)
    from ..worker import celery

    async_result = celery.send_task(f"folio.tasks.{task_name}", args=args, queue=queue, priority=priority)
    if not wait:
        return async_result.id
    try:
        return async_result.get(timeout=get_settings().engine_timeout_seconds, propagate=True)
    except TimeoutError as exc:
        raise EngineUnavailable("The document engine did not respond in time.") from exc


def enqueue(task_name: str, *args: Any, queue: str, priority: int) -> None:
    """Fire-and-forget background work (analysis of remaining pages, exports)."""
    from .. import tasks

    if get_settings().engine_mode == "inline":
        if get_settings().is_test:
            getattr(tasks, task_name).run(*args)
        else:
            import threading

            threading.Thread(target=getattr(tasks, task_name).run, args=args, daemon=True).start()
        return
    from ..worker import celery

    celery.send_task(f"folio.tasks.{task_name}", args=args, queue=queue, priority=priority)
