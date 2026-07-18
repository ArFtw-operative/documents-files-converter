from celery import Celery

from .config import settings

celery = Celery("convertvault", broker=settings.celery_broker_url, backend=settings.celery_result_backend)
celery.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_routes={
        "convertvault.tasks.run_conversion": {"queue": "general"},
        "convertvault.tasks.cleanup_trash": {"queue": "maintenance"},
    },
    beat_schedule={
        "cleanup-trash-nightly": {"task": "convertvault.tasks.cleanup_trash", "schedule": 86400},
        "reconcile-stale-jobs": {"task": "convertvault.tasks.reconcile_stale_jobs", "schedule": 300},
        "cleanup-expired-sessions": {"task": "convertvault.tasks.cleanup_sessions", "schedule": 86400},
    },
)
