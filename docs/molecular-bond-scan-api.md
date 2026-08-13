# LiH bond-scan API (P1 backend contract)

## Scope

These authenticated endpoints calculate a discrete LiH potential-energy scan.
Li is fixed at `[0, 0, 0]` Å and H at `[0, 0, distance_angstrom]` Å. Every
point runs the existing PySCF/Hamiltonian/Jordan-Wigner/VQE Workflow once and
is persisted independently. This is `logical_virtual_qpu` simulation with
`is_real_qpu: false`; it is not a real-QPU execution service.

- `GET /api/molecular-bond-scans/capabilities`
- `POST /api/molecular-bond-scans` (202, `Idempotency-Key` supported)
- `GET /api/molecular-bond-scans/{scan_id}`

All requests require `Authorization: Bearer <token>`. A scan owned by another
user is intentionally indistinguishable from a missing scan and returns 404.

## Request

`deployment_architectures` contains 3–12 items and reuses the frozen
`DeploymentArchitecture` schema from Molecular Study. The server calculates
the inclusive distance grid as `start + i * (end - start) / (point_count - 1)`;
it does not accumulate floating-point increments.

```json
{
  "molecule_type": "LiH",
  "scan": {
    "start_distance_angstrom": 1.0,
    "end_distance_angstrom": 2.4,
    "point_count": 8
  },
  "chemistry": {
    "charge": 0,
    "spin_multiplicity": 1,
    "basis_set": "sto-3g",
    "active_space_orbitals": 2,
    "pauli_coefficient_cutoff": 0.000001,
    "vqe": {
      "ansatz_layers": 1,
      "max_iterations": 80,
      "convergence_tolerance": 0.0001,
      "shots": 1024
    }
  },
  "deployment_architectures": [
    {"architecture_id": "linear-a", "partition": {"partition_count": 2, "partition_strategy": "sequential_greedy", "inter_qpu_topology": [{"source": 0, "target": 1}], "initial_layout": "identity", "routing_method": "shortest_path_swap", "virtual_qpus": [{"virtual_qpu_id": "T1", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]}, {"virtual_qpu_id": "T2", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]}]}},
    {"architecture_id": "forced-swap", "partition": {"partition_count": 2, "partition_strategy": "sequential_greedy", "inter_qpu_topology": [{"source": 0, "target": 1}], "initial_layout": "identity", "routing_method": "shortest_path_swap", "virtual_qpus": [{"virtual_qpu_id": "T1", "physical_qubit_count": 3, "physical_coupling_map": [{"source": 0, "target": 2}, {"source": 2, "target": 1}]}, {"virtual_qpu_id": "T2", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]}]}},
    {"architecture_id": "linear-b", "partition": {"partition_count": 2, "partition_strategy": "sequential_greedy", "inter_qpu_topology": [{"source": 0, "target": 1}], "initial_layout": "identity", "routing_method": "shortest_path_swap", "virtual_qpus": [{"virtual_qpu_id": "T1", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]}, {"virtual_qpu_id": "T2", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]}]}}
  ]
}
```

## Lifecycle and quality semantics

Poll while `status` is `queued` or `running`; stop while it is `completed` or
`failed`. The GET response always has the same `MolecularBondScanResult` shape
while running, with completed points and null values for results not yet known.
Each point is independently durable.

- A completed point with an unconverged VQE has `status: completed` and
  `validation_status: needs_review`; its diagnostics, energy, QASM and FCI
  fields are retained.
- A failed point has `status: failed` and a typed `error`; other points remain
  available. A scan can be `completed` with failed points when at least one
  point completed.
- A scan is `failed` only for a common configuration/scheduling failure or
  when every point failed.

`hf_discrete_minimum`, `vqe_discrete_minimum` and `fci_discrete_minimum` are
discrete scan minima / approximate bond-length candidates, not optimized
equilibrium bond lengths. `minimum_at_boundary: true` warns that the chosen
range may not bracket the true minimum. The VQE minimum considers only
`validation_status: passed` points.

Each point tries the bounded, same-geometry active-space FCI reference through
`DockerPySCFAdapter.calculate_classical_reference`. If FCI is unavailable or
unsupported, `fci_reference.energy_hartree` and
`vqe_fci_scientific_error_hartree` are null; no HF, VQE, or fixture value is
substituted.

Only the selected `vqe_discrete_minimum` point is sent to the three-or-more
deployment evaluations. Its persisted Workflow QASM/Hamiltonian are reused;
the selected point's PySCF, Hamiltonian construction and VQE are not rerun.
Every deployable architecture independently executes partitioning, mapping,
routing and logical distributed simulation. The result uses the existing typed
`DeploymentEvaluationResult`, including real routed-plan-consumption evidence,
distributed VQE–VQE execution error, SWAP and cross-QPU communication counts.

## Error contract

## P1.1 scientific minimum semantics

In addition to the legacy optimizer-valid `vqe_discrete_minimum`, P1.1 returns
`scientific_vqe_discrete_minimum`, calculated only from points whose
`scientific_validation.status` is `passed`. When no point is scientifically
accepted this field is null and no trustworthy approximate bond length is
claimed. `engineering_only_deployment: true` marks the exceptional case where
an optimizer-valid point was routed solely to assess deployment cost. Every
point separately contains `optimizer_validation`, `scientific_validation`, and
`deployment_validation`; chemical accuracy is the published `1.6e-3 Hartree`
threshold plus the actual VQE--FCI error.

`engineering_only_deployment` is nullable: it is `null` while a Scan is
queued/running and for historical terminal records that predate this evidence
(which also include `legacy_result_missing_release_fields` in summary issues).
New terminal Scans persist `false` for a scientific-minimum deployment or
`true` for an optimizer-only engineering deployment. If no deployment target
was selected and no deployment evaluation ran (including an all-points-failed
Scan), the value remains `null`; the API never infers `false` from missing
deployment evidence or a missing historical field.

Business errors use:

```json
{"detail":{"code":"string","message":"string","stage":"string|null","scan_id":"string|null","point_index":0,"molecular_problem_id":"string|null"}}
```

- 401: absent/expired Bearer token.
- 404: unknown scan or another user's scan.
- 409: an `Idempotency-Key` is associated with a different request.
- 422: standard FastAPI validation (`detail` array), or typed business input
  validation (`detail` object).
- 503: a request cannot be accepted or the runtime service is unavailable.
  Errors after asynchronous acceptance are reported from `GET` as failed scan
  or point state, rather than as a new POST error response.

The complete typed response fixture is
[`molecular-bond-scan-lih-success.json`](fixtures/molecular-bond-scan-lih-success.json).
