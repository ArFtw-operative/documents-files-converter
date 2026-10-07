from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from redis import Redis

from .config import settings
from .tasks import run_conversion


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="convertvault-local-worker")
_secret_lock = Lock()
_local_secrets: dict[str, str] = {}


def dispatch_job(job_id: str, queue: str) -> None:
    """Use an embedded worker locally and Celery in deployed environments."""
    if settings.app_env == "development":
        _executor.submit(run_conversion.run, job_id)
        return
    run_conversion.apply_async(args=[job_id], queue=queue)


def store_job_secret(job_id: str, secret: str, ttl: int) -> None:
    if settings.app_env == "development":
        with _secret_lock:
            _local_secrets[job_id] = secret
        return
    Redis.from_url(settings.redis_url).setex(f"job-secret:{job_id}", ttl, secret)


def consume_job_secret(job_id: str) -> str | None:
    if settings.app_env == "development":
        with _secret_lock:
            return _local_secrets.pop(job_id, None)
    value = Redis.from_url(settings.redis_url).getdel(f"job-secret:{job_id}")
    return value.decode("utf-8") if value else None
