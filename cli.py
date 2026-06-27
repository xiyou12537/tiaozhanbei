#!/usr/bin/env python3
"""
Command-line interface for the quantum circuit partitioning optimiser.

Usage::

    python cli.py --qasm path/to/circuit.qasm --partitions 4
    python cli.py --qasm circuit.qasm --search --interactive

For a web-based interface, import ``quantum_partitioning`` as a library.
"""

from __future__ import annotations

import argparse
import ast
import sys
import time
from typing import Dict, List, Optional, Tuple

from quantum_partitioning.qasm_io import load_qasm_file
from quantum_partitioning.circuit_utils import (
    extract_qubits,
    remove_single_qubit_gates,
)
from quantum_partitioning.partitioning import (
    PartitionScheme,
    run_partitioning_pipeline,
)
from quantum_partitioning.chip_mapping import (
    build_partition_interaction_graph,
    compute_total_epr_cost,
    find_chip_mapping,
    parse_target_topology_from_string,
)
from quantum_partitioning.visualization import (
    build_partition_graph_data,
    build_mapping_data,
    render_partition_graph,
    render_mapping_visualization,
)
from quantum_partitioning.config import (
    DEFAULT_NUM_PARTITIONS,
    DEFAULT_B1_RANGE,
    DEFAULT_B2_RANGE,
)


# ── CLI argument parsing ──────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Quantum Circuit Partitioning Optimiser",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py --qasm circuit.qasm
  python cli.py --qasm circuit.qasm --partitions 4 --search
  python cli.py --qasm circuit.qasm --interactive
        """,
    )

    parser.add_argument(
        "--qasm", "-q",
        required=True,
        help="Path to the OpenQASM 2.0 file.",
    )
    parser.add_argument(
        "--partitions", "-k",
        type=int,
        default=DEFAULT_NUM_PARTITIONS,
        help=f"Number of compute nodes (default: {DEFAULT_NUM_PARTITIONS}).",
    )
    parser.add_argument(
        "--search", "-s",
        action="store_true",
        help="Enable hyper-parameter grid search over (b1, b2).",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=3.0,
        help="Mergeability weight (default: 3.0).",
    )
    parser.add_argument(
        "--beta",
        type=float,
        default=1.0,
        help="Return-penalty weight (default: 1.0).",
    )
    parser.add_argument(
        "--b1",
        type=float,
        default=10.0,
        help="Interaction-score base b1 (default: 10).",
    )
    parser.add_argument(
        "--b2",
        type=float,
        default=2.0,
        help="Span-penalty base b2 (default: 2).",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Enter interactive mode for chip-topology mapping.",
    )
    parser.add_argument(
        "--save-plot",
        metavar="PREFIX",
        help="Save plots as PREFIX_graph.png etc. instead of displaying.",
    )
    return parser


# ── Main pipeline ─────────────────────────────────────────────────────

def run_pipeline(
    qasm_path: str,
    num_partitions: int = DEFAULT_NUM_PARTITIONS,
    search: bool = False,
    alpha: float = 3.0,
    beta: float = 1.0,
    b1: float = 10.0,
    b2: float = 2.0,
    interactive: bool = False,
    save_plot: Optional[str] = None,
) -> int:
    """Run the full partitioning pipeline and return exit code.

    Args:
        qasm_path: Path to QASM file.
        num_partitions: Number of compute nodes.
        search: Enable grid search.
        alpha: Mergeability weight.
        beta: Return-penalty weight.
        b1: Interaction base.
        b2: Span-penalty base.
        interactive: Enter chip-mapping interactive mode.
        save_plot: If set, save plots with this prefix.

    Returns:
        0 on success, 1 on error.
    """
    # ── Step 1: Load circuit ──────────────────────────────────────
    print(f"Loading circuit from: {qasm_path}")
    try:
        num_qubits, original_gates = load_qasm_file(qasm_path)
    except FileNotFoundError:
        print(f"ERROR: File not found: {qasm_path}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: Failed to load QASM: {exc}", file=sys.stderr)
        return 1

    print(f"  Qubits: {num_qubits}, Gates: {len(original_gates)}")

    # ── Step 2: Pre-process ───────────────────────────────────────
    qubits = extract_qubits(original_gates)
    print(f"  Active qubits: {len(qubits)}")

    multi_gates = remove_single_qubit_gates(original_gates)
    print(f"  Multi-qubit gates: {len(multi_gates)}")

    # ── Step 3: Partition ─────────────────────────────────────────
    print(f"\nPartitioning into {num_partitions} nodes...")
    start = time.time()

    scheme, used_b1, used_b2 = run_partitioning_pipeline(
        gates=multi_gates,
        qubits=qubits,
        num_partitions=num_partitions,
        search=search,
        b1=b1,
        b2=b2,
        alpha=alpha,
        beta=beta,
    )

    elapsed = time.time() - start
    print(f"  Time: {elapsed:.2f}s")

    if scheme is None:
        print("ERROR: Partitioning failed to find a valid solution.",
              file=sys.stderr)
        return 1

    print(f"\n=== Partitioning Results ===")
    print(f"  Teleportations: {scheme.teleportations}")
    print(f"  Global gates:   {scheme.global_gates}")
    print(f"  Parameters:     b1={used_b1}, b2={used_b2}")
    for i, part in enumerate(scheme.partitions):
        print(f"  P{i + 1}: {len(part)} qubits: {part[:10]}"
              f"{'...' if len(part) > 10 else ''}")

    # ── Step 4: Build interaction graph ───────────────────────────
    complete_graph, edge_costs = build_partition_interaction_graph(
        scheme.partitions, scheme.optimized_gates
    )

    graph_data = build_partition_graph_data(
        scheme.partitions, scheme.optimized_gates
    )
    print(f"\n=== Partition Interaction Graph ===")
    for (i, j), w in edge_costs.items():
        print(f"  {i} -- {j}: {w} global gates")

    # Save/display plot
    if save_plot:
        png = render_partition_graph(
            scheme.partitions, scheme.optimized_gates
        )
        path = f"{save_plot}_graph.png"
        with open(path, "wb") as f:
            f.write(png)
        print(f"  Graph saved to: {path}")

    # ── Step 5: Chip mapping (interactive) ────────────────────────
    if interactive:
        print("\n=== Interactive Chip-Topology Mapping ===")
        print("Enter target topology as an edge list, e.g.:")
        print("  [(0,1),(1,2),(2,3),(3,0)]  for a 4-node ring")
        print("  [(0,1),(0,2),(0,3)]        for a 4-node star")
        print("  (Type 'q' to quit)")

        while True:
            try:
                user_input = input("\nTopology edges: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if user_input.lower() == "q":
                break

            target_graph = parse_target_topology_from_string(user_input)
            if target_graph is None:
                print("  Invalid format. Try again.")
                continue

            mapping, min_cost = find_chip_mapping(
                complete_graph, target_graph
            )

            if mapping is None:
                print("  No valid mapping found for this topology.")
                continue

            print(f"\n  Best mapping: {mapping}")
            print(f"  Total cost:   {min_cost}")

            # Build qubit → partition mapping for EPR cost
            qubit_to_partition: Dict[int, str] = {}
            for idx, part in enumerate(scheme.partitions):
                pid = f"P{idx + 1}"
                for q in part:
                    qubit_to_partition[q] = pid

            partition_to_chip = mapping  # {chip: partition} → swap direction

            total_epr = compute_total_epr_cost(
                gates=scheme.optimized_gates,
                partitions=scheme.partitions,
                qubit_to_partition=qubit_to_partition,
                partition_to_chip=partition_to_chip,
                chip_graph=target_graph,
                alpha=alpha,
                beta=beta,
            )
            print(f"  Total EPR cost: {total_epr}")

            if save_plot:
                png = render_mapping_visualization(
                    complete_graph, target_graph, mapping, min_cost
                )
                path = f"{save_plot}_mapping.png"
                with open(path, "wb") as f:
                    f.write(png)
                print(f"  Mapping plot saved to: {path}")

    print("\nDone.")
    return 0


# ── Entry point ───────────────────────────────────────────────────────

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    exit_code = run_pipeline(
        qasm_path=args.qasm,
        num_partitions=args.partitions,
        search=args.search,
        alpha=args.alpha,
        beta=args.beta,
        b1=args.b1,
        b2=args.b2,
        interactive=args.interactive,
        save_plot=args.save_plot,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
