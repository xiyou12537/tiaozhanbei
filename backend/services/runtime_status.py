from __future__ import annotations

from typing import Any, Callable


def load_circuit_runtime() -> tuple[Callable[..., Any], Callable[..., Any], Callable[..., Any]]:
    """Load circuit parsing helpers on demand to avoid blocking API startup."""
    try:
        from quantum_partitioning.circuit_utils import extract_qubits, remove_single_qubit_gates
        from quantum_partitioning.qasm_io import load_qasm_string
    except Exception as exc:  # pragma: no cover - exercised through callers
        raise RuntimeError(f"量子线路解析依赖不可用: {exc}") from exc

    return load_qasm_string, remove_single_qubit_gates, extract_qubits


def load_partition_pipeline() -> Callable[..., Any]:
    """Load the partitioning pipeline on demand to avoid blocking API startup."""
    try:
        from quantum_partitioning.partitioning import run_partitioning_pipeline
    except Exception as exc:  # pragma: no cover - exercised through callers
        raise RuntimeError(f"量子分区依赖不可用: {exc}") from exc

    return run_partitioning_pipeline


def get_quantum_runtime_status() -> dict[str, dict[str, str]]:
    """Summarize the availability of quantum-related runtime dependencies."""
    services = {
        "circuit_parser": {"status": "ok", "detail": "量子线路解析模块可用。"},
        "partitioning": {"status": "ok", "detail": "量子分区模块可用。"},
    }

    try:
        load_circuit_runtime()
    except RuntimeError as exc:
        services["circuit_parser"] = {"status": "degraded", "detail": str(exc)}

    try:
        load_partition_pipeline()
    except RuntimeError as exc:
        services["partitioning"] = {"status": "degraded", "detail": str(exc)}

    return services
