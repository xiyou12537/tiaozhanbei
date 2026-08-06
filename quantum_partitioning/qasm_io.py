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
import re
from typing import TYPE_CHECKING, List, Tuple

try:
    from qiskit import QuantumCircuit
except ImportError:  # Keep the platform's OpenQASM 2.0 path available without an optional parser runtime.
    QuantumCircuit = None

if TYPE_CHECKING:
    from qiskit import QuantumCircuit as QuantumCircuitType

from .config import Gate


def circuit_to_gate_list(circuit: "QuantumCircuitType") -> Tuple[int, List[Gate]]:
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
    if QuantumCircuit is None:
        with open(filepath, encoding="utf-8") as qasm_file:
            return _parse_openqasm_2(qasm_file.read())
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
    if QuantumCircuit is None:
        return _parse_openqasm_2(qasm_str)

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


def _parse_openqasm_2(qasm_str: str) -> Tuple[int, List[Gate]]:
    """Parse the standard OpenQASM 2.0 subset emitted by platform circuit compilers.

    The fallback intentionally accepts parameterized single-qubit gates and the
    common two-qubit gates required by the partitioner.  More exotic dialects
    continue to use Qiskit when it is installed.
    """
    qubit_count = 0
    gates: List[Gate] = []
    for raw_line in qasm_str.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("OPENQASM") or line.startswith("include"):
            continue
        qreg_match = re.fullmatch(r"qreg\s+\w+\[(\d+)\];", line)
        if qreg_match:
            qubit_count = int(qreg_match.group(1))
            continue
        gate_match = re.fullmatch(r"([A-Za-z_][\w]*)(?:\([^;]*\))?\s+(.+);", line)
        if gate_match is None:
            raise ValueError(f"Unsupported OpenQASM 2.0 statement: {line}")
        gate_name, arguments = gate_match.groups()
        qubits = [int(index) for index in re.findall(r"\w+\[(\d+)\]", arguments)]
        if gate_name == "barrier":
            continue
        if len(qubits) not in {1, 2}:
            raise ValueError(f"Unsupported OpenQASM gate arity: {gate_name}")
        gates.append([gate_name, *qubits])
    if qubit_count == 0:
        raise ValueError("OpenQASM 2.0 source does not declare a quantum register.")
    return qubit_count, gates


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
