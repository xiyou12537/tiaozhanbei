from __future__ import annotations

import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend.services.electronic_structure.docker_adapter import (
    DockerPySCFAdapter,
    ElectronicStructureRuntimeError,
)


def test_timeout_force_removes_named_pyscf_container():
    """A bounded SCF worker must not leave an orphaned Docker container."""
    adapter = DockerPySCFAdapter(timeout_seconds=1)
    timeout = subprocess.TimeoutExpired(cmd=["docker", "run"], timeout=1)

    with patch(
        "backend.services.electronic_structure.docker_adapter.subprocess.run",
        side_effect=[
            timeout,
            SimpleNamespace(returncode=0, stdout="{}"),
            SimpleNamespace(returncode=0),
        ],
    ) as mocked_run:
        with pytest.raises(ElectronicStructureRuntimeError, match="timed out"):
            adapter.generate_active_space_candidates({"operation": "scf"})

    cleanup_command = mocked_run.call_args_list[2].args[0]
    assert cleanup_command[:3] == ["docker", "rm", "--force"]
    assert cleanup_command[3].startswith("liangzhi-qchem-")


def test_resource_monitor_snapshot_preserves_peak_value_and_timestamp():
    monitor = {
        "lock": threading.Lock(),
        "samples": [
            {
                "memory_usage_bytes": 100,
                "cgroup_memory_peak_bytes": 110,
                "process_peak_rss_bytes": 90,
                "timestamp_utc": "first",
                "timestamp_monotonic": 1.0,
            },
            {
                "memory_usage_bytes": 200,
                "cgroup_memory_peak_bytes": 220,
                "process_peak_rss_bytes": 180,
                "timestamp_utc": "peak",
                "timestamp_monotonic": 2.0,
            },
        ],
        "terminate_at_memory_bytes": 250,
        "terminated_for_memory_limit": False,
    }

    snapshot = DockerPySCFAdapter._resource_monitor_snapshot(monitor)

    assert snapshot["peak_memory_bytes"] == 200
    assert snapshot["peak_sample_timestamp_utc"] == "peak"
    assert snapshot["peak_sample_timestamp_monotonic"] == 2.0
    assert snapshot["cgroup_memory_peak_bytes"] == 220
    assert snapshot["monitored_process_peak_rss_bytes"] == 180
