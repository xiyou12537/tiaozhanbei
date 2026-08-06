"""
Background task manager for long-running computations.

Provides:
- Task submission with unique IDs
- Status polling (queued → running → completed/failed)
- Progress reporting
- Result storage via SessionCache
"""

from __future__ import annotations

import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from .cache import cache


class TaskManager:
    """Manages async computation tasks with status tracking."""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._progress: Dict[str, Dict[str, Any]] = {}

    def submit(
        self, fn: Callable[..., Any], *args, **kwargs
    ) -> str:
        """Submit a function for background execution.

        Returns a task_id for polling.
        """
        task_id = str(uuid.uuid4())[:8]

        self._progress[task_id] = {
            "status": "queued",
            "progress": 0.0,
            "message": "Waiting to start...",
            "result": None,
            "error": None,
        }

        def _wrapper() -> None:
            try:
                self._progress[task_id]["status"] = "running"
                self._progress[task_id]["message"] = "Computing..."
                self._progress[task_id]["progress"] = 10.0

                result = fn(*args, **kwargs)

                self._progress[task_id]["status"] = "completed"
                self._progress[task_id]["progress"] = 100.0
                self._progress[task_id]["message"] = "Done."
                self._progress[task_id]["result"] = result

                # Store result in cache for 30 min
                cache.set(f"result:{task_id}", result, ttl=1800)

            except Exception as exc:
                self._progress[task_id]["status"] = "failed"
                self._progress[task_id]["message"] = str(exc)
                self._progress[task_id]["error"] = traceback.format_exc()

        self._executor.submit(_wrapper)
        return task_id

    def submit_cancellable(self, fn: Callable[..., Any], *args, **kwargs) -> str:
        """Run a cooperative task that can terminate an external child process safely."""
        task_id = str(uuid.uuid4())[:8]
        self._progress[task_id] = {
            "status": "queued",
            "progress": 0.0,
            "message": "Waiting to start...",
            "result": None,
            "error": None,
            "cancel_requested": False,
        }

        def is_cancel_requested() -> bool:
            return bool(self._progress.get(task_id, {}).get("cancel_requested"))

        def _wrapper() -> None:
            if is_cancel_requested():
                self._progress[task_id].update(status="cancelled", progress=100.0, message="Cancelled before execution.")
                return
            try:
                self._progress[task_id].update(status="running", progress=10.0, message="Computing...")
                result = fn(is_cancel_requested, *args, **kwargs)
                if is_cancel_requested():
                    self._progress[task_id].update(status="cancelled", progress=100.0, message="Cancelled.", result=result)
                    return
                self._progress[task_id].update(status="completed", progress=100.0, message="Done.", result=result)
                cache.set(f"result:{task_id}", result, ttl=1800)
            except Exception as exc:
                if is_cancel_requested():
                    self._progress[task_id].update(status="cancelled", progress=100.0, message="Cancelled.")
                    return
                self._progress[task_id].update(status="failed", message=str(exc), error=traceback.format_exc())

        self._executor.submit(_wrapper)
        return task_id

    def cancel(self, task_id: str) -> bool:
        """Request cooperative cancellation; running subprocesses receive the request through their checker."""
        task = self._progress.get(task_id)
        if task is None or task["status"] in {"completed", "failed", "cancelled"}:
            return False
        task["cancel_requested"] = True
        task["message"] = "Cancellation requested."
        return True

    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self._progress.get(task_id)

    def get_result(self, task_id: str) -> Optional[Any]:
        """Retrieve completed task result from cache."""
        return cache.get(f"result:{task_id}")


# Global instance
task_manager = TaskManager(max_workers=2)
