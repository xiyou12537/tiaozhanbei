from __future__ import annotations

import json
import logging
import subprocess
import time
import uuid

logger = logging.getLogger(__name__)


class ElectronicStructureRuntimeError(RuntimeError):
    """Raised when the isolated PySCF container cannot complete a requested calculation."""


class DockerPySCFAdapter:
    """Execute small closed-shell HF candidate calculations in the pinned Linux PySCF image."""

    def __init__(
        self,
        image_name: str = "liangzhi-qchem:local",
        timeout_seconds: int = 120,
        startup_retry_count: int = 2,
    ) -> None:
        self.image_name = image_name
        self.timeout_seconds = timeout_seconds
        self.startup_retry_count = startup_retry_count

    def generate_active_space_candidates(self, request: dict, timeout_seconds: int | None = None) -> dict:
        """Run SCF candidate generation with an optional worker-specific timeout."""
        return self._run(request, timeout_seconds=timeout_seconds)

    def build_hamiltonian(self, request: dict) -> dict:
        return self._run({**request, "operation": "build_hamiltonian"})

    def map_hamiltonian(self, request: dict) -> dict:
        return self._run({**request, "operation": "map_hamiltonian"})

    def calculate_classical_reference(self, request: dict) -> dict:
        """Run a bounded PySCF FCI reference for a confirmed small closed-shell active space."""
        return self._run({**request, "operation": "classical_reference"})

    def _run(self, request: dict, timeout_seconds: int | None = None) -> dict:
        effective_timeout = timeout_seconds or self.timeout_seconds
        operation = str(request.get("operation", "active_space_candidates"))
        for attempt in range(self.startup_retry_count + 1):
            readiness = self._docker_readiness()
            if readiness is not None:
                category, return_code = readiness
                self._log_failure(category, return_code, operation)
                if attempt < self.startup_retry_count:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise ElectronicStructureRuntimeError(
                    f"PySCF Docker runtime is unavailable (category={category}, return_code={return_code})."
                )

            container_name = f"liangzhi-qchem-{uuid.uuid4().hex}"
            command = ["docker", "run", "--rm", "--name", container_name, "-i", self.image_name]
            try:
                completed = subprocess.run(
                    command,
                    input=json.dumps(request),
                    text=True,
                    capture_output=True,
                    timeout=effective_timeout,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                self._cleanup_container(container_name)
                category = "docker_client_unavailable" if isinstance(exc, OSError) else "docker_timeout"
                self._log_failure(category, None, operation)
                if category == "docker_client_unavailable" and attempt < self.startup_retry_count:
                    time.sleep(0.25 * (attempt + 1))
                    continue
                raise ElectronicStructureRuntimeError(
                    f"PySCF Docker runtime is unavailable (category={category})."
                ) from exc

            if completed.returncode == 0:
                try:
                    return json.loads(completed.stdout)
                except json.JSONDecodeError as exc:
                    self._log_failure("invalid_container_result", 0, operation)
                    raise ElectronicStructureRuntimeError("PySCF container returned an invalid result.") from exc

            category = self._classify_failure(completed.stderr)
            self._log_failure(category, completed.returncode, operation)
            if category == "docker_daemon_unavailable" and attempt < self.startup_retry_count:
                time.sleep(0.25 * (attempt + 1))
                continue
            raise ElectronicStructureRuntimeError(
                f"PySCF Docker calculation failed (category={category}, return_code={completed.returncode})."
            )

        raise AssertionError("Docker retry loop must return or raise.")

    @staticmethod
    def _classify_failure(stderr: str) -> str:
        message = (stderr or "").lower()
        if any(marker in message for marker in ("cannot connect to the docker daemon", "error during connect", "dockerdesktoplinuxengine")):
            return "docker_daemon_unavailable"
        if "no such image" in message or "pull access denied" in message:
            return "docker_image_unavailable"
        return "container_process_failed"

    def _docker_readiness(self) -> tuple[str, int | None] | None:
        """Check the daemon before starting PySCF, without emitting daemon output."""
        try:
            completed = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
        except OSError:
            return "docker_client_unavailable", None
        except subprocess.TimeoutExpired:
            return "docker_daemon_unavailable", None
        if completed.returncode != 0 or not completed.stdout.strip():
            return "docker_daemon_unavailable", completed.returncode
        return None

    @staticmethod
    def _log_failure(category: str, return_code: int | None, operation: str) -> None:
        # Keep diagnostic output useful for operations without exposing Docker
        # stderr, environment values, working directories, or container names.
        logger.warning(
            "PySCF Docker invocation failed: category=%s return_code=%s operation=%s",
            category,
            return_code,
            operation,
        )

    @staticmethod
    def _cleanup_container(container_name: str) -> None:
        # A timed-out Docker client can leave the named child behind despite
        # --rm. The generated name remains private and is not logged.
        try:
            subprocess.run(
                ["docker", "rm", "-f", container_name],
                text=True,
                capture_output=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
