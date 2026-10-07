"""Celery application for the CPU document worker (architecture §21, §46).

Queues: ``analysis``, ``pdf_mutation``, ``export``, ``maintenance`` (CPU worker) and ``ocr``
(GPU worker, milestone 2). Broker priorities implement P0–P5.
"""

from __future__ import annotations

from celery import Celery

from .config import get_settings

_url = get_settings().valkey_url
celery = Celery("folio", broker=_url or "memory://", backend=_url or "cache+memory://", include=["folio.tasks"])
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="analysis",
    task_default_priority=3,
    broker_transport_options={"priority_steps": list(range(6)), "sep": ":", "queue_order_strategy": "priority"},
    result_expires=3600,
    task_time_limit=600,
    task_soft_time_limit=540,
    worker_max_tasks_per_child=200,
    beat_schedule={
        "reconcile-temp": {"task": "folio.tasks.maintenance", "schedule": 3600.0,
                           "options": {"queue": "maintenance", "priority": 5}},
    },
)
