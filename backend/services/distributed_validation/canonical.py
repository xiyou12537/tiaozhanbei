from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import numpy as np
from qiskit import qasm2

ARTIFACT_CANONICAL_SCHEME = "artifact-canonical-json-v1"
QASM_CANONICAL_SCHEME = "qasm2-canonical-circuit-v1"
PARAMETER_HASH_SCHEME = "parameter-ieee754-f64-le-c-v1"
ORDERED_PAULI_SCHEME = "ordered-pauli-payload-v1"


class CanonicalizationError(ValueError):
    """Raised when an input cannot be represented by a frozen hash scheme."""


@dataclass(frozen=True)
class ParsedCircuit:
    """A strict, fully bound QASM2 circuit and its canonical representation."""

    qasm_text: str
    circuit: Any
    operations: tuple[dict[str, Any], ...]
    canonical_object: dict[str, Any]
    canonical_bytes: bytes
    canonical_sha256: str
    raw_qasm_sha256: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f64be_hex(value: float) -> str:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise CanonicalizationError("Non-finite binary64 value is forbidden.")
    return struct.pack(">d", numeric).hex()


def utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise CanonicalizationError("Naive datetimes are forbidden.")
    normalized = value.astimezone(timezone.utc)
    return normalized.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def validate_unicode_scalars(value: str) -> None:
    for character in value:
        codepoint = ord(character)
        if 0xD800 <= codepoint <= 0xDFFF:
            raise CanonicalizationError("Lone UTF-16 surrogate is forbidden.")


def canonical_artifact_path(value: str) -> str:
    validate_unicode_scalars(value)
    if "\\" in value or value.startswith("/") or value.startswith("//"):
        raise CanonicalizationError("Artifact path must be root-relative POSIX syntax.")
    if len(value) >= 2 and value[1] == ":":
        raise CanonicalizationError("Drive-qualified artifact path is forbidden.")
    path = PurePosixPath(value)
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise CanonicalizationError("Artifact path contains an invalid segment.")
    if str(path) != value:
        raise CanonicalizationError("Artifact path is not canonical.")
    return value


def _canonicalize_artifact_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        validate_unicode_scalars(value)
        return value
    if isinstance(value, datetime):
        return utc_timestamp(value)
    if isinstance(value, int) and not isinstance(value, bool):
        if not -(2**63) <= value <= 2**63 - 1:
            raise CanonicalizationError("Integer is outside signed 64-bit range.")
        return value
    if isinstance(value, (float, np.floating)):
        return {"$f64be": f64be_hex(float(value))}
    if isinstance(value, (list, tuple)):
        return [_canonicalize_artifact_value(item) for item in value]
    if isinstance(value, dict):
        canonical: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise CanonicalizationError("Artifact object keys must be ASCII strings.")
            validate_unicode_scalars(key)
            if key in canonical:
                raise CanonicalizationError(f"Duplicate artifact key: {key}")
            canonical[key] = _canonicalize_artifact_value(item)
        return canonical
    raise CanonicalizationError(f"Unsupported artifact value type: {type(value)!r}")


def canonical_artifact_bytes(payload: dict[str, Any]) -> bytes:
    canonical = _canonicalize_artifact_value(payload)
    return json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def canonical_artifact_sha256(payload: dict[str, Any]) -> str:
    return sha256_bytes(canonical_artifact_bytes(payload))


def decode_canonical_artifact_value(value: Any) -> Any:
    """Decode binary64 wrappers from an artifact-canonical-json-v1 document."""
    if isinstance(value, list):
        return [decode_canonical_artifact_value(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {"$f64be"}:
            encoded = value["$f64be"]
            if not isinstance(encoded, str) or len(encoded) != 16:
                raise CanonicalizationError("Malformed canonical binary64 wrapper.")
            try:
                numeric = struct.unpack(">d", bytes.fromhex(encoded))[0]
            except (ValueError, struct.error) as exc:
                raise CanonicalizationError(
                    "Malformed canonical binary64 encoding."
                ) from exc
            if not math.isfinite(numeric):
                raise CanonicalizationError("Non-finite canonical binary64 value.")
            return numeric
        return {
            key: decode_canonical_artifact_value(item)
            for key, item in value.items()
        }
    return value


def _condition_payload(operation: Any) -> dict[str, Any] | None:
    condition = operation.condition
    if condition is None:
        return None
    register_or_bit, value = condition
    name = getattr(register_or_bit, "name", None)
    if name is None:
        raise CanonicalizationError("Condition cannot be represented losslessly.")
    return {"register": str(name), "value": int(value)}


def parse_bound_qasm2_strict(qasm_text: str) -> ParsedCircuit:
    """Parse a fully bound u3/cx QASM2 circuit without executing it."""
    if not isinstance(qasm_text, str):
        raise CanonicalizationError("QASM must be text.")
    validate_unicode_scalars(qasm_text)
    raw_bytes = qasm_text.encode("utf-8", errors="strict")
    try:
        circuit = qasm2.loads(qasm_text)
    except Exception as exc:
        raise CanonicalizationError(f"QASM2 parsing failed: {exc}") from exc

    if circuit.num_clbits:
        raise CanonicalizationError("V1 does not accept classical bits or measurements.")

    qubit_indices: dict[Any, int] = {}
    qregs: list[dict[str, Any]] = []
    offset = 0
    for register in circuit.qregs:
        qregs.append({"name": register.name, "size": register.size})
        for local_index, bit in enumerate(register):
            qubit_indices[bit] = offset + local_index
        offset += register.size

    clbit_indices: dict[Any, int] = {}
    cregs: list[dict[str, Any]] = []
    offset = 0
    for register in circuit.cregs:
        cregs.append({"name": register.name, "size": register.size})
        for local_index, bit in enumerate(register):
            clbit_indices[bit] = offset + local_index
        offset += register.size

    operations: list[dict[str, Any]] = []
    allowed = {"u3", "cx"}
    for index, instruction in enumerate(circuit.data):
        operation = instruction.operation
        if operation.name not in allowed:
            raise CanonicalizationError(
                f"Unsupported V1 instruction at index {index}: {operation.name}"
            )
        if getattr(operation, "condition", None) is not None:
            raise CanonicalizationError("Conditional instructions are forbidden in V1.")
        params: list[str] = []
        numeric_params: list[float] = []
        for parameter in operation.params:
            try:
                numeric = float(parameter)
            except (TypeError, ValueError) as exc:
                raise CanonicalizationError("Unbound QASM parameter is forbidden.") from exc
            if not math.isfinite(numeric):
                raise CanonicalizationError("Non-finite QASM parameter is forbidden.")
            numeric_params.append(numeric)
            params.append(f64be_hex(numeric))
        operations.append(
            {
                "index": index,
                "name": operation.name,
                "qubits": [qubit_indices[bit] for bit in instruction.qubits],
                "clbits": [clbit_indices[bit] for bit in instruction.clbits],
                "params": params,
                "numeric_params": numeric_params,
                "condition": _condition_payload(operation),
            }
        )

    global_phase = float(circuit.global_phase)
    canonical_operations = [
        {key: value for key, value in operation.items() if key != "numeric_params"}
        for operation in operations
    ]
    canonical_object = {
        "schema": QASM_CANONICAL_SCHEME,
        "openqasm_version": "2.0",
        "qregs": qregs,
        "cregs": cregs,
        "global_phase": {
            "encoding": "ieee754-binary64",
            "big_endian_hex": f64be_hex(global_phase),
        },
        "operations": canonical_operations,
    }
    canonical_bytes = json.dumps(
        canonical_object,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return ParsedCircuit(
        qasm_text=qasm_text,
        circuit=circuit,
        operations=tuple(operations),
        canonical_object=canonical_object,
        canonical_bytes=canonical_bytes,
        canonical_sha256=sha256_bytes(canonical_bytes),
        raw_qasm_sha256=sha256_bytes(raw_bytes),
    )


def parameter_vector_sha256(parameters: list[float]) -> str:
    values = np.asarray(parameters, dtype="<f8", order="C")
    if values.ndim != 1 or not np.isfinite(values).all():
        raise CanonicalizationError("Parameter vector must be one-dimensional and finite.")
    return sha256_bytes(values.tobytes(order="C"))


def _full_pauli_label(sparse_label: str, qubit_count: int) -> str:
    label = ["I"] * qubit_count
    if sparse_label == "I":
        return "".join(label)
    occupied: set[int] = set()
    for token in sparse_label.split():
        if len(token) < 2 or token[0] not in "IXYZ":
            raise CanonicalizationError(f"Invalid sparse Pauli token: {token}")
        try:
            qubit = int(token[1:])
        except ValueError as exc:
            raise CanonicalizationError(f"Invalid sparse Pauli index: {token}") from exc
        if qubit < 0 or qubit >= qubit_count or qubit in occupied:
            raise CanonicalizationError(f"Invalid or duplicate Pauli qubit: {token}")
        occupied.add(qubit)
        label[qubit_count - 1 - qubit] = token[0]
    return "".join(label)


def ordered_pauli_payload(
    mapping: dict[str, Any],
    constant_offset: float | complex,
) -> dict[str, Any]:
    qubit_count = int(mapping["qubit_count"])
    terms: list[dict[str, Any]] = []
    for index, term in enumerate(mapping["pauli_terms"]):
        coefficient = complex(term["coefficient"])
        terms.append(
            {
                "index": index,
                "label": _full_pauli_label(
                    str(term["pauli_string"]),
                    qubit_count,
                ),
                "real_hex": f64be_hex(coefficient.real),
                "imag_hex": f64be_hex(coefficient.imag),
            }
        )
    offset = complex(constant_offset)
    return {
        "schema": ORDERED_PAULI_SCHEME,
        "mapping_method": "jordan_wigner",
        "qubit_count": qubit_count,
        "spin_orbital_ordering": "2p=alpha,2p+1=beta",
        "label_direction": "leftmost=q[n-1],rightmost=q[0]",
        "coefficient_encoding": "ieee754-binary64-big-endian-hex",
        "constant_offset": {
            "real_hex": f64be_hex(offset.real),
            "imag_hex": f64be_hex(offset.imag),
        },
        "terms": terms,
    }


def ordered_pauli_payload_bytes(
    mapping: dict[str, Any],
    constant_offset: float | complex,
) -> bytes:
    return json.dumps(
        ordered_pauli_payload(mapping, constant_offset),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
