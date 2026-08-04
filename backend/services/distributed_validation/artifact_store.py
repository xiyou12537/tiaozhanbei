from __future__ import annotations

import ctypes
import errno
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import (
    canonical_artifact_bytes,
    canonical_artifact_path,
    sha256_bytes,
    sha256_file,
)


class ArtifactStoreError(RuntimeError):
    """Raised when a canonical artifact cannot be published safely."""


@dataclass(frozen=True)
class PublishedArtifact:
    relative_path: str
    absolute_path: Path
    sha256: str
    size_bytes: int
    durability_method: str


class NoClobberArtifactStore:
    """Publish fully fsynced canonical files without replacing existing paths."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def publish_json(
        self,
        relative_path: str,
        payload: dict[str, Any],
        *,
        max_size_bytes: int,
    ) -> PublishedArtifact:
        data = canonical_artifact_bytes(payload)
        return self.publish_bytes(
            relative_path,
            data,
            max_size_bytes=max_size_bytes,
        )

    def publish_bytes(
        self,
        relative_path: str,
        data: bytes,
        *,
        max_size_bytes: int,
    ) -> PublishedArtifact:
        normalized = canonical_artifact_path(relative_path)
        if len(data) > max_size_bytes:
            raise ArtifactStoreError("Artifact exceeds the frozen size guardrail.")
        final_path = self.root / Path(*normalized.split("/"))
        try:
            final_path.relative_to(self.root)
        except ValueError as exc:
            raise ArtifactStoreError(
                "Artifact path escapes the configured root."
            ) from exc
        if final_path == self.root:
            raise ArtifactStoreError("Artifact path must name a file below the root.")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = final_path.parent / f".{final_path.name}.{uuid.uuid4().hex}.tmp"

        descriptor = os.open(
            temp_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            expected_sha = sha256_bytes(data)
            if sha256_file(temp_path) != expected_sha:
                raise ArtifactStoreError("Temporary artifact SHA-256 mismatch.")
            durability_method = self._publish_no_clobber(temp_path, final_path)
            if sha256_file(final_path) != expected_sha:
                raise ArtifactStoreError("Published artifact SHA-256 mismatch.")
            return PublishedArtifact(
                relative_path=normalized,
                absolute_path=final_path,
                sha256=expected_sha,
                size_bytes=len(data),
                durability_method=durability_method,
            )
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def _publish_no_clobber(self, temp_path: Path, final_path: Path) -> str:
        if os.name == "nt":
            move_file_ex = ctypes.windll.kernel32.MoveFileExW
            move_file_ex.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
            move_file_ex.restype = ctypes.c_int
            movefile_write_through = 0x00000008
            success = move_file_ex(
                str(temp_path),
                str(final_path),
                movefile_write_through,
            )
            if not success:
                error_code = ctypes.get_last_error()
                if final_path.exists():
                    raise FileExistsError(
                        errno.EEXIST,
                        "Artifact target already exists.",
                        str(final_path),
                    )
                raise ArtifactStoreError(
                    f"MoveFileExW failed with Windows error {error_code}."
                )
            return "movefileex_write_through"

        try:
            os.link(temp_path, final_path)
        except FileExistsError:
            raise
        except OSError as exc:
            if exc.errno in {errno.EXDEV, errno.EOPNOTSUPP, errno.ENOTSUP}:
                raise ArtifactStoreError(
                    "Atomic no-clobber publication is unsupported on this filesystem."
                ) from exc
            raise
        temp_path.unlink()
        directory_fd = os.open(final_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return "linkat_and_directory_fsync"
