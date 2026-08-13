"""Process-local admission control for memory-bound molecular calculations.

The production deployment deliberately runs one Uvicorn worker.  A single
slot prevents concurrent PySCF/VQE statevector jobs from exhausting the
4-core, 3.6 GiB host while leaving asynchronous Studies and Bond Scans queued
in their background worker until a slot becomes available.
"""

from __future__ import annotations

import os
import threading


class MolecularComputeAdmissionController:
    """Thread-safe bounded semaphore with explicit non-blocking admission."""

    def __init__(self, max_concurrent: int = 1) -> None:
        if max_concurrent < 1:
            raise ValueError("MOLECULAR_COMPUTE_MAX_CONCURRENT must be at least 1")
        self.max_concurrent = max_concurrent
        self._slots = threading.BoundedSemaphore(max_concurrent)

    def try_acquire(self) -> bool:
        return self._slots.acquire(blocking=False)

    def wait_acquire(self, timeout_seconds: float) -> bool:
        return self._slots.acquire(timeout=timeout_seconds)

    def release(self) -> None:
        self._slots.release()


def _environment_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


_default_admission = MolecularComputeAdmissionController(
    _environment_int("MOLECULAR_COMPUTE_MAX_CONCURRENT", 1)
)
_queue_timeout_seconds = _environment_int("MOLECULAR_COMPUTE_QUEUE_TIMEOUT_SECONDS", 900)


def get_molecular_compute_admission() -> MolecularComputeAdmissionController:
    return _default_admission


def molecular_compute_queue_timeout_seconds() -> int:
    return _queue_timeout_seconds
