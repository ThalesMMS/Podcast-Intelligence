from __future__ import annotations

from celery import Celery

from podcast_intelligence.config import get_settings

settings = get_settings()
celery_app = Celery(
    "podcast_intelligence",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["podcast_intelligence.worker.tasks"],
)
celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "socket_connect_timeout": 5.0,
        "socket_timeout": 5.0,
    },
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 3,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 0.5,
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "dispatch-pending-processing-jobs": {
            "task": "podcast_intelligence.dispatch_pending_jobs",
            "schedule": 5.0,
        }
    },
)
