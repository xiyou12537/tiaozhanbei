"""
QASM file I/O and conversion utilities.

Converts between:
- Qiskit QuantumCircuit objects
- Flat gate lists (the internal representation used by all algorithms)
- OpenQASM 2.0 text
"""

from __future__ import annotations

import tempfile
import os
from typing import List, Tuple
from qiskit import QuantumCircuit

from .config import Gate


def circuit_to_gate_list(circuit: QuantumCircuit) -> Tuple[int, List[Gate]]:
    """Convert a Qiskit QuantumCircuit into a flat gate list.

    Each gate is ``[name, qubit_index, ...]``.

    Args:
        circuit: A fully constructed Qiskit ``QuantumCircuit``.

    Returns:
        ``(num_qubits, gates)`` where *num_qubits* is the total number of
        qubits in the circuit and *gates* is the gate list.
    """
    gates: List[Gate] = []
    qubit_indices: set[int] = set()

    # Build a fast lookup: qubit object -> index
    qidx_map = {q: i for i, q in enumerate(circuit.qubits)}

    for instruction, qargs, _ in circuit.data:
        gate_name = instruction.name
        num_q = instruction.num_qubits

        if num_q == 2:
            ctrl = qidx_map[qargs[0]]
            targ = qidx_map[qargs[1]]
            gates.append([gate_name, ctrl, targ])
            qubit_indices.update((ctrl, targ))

        elif num_q == 1:
            q = qidx_map[qargs[0]]
            gates.append([gate_name, q])
            qubit_indices.add(q)

        # 3-qubit gates (e.g. ccx) and measurements are skipped for now
        # but could be decomposed in a future version.

    num_qubits = max(qubit_indices) + 1 if qubit_indices else 0
    return num_qubits, gates


def load_qasm_file(filepath: str) -> Tuple[int, List[Gate]]:
    """Load a ``.qasm`` file and convert it to a gate list.

    Args:
        filepath: Path to an OpenQASM 2.0 file.

    Returns:
        ``(num_qubits, gates)``.
    """
    circuit = QuantumCircuit.from_qasm_file(filepath)
    return circuit_to_gate_list(circuit)


def load_qasm_string(qasm_str: str) -> Tuple[int, List[Gate]]:
    """Parse an OpenQASM 2.0 string and convert it to a gate list.

    Uses Qiskit's permissive file parser (via a temp file) to handle
    Qiskit-specific gate extensions like ``cp``, ``cu3``, etc.

    Args:
        qasm_str: Raw QASM source text.

    Returns:
        ``(num_qubits, gates)``.
    """
    # Write to temp file so Qiskit's from_qasm_file (permissive parser)
    # can handle extensions that the strict qasm2 parser rejects.
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".qasm", delete=False, encoding="utf-8"
    )
    try:
        tmp.write(qasm_str)
        tmp.close()
        circuit = QuantumCircuit.from_qasm_file(tmp.name)
    finally:
        os.unlink(tmp.name)

    return circuit_to_gate_list(circuit)


def gates_to_qasm(num_qubits: int, gates: List[Gate]) -> str:
    """Convert a gate list back into an OpenQASM 2.0 string.

    Args:
        num_qubits: Number of qubits in the circuit.
        gates: Gate list.

    Returns:
        Valid OpenQASM 2.0 source text.
    """
    lines = [
        "OPENQASM 2.0;",
        'include "qelib1.inc";',
        f"qreg q[{num_qubits}];",
    ]

    for gate in gates:
        name = gate[0]
        qubits = gate[1:]
        if name == "rswap":
            # rswap is a custom gate — emit as a comment + dummy barrier
            lines.append(f"// rswap q[{qubits[0]}], q[{qubits[1]}];")
            lines.append(f"barrier q[{qubits[0]}], q[{qubits[1]}];")
        else:
            qargs = ", ".join(f"q[{q}]" for q in qubits)
            lines.append(f"{name} {qargs};")

    return "\n".join(lines) + "\n"
