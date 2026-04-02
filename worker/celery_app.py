from __future__ import annotations

import os
from typing import Any, Callable, Dict, Optional

from utils.local_runtime import apply_runtime_entrypoint_defaults


apply_runtime_entrypoint_defaults()


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


class _LocalTask:
    def __init__(self, func: Callable[..., Any], name: str) -> None:
        self.func = func
        self.__name__ = getattr(func, "__name__", "local_task")
        self.name = name

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)

    def delay(self, *args: Any, **kwargs: Any) -> Any:
        return self.func(*args, **kwargs)


class _LocalCelery:
    def __init__(self, name: str, broker: str, backend: str, include: Optional[list[str]] = None) -> None:
        self.main = name
        self.broker = broker
        self.backend = backend
        self.include = include or []
        self.tasks: Dict[str, _LocalTask] = {}
        self.conf: Dict[str, Any] = {}

    def task(self, name: Optional[str] = None, **_kwargs: Any) -> Callable[[Callable[..., Any]], _LocalTask]:
        def decorator(func: Callable[..., Any]) -> _LocalTask:
            task_name = name or func.__name__
            wrapped = _LocalTask(func=func, name=task_name)
            self.tasks[task_name] = wrapped
            return wrapped

        return decorator


broker_url = os.getenv("GEOFUSION_CELERY_BROKER", "redis://localhost:6379/0")
result_backend = os.getenv("GEOFUSION_CELERY_BACKEND", broker_url)
always_eager = _as_bool(os.getenv("GEOFUSION_CELERY_EAGER", "1"))

try:
    from celery import Celery as _Celery  # type: ignore
except Exception:  # noqa: BLE001
    celery_app: Any = _LocalCelery(
        "geofusion",
        broker=broker_url,
        backend=result_backend,
        include=["worker.tasks"],
    )
else:
    celery_app = _Celery(
        "geofusion",
        broker=broker_url,
        backend=result_backend,
        include=["worker.tasks"],
    )

celery_app.conf.update(
    task_always_eager=always_eager,
    task_eager_propagates=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=os.getenv("GEOFUSION_TIMEZONE", "Asia/Shanghai"),
    enable_utc=True,
    beat_schedule={
        "scheduled-run-producer": {
            "task": "geofusion.scheduled_tick",
            "schedule": float(os.getenv("GEOFUSION_SCHEDULED_INTERVAL_SECONDS", "3600")),
            "args": (),
        }
    },
)
