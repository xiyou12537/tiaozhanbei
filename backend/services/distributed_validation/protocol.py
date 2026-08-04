from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifact_store import NoClobberArtifactStore, PublishedArtifact
from .canonical import (
    ARTIFACT_CANONICAL_SCHEME,
    ORDERED_PAULI_SCHEME,
    PARAMETER_HASH_SCHEME,
    QASM_CANONICAL_SCHEME,
)

PROTOCOL_ID = "distributed_molecular_circuit_validation"
PROTOCOL_VERSION = "1.0.0"
PROTOCOL_API_ALIAS = "distributed_molecular_circuit_v1"
PROTOCOL_FILENAME = "distributed_molecular_circuit_validation_protocol_v1.json"

TOPOLOGY_4Q_SHA256 = "c7587d1aca795ae2c2039204f3360594eb6e9969083b8e7f470412e2e96721bc"
TOPOLOGY_8Q_SHA256 = "5bdfd27b4eafed3ced5fe06af793151182d3d3e748968ece25b25d723a972663"


def _level(
    *,
    level: str,
    qubit_count: int,
    node_capacity: int,
    topology_sha256: str,
    maximum_expanded_gate_count: int,
    maximum_artifact_size_bytes: int,
    maximum_artifact_total_bytes: int,
    maximum_qasm_size_bytes: int,
    compilation_wall_seconds: int,
    simulation_wall_seconds: int,
    rss_limit_bytes: int,
    available_memory_bytes: int,
    available_disk_bytes: int,
) -> dict[str, Any]:
    return {
        "level": level,
        "qubit_count": qubit_count,
        "partition_count": 2,
        "node_count": 2,
        "qubit_capacity_per_node": node_capacity,
        "topology_name": f"linear-2-capacity-{node_capacity}",
        "topology_sha256": topology_sha256,
        "maximum_expanded_gate_count": maximum_expanded_gate_count,
        "maximum_circuit_depth": maximum_expanded_gate_count,
        "maximum_artifact_size_bytes": maximum_artifact_size_bytes,
        "maximum_artifact_total_bytes": maximum_artifact_total_bytes,
        "maximum_qasm_size_bytes": maximum_qasm_size_bytes,
        "compilation_wall_seconds": compilation_wall_seconds,
        "simulation_wall_seconds": simulation_wall_seconds,
        "total_wall_seconds": compilation_wall_seconds + simulation_wall_seconds,
        "rss_limit_bytes": rss_limit_bytes,
        "minimum_available_memory_bytes": available_memory_bytes,
        "minimum_available_disk_bytes": available_disk_bytes,
        "formal_attempt_limit": 1,
    }


def build_protocol_payload(created_at: datetime | None = None) -> dict[str, Any]:
    """Build the complete immutable Stage-A-approved V1 protocol payload."""
    timestamp = created_at or datetime.now(timezone.utc)
    return {
        "artifact_type": "distributed_molecular_circuit_validation_protocol",
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "protocol_version": PROTOCOL_VERSION,
        "protocol_api_alias": PROTOCOL_API_ALIAS,
        "created_at": timestamp,
        "immutable": True,
        "owner_user_id": 183,
        "stage_a_design": "accepted",
        "stage_b_authorized": True,
        "stage_c_authorized": False,
        "hash_schemes": {
            "artifact": ARTIFACT_CANONICAL_SCHEME,
            "qasm": QASM_CANONICAL_SCHEME,
            "parameters": PARAMETER_HASH_SCHEME,
            "ordered_pauli": ORDERED_PAULI_SCHEME,
            "digest": "sha256",
        },
        "execution_semantics": {
            "strategy": "topology_aware_remote_swap_route_and_restore",
            "description": "classical_statevector_distributed_communication_semantics",
            "actual_distributed_hardware_execution": False,
            "custom_remote_gate_allowed": False,
            "standard_gate_set": ["u3", "cx"],
            "shots": 0,
            "statevector_dtype": "complex128",
            "optimizer_execution_allowed": False,
            "parameter_rebinding_allowed": False,
            "hamiltonian_rebuild_allowed": False,
            "topology_replacement_allowed": False,
            "automatic_retry_allowed": False,
        },
        "partitioning": {
            "algorithm": "deterministic_greedy_multistart_grid_v1",
            "partition_ids": [0, 1],
            "partition_count": 2,
            "maximum_imbalance": 1,
            "b1_grid": list(range(1, 21)),
            "b2_grid": list(range(1, 21)),
            "alpha": 3.0,
            "beta": 1.0,
            "num_starts_rule": "min(15,qubit_count)",
            "seed": 20260728,
            "stochastic_behavior_allowed": False,
            "partition_numbering": "minimum_logical_qubit_ascending_then_zero_based",
            "candidate_tie_break": [
                "estimated_teleportations",
                "global_gate_count",
                "cross_partition_gate_count",
                "load_difference",
                "partition_signature",
                "b1",
                "b2",
                "seed_qubit",
            ],
        },
        "gate_ordering": {
            "scheme": "disjoint-support-only-v1",
            "unsupported_commutation_fallback": "fail",
            "equivalence_infidelity_maximum": 1e-12,
        },
        "mapping": {
            "algorithm": "minimum_cost_then_lexicographic_mapping_v1",
            "equal_cost_tie_break": "lexicographically_smallest_sorted_integer_partition_node_pairs",
            "frozen_equal_cost_mapping": [[0, 0], [1, 1]],
            "networkx_iteration_order_is_semantic": False,
        },
        "routing": {
            "carrier_type": "existing_data_qubit",
            "route_first_operand_to_second_operand_node": True,
            "carrier_order": "execution_qubit_index_ascending",
            "carrier_must_not_be_gate_operand": True,
            "carrier_must_be_unreserved": True,
            "additional_ancilla_allowed": False,
            "swap_decomposition": ["cx(a,b)", "cx(b,a)", "cx(a,b)"],
            "inverse_route_required": True,
            "final_mapping_required": "identity",
        },
        "topologies": {
            "level_a_4q": {
                "canonical_preimage": {
                    "schema": "distributed-topology-v1",
                    "topology_name": "linear-2-capacity-2",
                    "directed": False,
                    "nodes": [
                        {"id": 0, "qubit_capacity": 2},
                        {"id": 1, "qubit_capacity": 2},
                    ],
                    "edges": [
                        {
                            "source": 0,
                            "target": 1,
                            "weight_hex": "3ff0000000000000",
                        }
                    ],
                },
                "sha256": TOPOLOGY_4Q_SHA256,
            },
            "level_b_8q": {
                "canonical_preimage": {
                    "schema": "distributed-topology-v1",
                    "topology_name": "linear-2-capacity-4",
                    "directed": False,
                    "nodes": [
                        {"id": 0, "qubit_capacity": 4},
                        {"id": 1, "qubit_capacity": 4},
                    ],
                    "edges": [
                        {
                            "source": 0,
                            "target": 1,
                            "weight_hex": "3ff0000000000000",
                        }
                    ],
                },
                "sha256": TOPOLOGY_8Q_SHA256,
            },
        },
        "resource_guardrails": {
            "level_a_4q": _level(
                level="level_a_4q",
                qubit_count=4,
                node_capacity=2,
                topology_sha256=TOPOLOGY_4Q_SHA256,
                maximum_expanded_gate_count=600,
                maximum_artifact_size_bytes=8 * 1024 * 1024,
                maximum_artifact_total_bytes=32 * 1024 * 1024,
                maximum_qasm_size_bytes=1024 * 1024,
                compilation_wall_seconds=60,
                simulation_wall_seconds=120,
                rss_limit_bytes=1024 * 1024 * 1024,
                available_memory_bytes=2 * 1024 * 1024 * 1024,
                available_disk_bytes=2 * 1024 * 1024 * 1024,
            ),
            "level_b_8q": _level(
                level="level_b_8q",
                qubit_count=8,
                node_capacity=4,
                topology_sha256=TOPOLOGY_8Q_SHA256,
                maximum_expanded_gate_count=12000,
                maximum_artifact_size_bytes=32 * 1024 * 1024,
                maximum_artifact_total_bytes=128 * 1024 * 1024,
                maximum_qasm_size_bytes=2 * 1024 * 1024,
                compilation_wall_seconds=180,
                simulation_wall_seconds=300,
                rss_limit_bytes=1536 * 1024 * 1024,
                available_memory_bytes=3 * 1024 * 1024 * 1024,
                available_disk_bytes=4 * 1024 * 1024 * 1024,
            ),
        },
        "acceptance_thresholds": {
            "fci_vs_exact_pauli_hartree": 1e-8,
            "runtime_logical_vs_upstream_hartree": 1e-9,
            "variational_lower_bound_hartree": 1e-8,
            "logical_vs_exact_pauli_hartree": 0.0016,
            "distributed_vs_exact_pauli_hartree": 0.0016,
            "distributed_vs_logical_hartree": 1e-9,
            "statevector_infidelity": 1e-12,
            "statevector_normalization_error": 1e-12,
            "energy_imaginary_absolute_hartree": 1e-12,
            "particle_sector_expectation_error": 1e-10,
            "particle_sector_variance": 1e-10,
            "correlation_recovery_ratio_minimum": 0.90,
        },
        "hamiltonian_runtime_rule": {
            "identity_pauli_term_contains_energy_offset": True,
            "constant_offset_is_audit_only": True,
            "add_constant_offset_at_runtime": False,
            "exact_pauli_energy_regression_required": True,
        },
        "software_environment": {
            "python": "3.12.4",
            "python_distribution": "Anaconda",
            "qiskit": "0.46.3",
            "qiskit_terra": "0.46.3",
            "numpy": "2.4.6",
            "networkx": "3.6.1",
            "sqlalchemy": "2.0.50",
            "alembic": "1.18.5",
            "fastapi": "0.133.1",
            "pydantic": "2.13.4",
        },
        "scientific_limits": {
            "shots": 0,
            "ground_state_assessed": False,
            "scientific_adsorption_validation": False,
            "qpu_execution": False,
            "fe_n4_li2s4_adsorption_reproduction": False,
        },
    }


def create_protocol_artifact(artifact_root: Path) -> PublishedArtifact:
    """Create the protocol exactly once using the frozen no-clobber store."""
    store = NoClobberArtifactStore(artifact_root)
    return store.publish_json(
        PROTOCOL_FILENAME,
        build_protocol_payload(),
        max_size_bytes=8 * 1024 * 1024,
    )
