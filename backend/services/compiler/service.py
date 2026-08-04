TOPOLOGY_PRESETS = {
    "ring-3": {
        "name": "ring-3",
        "label": "Ring (3 chips)",
        "description": "3-node cycle",
        "edges": [
            {"source": 0, "target": 1},
            {"source": 1, "target": 2},
            {"source": 2, "target": 0},
        ],
    },
    "linear-3": {
        "name": "linear-3",
        "label": "Linear (3 chips)",
        "description": "3-node path",
        "edges": [
            {"source": 0, "target": 1},
            {"source": 1, "target": 2},
        ],
    },
}


class DistributedCompilerService:
    def compile(self, quantum_problem: dict) -> dict:
        qubit_count = quantum_problem["qubit_count"]
        partition_count = 2 if qubit_count <= 6 else 3
        partitions = {
            f"P{index + 1}": list(range(index, qubit_count, partition_count))
            for index in range(partition_count)
        }
        topology_name = "ring-3" if partition_count == 2 else "linear-3"
        mapping = {
            chip: part
            for chip, part in zip(["C0", "C1", "C2"], list(partitions.keys()) + ["P1"])
        }

        return {
            "partition_count": partition_count,
            "partitions": partitions,
            "mapping": mapping,
            "teleportations": max(1, qubit_count - partition_count),
            "topology": TOPOLOGY_PRESETS[topology_name],
        }
