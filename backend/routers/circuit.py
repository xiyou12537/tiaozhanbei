"""
电路上传与解析接口
=================
- POST /api/circuit/upload  ——  上传 QASM 电路文本，解析后存入缓存
- GET  /api/circuit/info/{id} ——  获取已上传电路的基本信息
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models import CircuitInfo, QasmUploadRequest
from ..services.cache import cache
from quantum_partitioning.qasm_io import load_qasm_string
from quantum_partitioning.circuit_utils import remove_single_qubit_gates, extract_qubits

router = APIRouter(prefix="/api/circuit", tags=["circuit"])


@router.post("/upload", response_model=CircuitInfo)
def upload_circuit(body: QasmUploadRequest):
    """Parse QASM text and return circuit summary."""
    try:
        num_qubits, gates = load_qasm_string(body.qasm_content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"QASM parse error: {exc}")

    multi = remove_single_qubit_gates(gates)
    qubits = extract_qubits(gates)

    circuit_id = f"circuit_{hash(body.qasm_content) & 0xFFFFFFFF:08x}"

    info = CircuitInfo(
        circuit_id=circuit_id,
        num_qubits=num_qubits,
        total_gates=len(gates),
        single_qubit_gates=len(gates) - len(multi),
        multi_qubit_gates=len(multi),
        qubit_list=qubits,
    )

    # Cache the parsed circuit data for later use
    cache.set(circuit_id, {
        "qasm": body.qasm_content,
        "num_qubits": num_qubits,
        "gates": gates,
        "multi_gates": multi,
        "qubits": qubits,
    }, ttl=3600)

    return info


@router.get("/info/{circuit_id}", response_model=CircuitInfo)
def get_circuit_info(circuit_id: str):
    """Retrieve cached circuit info."""
    data = cache.get(circuit_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Circuit not found. Upload first.")
    return CircuitInfo(
        circuit_id=circuit_id,
        num_qubits=data["num_qubits"],
        total_gates=len(data["gates"]),
        single_qubit_gates=len(data["gates"]) - len(data["multi_gates"]),
        multi_qubit_gates=len(data["multi_gates"]),
        qubit_list=data["qubits"],
    )
