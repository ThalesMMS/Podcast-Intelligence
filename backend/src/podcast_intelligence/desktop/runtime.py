from __future__ import annotations

from collections.abc import Callable
from threading import Lock, Timer

_shutdown_callback: Callable[[], None] | None = None
_shutdown_guard = Lock()


def register_shutdown_callback(callback: Callable[[], None]) -> None:
    global _shutdown_callback
    with _shutdown_guard:
        _shutdown_callback = callback


def request_shutdown(delay_seconds: float = 0.15) -> bool:
    with _shutdown_guard:
        callback = _shutdown_callback
    if callback is None:
        return False
    timer = Timer(delay_seconds, callback)
    timer.daemon = True
    timer.start()
    return True
