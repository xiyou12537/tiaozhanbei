from __future__ import annotations

import json
import subprocess


class ElectronicStructureRuntimeError(RuntimeError):
    """Raised when the isolated PySCF container cannot complete a requested calculation."""


class DockerPySCFAdapter:
    """Execute small closed-shell HF candidate calculations in the pinned Linux PySCF image."""

    def __init__(self, image_name: str = "liangzhi-qchem:local", timeout_seconds: int = 120) -> None:
        self.image_name = image_name
        self.timeout_seconds = timeout_seconds

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
        command = ["docker", "run", "--rm", "-i", self.image_name]
        effective_timeout = timeout_seconds or self.timeout_seconds
        try:
            completed = subprocess.run(command, input=json.dumps(request), text=True, capture_output=True, timeout=effective_timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ElectronicStructureRuntimeError("PySCF Docker runtime is unavailable or timed out.") from exc
        if completed.returncode != 0:
            message = completed.stderr.strip() or "PySCF calculation failed."
            raise ElectronicStructureRuntimeError(message)
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ElectronicStructureRuntimeError("PySCF container returned an invalid result.") from exc
