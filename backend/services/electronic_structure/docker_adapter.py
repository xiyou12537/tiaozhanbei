from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4


class ElectronicStructureRuntimeError(RuntimeError):
    """Raised when the isolated PySCF container cannot complete a requested calculation."""

    def __init__(self, message: str, diagnostic: dict | None = None) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic or {}


class DockerPySCFAdapter:
    """Execute small closed-shell HF candidate calculations in the pinned Linux PySCF image."""

    def __init__(self, image_name: str = "liangzhi-qchem:local", timeout_seconds: int = 120) -> None:
        self.image_name = image_name
        self.timeout_seconds = timeout_seconds

    def generate_active_space_candidates(
        self,
        request: dict,
        timeout_seconds: int | None = None,
        execution_options: dict | None = None,
    ) -> dict:
        """Run SCF candidate generation with an optional worker-specific timeout."""
        return self._run(request, timeout_seconds=timeout_seconds, execution_options=execution_options)

    def run_density_preconditioner(
        self,
        request: dict,
        timeout_seconds: int | None = None,
        execution_options: dict | None = None,
    ) -> dict:
        """Run an isolated density-only preconditioner without creating an SCF candidate."""
        return self._run(
            {**request, "operation": "density_preconditioner"},
            timeout_seconds=timeout_seconds,
            execution_options=execution_options,
        )

    def analyze_orbital_projections(
        self,
        request: dict,
        timeout_seconds: int | None = None,
        execution_options: dict | None = None,
    ) -> dict:
        """Read a validated checkpoint and analyze orbitals without invoking an SCF kernel."""
        return self._run(
            {**request, "operation": "orbital_projection_analysis"},
            timeout_seconds=timeout_seconds,
            execution_options=execution_options,
        )

    def build_checkpoint_active_space_benchmark(
        self,
        request: dict,
        timeout_seconds: int | None = None,
        execution_options: dict | None = None,
    ) -> dict:
        """Build a checkpoint-frozen UHF Hamiltonian and FCI result without starting SCF."""
        return self._run(
            {**request, "operation": "checkpoint_active_space_benchmark"},
            timeout_seconds=timeout_seconds,
            execution_options=execution_options,
        )

    def build_hamiltonian(self, request: dict) -> dict:
        return self._run({**request, "operation": "build_hamiltonian"})

    def map_hamiltonian(self, request: dict) -> dict:
        return self._run({**request, "operation": "map_hamiltonian"})

    def calculate_classical_reference(self, request: dict) -> dict:
        """Run a bounded PySCF FCI reference for a confirmed small closed-shell active space."""
        return self._run({**request, "operation": "classical_reference"})

    def _run(
        self,
        request: dict,
        timeout_seconds: int | None = None,
        execution_options: dict | None = None,
    ) -> dict:
        container_name = f"liangzhi-qchem-{uuid4().hex}"
        command = ["docker", "run", "--rm", "--name", container_name, "-i", self.image_name]
        options = execution_options or {}
        cpu_count = options.get("cpu_count")
        memory_limit_mb = options.get("memory_limit_mb")
        checkpoint_directory = options.get("checkpoint_directory")
        monitor = (
            self._start_resource_monitor(container_name, options.get("terminate_at_memory_bytes"))
            if options.get("monitor_resources")
            else None
        )
        if cpu_count is not None:
            command[2:2] = ["--cpus", str(cpu_count)]
        if memory_limit_mb is not None:
            memory_limit = f"{int(memory_limit_mb)}m"
            command[2:2] = ["--memory", memory_limit, "--memory-swap", memory_limit]
        if checkpoint_directory:
            host_directory = Path(checkpoint_directory).resolve()
            host_directory.mkdir(parents=True, exist_ok=True)
            command[2:2] = ["--mount", f"type=bind,src={host_directory},dst=/checkpoints"]
        for read_only_mount in options.get("read_only_mounts", []):
            source_path = Path(read_only_mount["source"]).resolve()
            if not source_path.is_file():
                raise ElectronicStructureRuntimeError(f"Read-only container input is missing: {source_path}")
            target_path = read_only_mount["target"]
            command[2:2] = [
                "--mount",
                f"type=bind,src={source_path},dst={target_path},readonly",
            ]
        if cpu_count is not None:
            thread_count = str(int(cpu_count))
            command[2:2] = [
                "--env",
                f"OMP_NUM_THREADS={thread_count}",
                "--env",
                f"OPENBLAS_NUM_THREADS={thread_count}",
                "--env",
                f"MKL_NUM_THREADS={thread_count}",
            ]
        effective_timeout = timeout_seconds or self.timeout_seconds
        try:
            completed = subprocess.run(
                command,
                input=json.dumps(request),
                text=True,
                encoding="utf-8",
                errors="strict",
                capture_output=True,
                timeout=effective_timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
            # `docker run --rm` does not reliably stop a child container when its
            # parent process is interrupted, so explicitly remove this named job.
            try:
                # A stuck SCF process can ignore Docker's grace-period signal.
                # Removing the uniquely named container with --force guarantees
                # that a bounded preflight does not leave compute behind.
                diagnostic = self._collect_timeout_diagnostic(container_name, checkpoint_directory)
                checkpoint_sha256_at_timeout = diagnostic.get("checkpoint_sha256")
                if monitor:
                    diagnostic["container_resource_monitor"] = self._resource_monitor_snapshot(monitor)
                diagnostic["output_decoding"] = {
                    "encoding": "utf-8",
                    "succeeded": not isinstance(exc, UnicodeError),
                }
                subprocess.run(
                    ["docker", "rm", "--force", container_name],
                    text=True,
                    capture_output=True,
                    timeout=15,
                    check=False,
                )
                post_stop_diagnostic = self._read_checkpoint_diagnostic(checkpoint_directory)
                diagnostic.update(post_stop_diagnostic)
                diagnostic["checkpoint_sha256_at_timeout"] = checkpoint_sha256_at_timeout
            except (OSError, subprocess.TimeoutExpired):
                diagnostic = self._read_checkpoint_diagnostic(checkpoint_directory)
            raise ElectronicStructureRuntimeError(
                "PySCF Docker runtime is unavailable or timed out.",
                diagnostic,
            ) from exc
        finally:
            if monitor:
                monitor["stop"].set()
                monitor["thread"].join(timeout=5)
        if completed.returncode != 0:
            message = completed.stderr.strip() or "PySCF calculation failed."
            diagnostic = self._read_checkpoint_diagnostic(checkpoint_directory)
            diagnostic.update(
                {
                    "docker_exit_code": completed.returncode,
                    "oom_suspected": completed.returncode in {137, 139} or "oom" in message.lower(),
                    "output_decoding": {"encoding": "utf-8", "succeeded": True},
                }
            )
            if monitor:
                diagnostic["container_resource_monitor"] = self._resource_monitor_snapshot(monitor)
            raise ElectronicStructureRuntimeError(message, diagnostic)
        try:
            if completed.stdout is None:
                raise ElectronicStructureRuntimeError(
                    "PySCF container output could not be decoded.",
                    self._read_checkpoint_diagnostic(checkpoint_directory),
                )
            result = json.loads(completed.stdout)
            result.setdefault("execution_metadata", {}).update(
                {
                    "container_cpu_limit": cpu_count,
                    "container_memory_limit_mb": memory_limit_mb,
                    "checkpoint_sha256": self._checkpoint_hash(checkpoint_directory),
                    "checkpoint_size_bytes": self._checkpoint_size(checkpoint_directory),
                    "df_cderi_sha256": self._artifact_hash(checkpoint_directory, "df_cderi.h5"),
                    "density_sha256": self._artifact_hash(checkpoint_directory, "uks_density.npz"),
                    "density_size_bytes": self._artifact_size(checkpoint_directory, "uks_density.npz"),
                    "checkpoint_directory": "/checkpoints" if checkpoint_directory else None,
                    "container_resource_monitor": self._resource_monitor_snapshot(monitor) if monitor else None,
                    "output_decoding": {"encoding": "utf-8", "succeeded": True},
                }
            )
            return result
        except json.JSONDecodeError as exc:
            diagnostic = self._read_checkpoint_diagnostic(checkpoint_directory)
            diagnostic["output_decoding"] = {"encoding": "utf-8", "succeeded": True}
            raise ElectronicStructureRuntimeError("PySCF container returned an invalid result.", diagnostic) from exc

    @staticmethod
    def _checkpoint_hash(checkpoint_directory: str | None) -> str | None:
        if not checkpoint_directory:
            return None
        checkpoint_path = Path(checkpoint_directory) / "scf.chk"
        return sha256(checkpoint_path.read_bytes()).hexdigest() if checkpoint_path.is_file() else None

    @staticmethod
    def _artifact_hash(checkpoint_directory: str | None, filename: str) -> str | None:
        if not checkpoint_directory:
            return None
        artifact_path = Path(checkpoint_directory) / filename
        if not artifact_path.is_file():
            return None
        digest = sha256()
        with artifact_path.open("rb") as artifact_file:
            for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _checkpoint_size(checkpoint_directory: str | None) -> int | None:
        if not checkpoint_directory:
            return None
        checkpoint_path = Path(checkpoint_directory) / "scf.chk"
        return checkpoint_path.stat().st_size if checkpoint_path.is_file() else None

    @staticmethod
    def _artifact_size(checkpoint_directory: str | None, filename: str) -> int | None:
        if not checkpoint_directory:
            return None
        artifact_path = Path(checkpoint_directory) / filename
        return artifact_path.stat().st_size if artifact_path.is_file() else None

    def _collect_timeout_diagnostic(self, container_name: str, checkpoint_directory: str | None) -> dict:
        diagnostic = self._read_checkpoint_diagnostic(checkpoint_directory, include_artifact_hashes=False)
        try:
            stats = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", container_name],
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if stats.returncode == 0 and stats.stdout.strip():
                diagnostic["docker_stats"] = json.loads(stats.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return diagnostic

    def _start_resource_monitor(self, container_name: str, terminate_at_memory_bytes: int | None = None) -> dict:
        monitor = {
            "stop": threading.Event(),
            "lock": threading.Lock(),
            "samples": [],
            "terminate_at_memory_bytes": terminate_at_memory_bytes,
            "terminated_for_memory_limit": False,
        }

        def poll() -> None:
            while not monitor["stop"].wait(0.4):
                sample = self._container_resource_sample(container_name)
                if sample is None:
                    continue
                with monitor["lock"]:
                    monitor["samples"].append(sample)
                memory_usage = sample.get("memory_usage_bytes")
                if terminate_at_memory_bytes is not None and memory_usage is not None and memory_usage >= terminate_at_memory_bytes:
                    with monitor["lock"]:
                        monitor["terminated_for_memory_limit"] = True
                    subprocess.run(
                        ["docker", "rm", "--force", container_name],
                        text=True,
                        capture_output=True,
                        timeout=10,
                        check=False,
                    )
                    monitor["stop"].set()
                    break

        monitor["thread"] = threading.Thread(target=poll, name=f"docker-stats-{container_name}", daemon=True)
        monitor["thread"].start()
        return monitor

    @staticmethod
    def _container_resource_sample(container_name: str) -> dict | None:
        try:
            completed = subprocess.run(
                ["docker", "stats", "--no-stream", "--format", "{{json .}}", container_name],
                text=True,
                capture_output=True,
                timeout=3,
                check=False,
            )
            if completed.returncode != 0 or not completed.stdout.strip():
                return None
            payload = json.loads(completed.stdout)
            kernel_peaks = DockerPySCFAdapter._container_kernel_peaks(container_name)
            return {
                "timestamp_monotonic": time.monotonic(),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "raw": payload,
                "memory_usage_bytes": DockerPySCFAdapter._memory_usage_bytes(payload.get("MemUsage", "")),
                **kernel_peaks,
            }
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return None

    @staticmethod
    def _container_kernel_peaks(container_name: str) -> dict:
        """Read cgroup and main-process high-water marks while the container is alive."""
        try:
            completed = subprocess.run(
                [
                    "docker",
                    "exec",
                    container_name,
                    "sh",
                    "-c",
                    "printf 'cgroup='; cat /sys/fs/cgroup/memory.peak 2>/dev/null; "
                    "printf '\\nrss_kib='; awk '/VmHWM:/ {print $2}' /proc/1/status 2>/dev/null",
                ],
                text=True,
                encoding="utf-8",
                errors="strict",
                capture_output=True,
                timeout=3,
                check=False,
            )
            values = completed.stdout.splitlines() if completed.returncode == 0 else []
            parsed_values = dict(value.split("=", 1) for value in values if "=" in value)
            cgroup_value = parsed_values.get("cgroup", "")
            process_value = parsed_values.get("rss_kib", "")
            cgroup_peak = int(cgroup_value) if cgroup_value.isdigit() else None
            process_peak_kib = int(process_value) if process_value.isdigit() else None
            return {
                "cgroup_memory_peak_bytes": cgroup_peak,
                "process_peak_rss_bytes": process_peak_kib * 1024 if process_peak_kib is not None else None,
            }
        except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError):
            return {"cgroup_memory_peak_bytes": None, "process_peak_rss_bytes": None}

    @staticmethod
    def _memory_usage_bytes(memory_usage: str) -> int | None:
        match = re.match(r"\s*([0-9.]+)\s*([KMGT]?i?B)", memory_usage)
        if not match:
            return None
        value = float(match.group(1))
        unit = match.group(2)
        factors = {"B": 1, "KB": 1000, "MB": 1000**2, "GB": 1000**3, "TB": 1000**4, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}
        return int(value * factors[unit])

    @staticmethod
    def _resource_monitor_snapshot(monitor: dict | None) -> dict | None:
        if not monitor:
            return None
        with monitor["lock"]:
            samples = list(monitor["samples"])
        memory_samples = [sample["memory_usage_bytes"] for sample in samples if sample["memory_usage_bytes"] is not None]
        cgroup_peak_samples = [
            sample["cgroup_memory_peak_bytes"]
            for sample in samples
            if sample.get("cgroup_memory_peak_bytes") is not None
        ]
        process_peak_samples = [
            sample["process_peak_rss_bytes"]
            for sample in samples
            if sample.get("process_peak_rss_bytes") is not None
        ]
        peak_sample = (
            max(
                (sample for sample in samples if sample["memory_usage_bytes"] is not None),
                key=lambda sample: sample["memory_usage_bytes"],
            )
            if memory_samples
            else None
        )
        return {
            "sample_count": len(samples),
            "peak_memory_bytes": max(memory_samples) if memory_samples else None,
            "peak_sample_timestamp_utc": peak_sample.get("timestamp_utc") if peak_sample else None,
            "peak_sample_timestamp_monotonic": peak_sample.get("timestamp_monotonic") if peak_sample else None,
            "cgroup_memory_peak_bytes": max(cgroup_peak_samples) if cgroup_peak_samples else None,
            "cgroup_memory_peak_available": bool(cgroup_peak_samples),
            "monitored_process_peak_rss_bytes": max(process_peak_samples) if process_peak_samples else None,
            "terminate_at_memory_bytes": monitor["terminate_at_memory_bytes"],
            "terminated_for_memory_limit": monitor["terminated_for_memory_limit"],
            "samples": samples,
        }

    def _read_checkpoint_diagnostic(
        self,
        checkpoint_directory: str | None,
        *,
        include_artifact_hashes: bool = True,
    ) -> dict:
        if not checkpoint_directory:
            return {}
        checkpoint_root = Path(checkpoint_directory)
        progress_path = checkpoint_root / "scf_progress.jsonl"
        validation_path = checkpoint_root / "checkpoint_validation.json"
        iterations: list[dict] = []
        if progress_path.is_file():
            for line in progress_path.read_text(encoding="utf-8").splitlines():
                try:
                    iterations.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        checkpoint_validation = None
        if validation_path.is_file():
            try:
                checkpoint_validation = json.loads(validation_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                checkpoint_validation = {"status": "invalid_json"}
        return {
            "checkpoint_sha256": self._checkpoint_hash(checkpoint_directory),
            "checkpoint_available": (checkpoint_root / "scf.chk").is_file(),
            "checkpoint_size_bytes": self._checkpoint_size(checkpoint_directory),
            "df_cderi_available": (checkpoint_root / "df_cderi.h5").is_file(),
            "df_cderi_size_bytes": (
                (checkpoint_root / "df_cderi.h5").stat().st_size
                if (checkpoint_root / "df_cderi.h5").is_file()
                else None
            ),
            "df_cderi_sha256": (
                self._artifact_hash(checkpoint_directory, "df_cderi.h5") if include_artifact_hashes else None
            ),
            "density_available": (checkpoint_root / "uks_density.npz").is_file(),
            "density_size_bytes": self._artifact_size(checkpoint_directory, "uks_density.npz"),
            "density_sha256": (
                self._artifact_hash(checkpoint_directory, "uks_density.npz") if include_artifact_hashes else None
            ),
            "checkpoint_validation": checkpoint_validation,
            "last_scf_iteration": iterations[-1] if iterations else None,
            "scf_iteration_log": iterations,
        }
