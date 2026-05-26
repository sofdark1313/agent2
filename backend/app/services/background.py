"""共享的后台线程 helper,供文章生成与发布 pipeline 复用。"""
from __future__ import annotations

import logging
from threading import Thread
from typing import Callable

logger = logging.getLogger(__name__)


def run_in_background(function: Callable[..., object], *args, name: str | None = None) -> Thread:
    thread = Thread(
        target=_safe_run,
        args=(function, args),
        daemon=True,
        name=name or function.__name__,
    )
    thread.start()
    return thread


def _safe_run(function: Callable[..., object], args: tuple) -> None:
    try:
        function(*args)
    except Exception:
        logger.exception("background task %s crashed", function.__name__)
