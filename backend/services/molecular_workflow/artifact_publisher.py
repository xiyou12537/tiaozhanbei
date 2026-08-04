"""No-clobber Artifact publication and evidence-only reconciliation."""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

PATH_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}
ALLOWED_FILENAMES = frozenset(
    {"canonical_molecular_geometry.json", "molecular_input_manifest.json"}
)


class ArtifactPublicationError(RuntimeError):
    """Raised when a no-clobber publication cannot complete."""

    def __init__(self, code: str, stage: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage


@dataclass(frozen=True)
class PublicationResult:
    relative_path: str
    sha256: str
    size_bytes: int


class NoClobberArtifactPublisher:
    """Publish exact bytes only when the final target does not exist."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _target(self, relative_path: str) -> Path:
        raw_parts = Path(relative_path).parts
        if len(raw_parts) < 2 or raw_parts[-1] not in ALLOWED_FILENAMES:
            raise ArtifactPublicationError(
                "artifact_path_invalid", "path_validation", "Artifact filename is not frozen."
            )
        for segment in raw_parts[:-1]:
            lowered = segment.lower()
            if (
                not PATH_SEGMENT.fullmatch(segment)
                or lowered in WINDOWS_RESERVED
                or any(0xD800 <= ord(character) <= 0xDFFF for character in segment)
            ):
                raise ArtifactPublicationError(
                    "artifact_path_invalid", "path_validation", "Artifact path segment is invalid."
                )
        target = (self.root.joinpath(*raw_parts)).resolve()
        if self.root not in target.parents:
            raise ArtifactPublicationError(
                "artifact_path_escape", "path_validation", "Artifact path escapes its root."
            )
        return target

    def publish(
        self,
        relative_path: str,
        payload: bytes,
        *,
        crash_after: str | None = None,
    ) -> PublicationResult:
        """Write exact bytes and promote with an OS-level no-clobber primitive."""
        target = self._target(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.parent / f".{target.name}.{uuid.uuid4().hex}.pending"
        try:
            with temporary.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            if crash_after == "temp_fsync":
                raise ArtifactPublicationError(
                    "crash_injected", "after_temp_fsync", "Injected publication crash."
                )
            self._promote_no_clobber(temporary, target)
            if crash_after == "promote":
                raise ArtifactPublicationError(
                    "crash_injected", "after_promote", "Injected publication crash."
                )
        except FileExistsError as exc:
            raise ArtifactPublicationError(
                "artifact_target_exists", "promote_no_clobber", "Artifact target already exists."
            ) from exc
        except ArtifactPublicationError:
            raise
        except OSError as exc:
            raise ArtifactPublicationError(
                "artifact_storage_io_failed",
                "storage_io",
                "Artifact storage operation failed.",
            ) from exc
        finally:
            if temporary.exists():
                temporary.unlink()
        try:
            published_bytes = target.read_bytes()
        except OSError as exc:
            raise ArtifactPublicationError(
                "artifact_storage_io_failed",
                "post_publish_verify",
                "Published Artifact could not be reopened for verification.",
            ) from exc
        expected_digest = hashlib.sha256(payload).hexdigest()
        actual_digest = hashlib.sha256(published_bytes).hexdigest()
        if actual_digest != expected_digest or published_bytes != payload:
            raise ArtifactPublicationError(
                "artifact_post_publish_mismatch",
                "post_publish_verify",
                "Published Artifact bytes differ from the frozen payload.",
            )
        return PublicationResult(relative_path, actual_digest, len(published_bytes))

    @staticmethod
    def _promote_no_clobber(source: Path, target: Path) -> None:
        if os.name == "nt":
            move_file_ex = ctypes.windll.kernel32.MoveFileExW
            move_file_ex.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
            move_file_ex.restype = ctypes.c_int
            movefile_write_through = 0x00000008
            if not move_file_ex(str(source), str(target), movefile_write_through):
                error = ctypes.get_last_error()
                if target.exists():
                    raise FileExistsError(str(target))
                raise OSError(error, "MoveFileExW failed without replacement")
            return
        os.link(source, target)
        source.unlink()

    def reconcile_existing(
        self,
        relative_path: str,
        expected_sha256: str,
    ) -> PublicationResult:
        """Validate existing bytes; never recreate a missing Artifact."""
        target = self._target(relative_path)
        if not target.is_file():
            raise ArtifactPublicationError(
                "artifact_missing",
                "reconcile_existing",
                "Missing Artifact cannot be reconstructed during reconciliation.",
            )
        payload = target.read_bytes()
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ArtifactPublicationError(
                "artifact_sha256_mismatch",
                "reconcile_existing",
                "Existing Artifact bytes do not match the journal.",
            )
        return PublicationResult(relative_path, actual_sha256, len(payload))
