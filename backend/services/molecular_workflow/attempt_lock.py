"""OS-backed exclusive locks for one deterministic confirmation attempt."""

from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
from types import TracebackType


class ConfirmationAttemptLockBusy(RuntimeError):
    """Raised when another process or thread owns the same attempt lock."""


def confirmation_attempt_lock_id(
    owner_user_id: int,
    molecular_model_id: str,
    idempotency_key_hash: str,
) -> str:
    """Derive a path-safe stable ID without exposing owner or idempotency input."""

    preimage = (
        "confirmation_attempt_lock_v1\0"
        f"{owner_user_id}\0{molecular_model_id}\0{idempotency_key_hash}"
    ).encode("utf-8")
    return hashlib.sha256(preimage).hexdigest()


class ExclusiveConfirmationAttemptLock:
    """Hold a non-blocking OS-exclusive handle until the context exits."""

    def __init__(self, lock_root: str | Path, attempt_lock_id: str) -> None:
        if (
            len(attempt_lock_id) != 64
            or any(character not in "0123456789abcdef" for character in attempt_lock_id)
        ):
            raise ValueError("attempt_lock_id must be 64 lowercase hexadecimal characters.")
        self.lock_root = Path(lock_root).resolve()
        self.path = self.lock_root / f"confirmation-{attempt_lock_id}.lock"
        self._windows_handle: int | None = None
        self._posix_fd: int | None = None

    def __enter__(self) -> "ExclusiveConfirmationAttemptLock":
        self.lock_root.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            self._acquire_windows()
        else:
            self._acquire_posix()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback
        if self._windows_handle is not None:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [ctypes.c_void_p]
            close_handle.restype = ctypes.c_int
            if not close_handle(ctypes.c_void_p(self._windows_handle)):
                raise OSError(ctypes.get_last_error(), "CloseHandle failed.")
            self._windows_handle = None
        if self._posix_fd is not None:
            import fcntl

            try:
                fcntl.flock(self._posix_fd, fcntl.LOCK_UN)
            finally:
                os.close(self._posix_fd)
                self._posix_fd = None

    def _acquire_windows(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            ctypes.c_wchar_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        create_file.restype = ctypes.c_void_p
        generic_read_write = 0x80000000 | 0x40000000
        open_always = 4
        file_attribute_normal = 0x00000080
        handle = create_file(
            str(self.path),
            generic_read_write,
            0,
            None,
            open_always,
            file_attribute_normal,
            None,
        )
        invalid_handle_value = ctypes.c_void_p(-1).value
        if handle == invalid_handle_value:
            error = ctypes.get_last_error()
            if error in {32, 33}:
                raise ConfirmationAttemptLockBusy(str(self.path))
            raise OSError(error, "CreateFileW attempt lock failed.")
        self._windows_handle = int(handle)

    def _acquire_posix(self) -> None:
        import errno
        import fcntl

        file_descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(file_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(file_descriptor)
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise ConfirmationAttemptLockBusy(str(self.path)) from exc
            raise
        self._posix_fd = file_descriptor
