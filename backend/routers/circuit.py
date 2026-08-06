from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models import CircuitInfo, QasmUploadRequest
from ..services.cache import cache
from ..services.runtime_status import load_circuit_runtime

router = APIRouter(prefix="/api/circuit", tags=["电路"])


def _get_circuit_runtime():
    try:
        return load_circuit_runtime()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/upload", response_model=CircuitInfo)
def upload_circuit(body: QasmUploadRequest):
    """Parse uploaded QASM text and return the circuit summary."""
    load_qasm_string, remove_single_qubit_gates, extract_qubits = _get_circuit_runtime()

    try:
        num_qubits, gates = load_qasm_string(body.qasm_content)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"QASM 解析失败: {exc}") from exc

    multi_qubit_gates = remove_single_qubit_gates(gates)
    qubit_list = extract_qubits(gates)
    circuit_id = f"circuit_{hash(body.qasm_content) & 0xFFFFFFFF:08x}"

    cache.set(
        circuit_id,
        {
            "qasm": body.qasm_content,
            "num_qubits": num_qubits,
            "gates": gates,
            "multi_gates": multi_qubit_gates,
            "qubits": qubit_list,
        },
        ttl=3600,
    )

    return CircuitInfo(
        circuit_id=circuit_id,
        num_qubits=num_qubits,
        total_gates=len(gates),
        single_qubit_gates=len(gates) - len(multi_qubit_gates),
        multi_qubit_gates=len(multi_qubit_gates),
        qubit_list=qubit_list,
    )


@router.get("/info/{circuit_id}", response_model=CircuitInfo)
def get_circuit_info(circuit_id: str):
    """Return the summary of a previously uploaded circuit."""
    data = cache.get(circuit_id)
    if data is None:
        raise HTTPException(status_code=404, detail="电路未找到，请先上传。")

    return CircuitInfo(
        circuit_id=circuit_id,
        num_qubits=data["num_qubits"],
        total_gates=len(data["gates"]),
        single_qubit_gates=len(data["gates"]) - len(data["multi_gates"]),
        multi_qubit_gates=len(data["multi_gates"]),
        qubit_list=data["qubits"],
    )
