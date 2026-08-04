from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path

import pytest


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
FORMAL_DATA_ROOT = WORKSPACE_ROOT / "data"
TEST_ROOT = Path(tempfile.mkdtemp(prefix="distributed-validation-tests-")).resolve()
TEST_DATA_ROOT = TEST_ROOT / "data"
TEST_ARTIFACT_ROOT = TEST_DATA_ROOT / "structure_artifacts"
TEST_DATABASE_PATH = TEST_DATA_ROOT / "partitioning.db"

# These variables are set during conftest import, before pytest imports application
# modules that otherwise bind global database and Artifact paths.
os.environ["PLATFORM_DATA_ROOT"] = str(TEST_DATA_ROOT)
os.environ["LEGACY_DATABASE_PATH"] = str(TEST_DATABASE_PATH)
os.environ["LEGACY_SCHEMA_INITIALIZATION_MODE"] = "create_for_tests"
os.environ["M_B_ENGINEERING_TEST_MODE"] = "true"
os.environ["MOLECULAR_ARTIFACT_ROOT"] = str(TEST_ARTIFACT_ROOT / "molecular")
TEST_ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

FORMAL_EVIDENCE_PATHS = (
    FORMAL_DATA_ROOT / "partitioning.db",
    FORMAL_DATA_ROOT
    / "backups"
    / "partitioning.pre-stage-b.20260728T102950095.db",
    FORMAL_DATA_ROOT
    / "structure_artifacts"
    / "distributed_molecular_circuit_validation_protocol_v1.json",
    FORMAL_DATA_ROOT
    / "structure_artifacts"
    / "distributed_validation"
    / "dmc_a728180ea4944d36a83ee4dde1762f04"
    / "chip_mapping.json",
    FORMAL_DATA_ROOT
    / "structure_artifacts"
    / "distributed_validation"
    / "dmc_a728180ea4944d36a83ee4dde1762f04"
    / "communication_route_plan.json",
    FORMAL_DATA_ROOT
    / "structure_artifacts"
    / "distributed_validation"
    / "dmc_a728180ea4944d36a83ee4dde1762f04"
    / "distributed_executable.json",
    FORMAL_DATA_ROOT
    / "structure_artifacts"
    / "distributed_validation"
    / "dmc_a728180ea4944d36a83ee4dde1762f04"
    / "input_manifest.json",
    FORMAL_DATA_ROOT
    / "structure_artifacts"
    / "distributed_validation"
    / "dmc_a728180ea4944d36a83ee4dde1762f04"
    / "logical_circuit_snapshot.json",
    FORMAL_DATA_ROOT
    / "structure_artifacts"
    / "distributed_validation"
    / "dmc_a728180ea4944d36a83ee4dde1762f04"
    / "optimized_gate_order.json",
    FORMAL_DATA_ROOT
    / "structure_artifacts"
    / "distributed_validation"
    / "dmc_a728180ea4944d36a83ee4dde1762f04"
    / "partition_plan.json",
    FORMAL_DATA_ROOT
    / "structure_artifacts"
    / "distributed_validation"
    / "dmc_a728180ea4944d36a83ee4dde1762f04"
    / "target_topology.json",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


FORMAL_EVIDENCE_BASELINE = {
    str(path): {"sha256": _sha256(path), "size_bytes": path.stat().st_size}
    for path in FORMAL_EVIDENCE_PATHS
}


@pytest.fixture(scope="session")
def isolated_test_root() -> Path:
    """Return the session-scoped root used for all mutable test evidence."""
    return TEST_ROOT


@pytest.fixture(scope="session")
def formal_evidence_baseline() -> dict[str, dict[str, str | int]]:
    """Expose the immutable evidence baseline for explicit regression checks."""
    return FORMAL_EVIDENCE_BASELINE


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del exitstatus
    changed: list[str] = []
    for raw_path, expected in FORMAL_EVIDENCE_BASELINE.items():
        path = Path(raw_path)
        actual = {
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        if actual != expected:
            changed.append(
                f"{path}: expected={expected!r}, actual={actual!r}"
            )
    if changed:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_sep(
                "!",
                "FORMAL EVIDENCE MUTATION DETECTED",
                red=True,
            )
            for detail in changed:
                reporter.write_line(detail, red=True)
    shutil.rmtree(TEST_ROOT, ignore_errors=True)
