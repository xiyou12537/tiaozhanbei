import unittest

from quantum_partitioning.partitioning import GreedyPartitioner


class GreedyPartitionBalanceTests(unittest.TestCase):
    def test_even_qubits_are_split_evenly_across_requested_partitions(self):
        gates = [
            ["cx", 0, 1],
            ["cx", 1, 2],
            ["cx", 2, 3],
        ]

        result = GreedyPartitioner(
            gates=gates,
            qubits=[0, 1, 2, 3],
            num_partitions=2,
            max_imbalance=1,
            num_starts=1,
        ).run()

        self.assertIsNotNone(result)
        self.assertEqual(sorted(len(partition) for partition in result.partitions), [2, 2])
        self.assertEqual(
            sorted(qubit for partition in result.partitions for qubit in partition),
            [0, 1, 2, 3],
        )

    def test_remainder_qubit_is_greedily_assigned_to_its_best_partition(self):
        gates = (
            [["cx", 0, 1] for _ in range(10)]
            + [["cx", 2, 3] for _ in range(4)]
            + [["cx", 3, 4] for _ in range(2)]
        )

        result = GreedyPartitioner(
            gates=gates,
            qubits=[0, 1, 2, 3, 4],
            num_partitions=2,
            max_imbalance=1,
            num_starts=1,
        ).run()

        self.assertIsNotNone(result)
        self.assertEqual(sorted(len(partition) for partition in result.partitions), [2, 3])
        remainder_partition = next(partition for partition in result.partitions if 4 in partition)
        self.assertEqual(set(remainder_partition), {2, 3, 4})


if __name__ == "__main__":
    unittest.main()
