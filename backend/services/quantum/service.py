class QuantumProblemService:
    def encode_problem(self, chemistry_model: dict) -> dict:
        qubit_count = chemistry_model["orbital_count"]
        qasm_lines = [
            "OPENQASM 2.0;",
            'include "qelib1.inc";',
            f"qreg q[{qubit_count}];",
        ]
        for idx in range(max(1, qubit_count - 1)):
            qasm_lines.append(f"h q[{idx}];")
            qasm_lines.append(f"cx q[{idx}],q[{(idx + 1) % qubit_count}];")

        return {
            "candidate_name": chemistry_model["candidate_name"],
            "qubit_count": qubit_count,
            "pauli_term_count": qubit_count + 2,
            "qasm_content": "\n".join(qasm_lines) + "\n",
        }
