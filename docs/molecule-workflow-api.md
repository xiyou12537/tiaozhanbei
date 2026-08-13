# 通用小分子量子计算 Workflow API（P0 前端联调契约）

## 契约入口

- Swagger UI：`GET /docs`
- OpenAPI JSON：`GET /openapi.json`
- 创建并同步执行：`POST /api/molecule-workflows`
- 查询当前用户的 Workflow 历史：`GET /api/molecule-workflows`
- 查询持久化结果：`GET /api/molecule-workflows/{workflow_id}`
- 认证：`Authorization: Bearer <token>`
- 可选幂等头：`Idempotency-Key: <client-generated-key>`

`POST` 的 OpenAPI `201` response example 是完整成功响应，包含九个计算阶段、HF 能量、活性空间、全部 Pauli 项、QASM、VQE 迭代历史、分区方案、虚拟节点映射、通信事件与次数、两类模拟能量及绝对误差。`404/409/422/503` 均提供失败响应示例。

## Workflow history

`GET /api/molecule-workflows` requires the same Bearer token as creation and
returns only the caller's records. Query parameters are `page` (default `1`),
`page_size` (default `20`, maximum `100`), and optional exact-match filters
`molecule_name`, `status` (`running|completed|failed`), and `validation_status`
(`passed|needs_review`). The result contains `items`, `page`, `page_size`,
`total`, and `total_pages`; an out-of-range positive page returns an empty
`items` array while preserving the total.

Each item is a compact persisted-result summary: workflow and molecule identity,
creation/completion time and duration, execution and validation status, optimizer,
qubit/Pauli counts, VQE energy, distributed energy, and absolute error. Historical
failed or legacy records can have nullable result-derived fields.

第一版是同步接口。PySCF、Hamiltonian 映射和 VQE 可能耗时，前端应显示运行中状态并设置适当的请求超时；重复提交应复用同一个 `Idempotency-Key`。

## 固定约束

- 直接消费请求中的固定几何，不执行 DFT 或其他几何优化。
- 原子数为 `1..10`。
- 自动活性空间最多 6 个空间轨道，映射后最多 12 个量子比特。
- `execution_mode` 只能是 `logical_virtual_qpu`。
- 响应固定返回 `is_real_qpu: false`，不得在 UI 标记为真实 QPU。
- 当前统一 Workflow 固定使用 Jordan–Wigner 映射；这保证活性电子对应的 Hartree–Fock 占据初态可以被明确编码。
- 当前 VQE 线路以 Hartree–Fock 占据态初始化，随后使用 `hardware_efficient_ry_cx`，优化器是 Powell。SciPy 的原始终止结论通过 `vqe.optimizer_diagnostics` 返回，不会被人为改写为收敛。
- 分布式能量由按虚拟节点排列的分区张量实际执行 QASM 后重组 Pauli 期望值得到，不复用未分区 VQE 最终能量。

## 请求示例

H₂：

```json
{
  "molecule_name": "H2",
  "geometry": [
    {"element": "H", "coordinates_angstrom": [0.0, 0.0, 0.0]},
    {"element": "H", "coordinates_angstrom": [0.0, 0.0, 0.735]}
  ],
  "charge": 0,
  "spin_multiplicity": 1,
  "basis_set": "sto-3g",
  "mapping_method": "jordan_wigner",
  "active_space_orbitals": 2,
  "pauli_coefficient_cutoff": 0.000001,
  "vqe": {
    "ansatz_layers": 1,
    "max_iterations": 80,
    "convergence_tolerance": 0.0001,
    "shots": 1024
  },
  "partition": {
    "partition_count": 2,
    "topology_edges": [{"source": 0, "target": 1}]
  },
  "execution_mode": "logical_virtual_qpu"
}
```

LiH 使用相同契约，将名称和几何替换为：

```json
{
  "molecule_name": "LiH",
  "geometry": [
    {"element": "Li", "coordinates_angstrom": [0.0, 0.0, 0.0]},
    {"element": "H", "coordinates_angstrom": [0.0, 0.0, 1.595]}
  ]
}
```

H₂O 使用相同契约，将名称和几何替换为：

```json
{
  "molecule_name": "H2O",
  "geometry": [
    {"element": "O", "coordinates_angstrom": [0.0, 0.0, 0.0]},
    {"element": "H", "coordinates_angstrom": [0.7586, 0.0, 0.5043]},
    {"element": "H", "coordinates_angstrom": [-0.7586, 0.0, 0.5043]}
  ]
}
```

后两个片段只展示需要替换的字段，调用时仍需发送完整请求对象。

## 响应字段约定

| 字段 | 含义 |
| --- | --- |
| `stages` | 九阶段执行状态、时间和阶段摘要 |
| `hf_energy_hartree` | PySCF SCF 返回的 HF 总能量 |
| `active_space` | 活性电子数、空间轨道数、轨道索引与选择依据 |
| `hamiltonian.pauli_terms` | 映射和阈值截断后的完整 Pauli 项 |
| `vqe.qasm` | 最优参数对应的 OpenQASM 2.0 |
| `vqe.iteration_history` | 每次目标函数评估的参数、能量和不确定度 |
| `distribution.partition_scheme` | 现有线路分区算法返回的分区及代价统计 |
| `distribution.virtual_node_mapping` | 分区到逻辑虚拟 QPU 节点的映射 |
| `distribution.communication_events` | 实际执行中每个跨分区 CX 的源/目标节点证据 |
| `distribution.cross_partition_communication_count` | 上述通信事件数量 |
| `energies.unpartitioned_benchmark_energy_hartree` | 原 VQE 状态向量执行器的最终能量 |
| `energies.distributed_simulation_energy_hartree` | 消费分区和映射后的逻辑分布式模拟能量 |
| `energies.absolute_error_hartree` | 两种执行路径能量的绝对差 |

## 失败响应

工作流业务失败使用统一结构：

```json
{
  "detail": {
    "code": "electronic_structure_runtime_unavailable",
    "message": "PySCF/OpenFermion 计算运行时不可用：PySCF Docker runtime is unavailable or timed out.",
    "stage": "electronic_structure",
    "workflow_id": "molwf_8c1c4ceff69049aa9bc3d9f582a1a9c7"
  }
}
```

请求模型校验失败仍使用 FastAPI 标准 `422` 校验错误数组；进入工作流后发生的 `422` 使用上述统一结构并带有可查询的 `workflow_id`。

## 持久化与回滚

应用启动时通过 SQLAlchemy 创建 `molecule_workflows` 表；也可以显式执行 `backend/scripts/create_molecule_workflows_table.sql`。新增表不修改已有数据或接口。

如需回滚，先确认结果不再需要，再执行 `DROP TABLE molecule_workflows;`，并移除路由注册和 ORM 模型。该回滚会永久删除分子工作流结果，执行前必须备份。

PySCF/OpenFermion 运行时镜像构建命令：

```powershell
docker build -t liangzhi-qchem:local backend/quantum_chemistry_adapter
```

## Execution status and scientific validation

## Scientific audit (P1.1)

New calculations retain `contract_version: "2.0"` for additive compatibility
and identify their scientific artifact with `vqe.ansatz`,
`vqe.ansatz_version`, `vqe.simulator_version`,
`hamiltonian_builder_version`, and `scientific_validation_version`.

The default VQE ansatz is `uccsd_particle_conserving_pauli` version `1.0`.
It applies spin-conserving singles
`exp(theta/2 (a†_p a_q - a†_q a_p))` and paired doubles
`exp(theta/2 (a†_r a†_s a_q a_p - h.c.))`. Their Jordan--Wigner Pauli
rotations compile only to `H`, `S`, `SDG`, `RZ`, and `CX`. Therefore zero
parameters exactly preserve the Hartree--Fock determinant and all parameters
preserve particle number. The same gate semantics are used by unpartitioned
simulation, QASM parsing, routing and logical distributed simulation.

Results expose three independent conclusions: `optimizer_validation`,
`scientific_validation`, and `deployment_validation`. The deprecated legacy
`validation_status` remains optimizer-only for existing consumers; it must not
be interpreted as scientific acceptance. `scientific_validation` reports the
HF determinant/zero-parameter checks, exact qubit diagonalization, same-active
space FCI, particle-number expectation/variance, the real VQE--FCI error and
the public `chemical_accuracy_threshold_hartree: 1.6e-3`.

`status: "completed"` means every workflow stage finished and the complete result
was persisted. It does not mean that the scientific result has passed convergence
validation. `validation_status` is `passed` only when VQE reports convergence;
otherwise it is `needs_review` and `validation_issues` retains a
`vqe_not_converged` record with the `vqe_optimization` stage, iteration count, and
an explanation. A needs-review result still includes its complete VQE history,
energies, partition plan, virtual-node mapping, and communication evidence.

`vqe.optimizer_diagnostics` records SciPy's `success`, `status`, `message`, and
`nfev`, together with a normalized termination reason, best iteration, initial and
final energy, and the most recent energy deltas. These diagnostics report the
optimizer outcome as-is; they do not alter its convergence decision.

## Contract v2: physical virtual-chip routing

`GET /api/molecule-workflows/capabilities` is authenticated and declares the
contract boundary. It reports supported elements/bases, `max_atom_count: 10`,
`max_mapped_qubits: 12`, partition counts, `sequential_greedy`, user-supplied
inter-QPU and physical coupling edge lists, `identity|dense_greedy` layout,
`shortest_path_swap` routing, and only `logical_virtual_qpu` with
`is_real_qpu: false`.

`partition.topology_edges` remains accepted for compatibility, but new clients
must send `inter_qpu_topology`. It describes the network between virtual QPUs;
it is not a chip coupling map. Each `virtual_qpus[]` item carries a distinct
`physical_qubit_count` and `physical_coupling_map` for that virtual chip.

```json
{
  "molecule_name": "H2",
  "geometry": [
    {"element": "H", "coordinates_angstrom": [0.0, 0.0, 0.0]},
    {"element": "H", "coordinates_angstrom": [0.0, 0.0, 0.735]}
  ],
  "charge": 0,
  "spin_multiplicity": 1,
  "basis_set": "sto-3g",
  "mapping_method": "jordan_wigner",
  "active_space_orbitals": 2,
  "partition": {
    "partition_count": 2,
    "partition_strategy": "sequential_greedy",
    "inter_qpu_topology": [{"source": 0, "target": 1}],
    "virtual_qpus": [
      {"virtual_qpu_id": "T1", "physical_qubit_count": 2, "physical_coupling_map": [{"source": 0, "target": 1}]},
      {"virtual_qpu_id": "T2", "physical_qubit_count": 4, "physical_coupling_map": [{"source": 2, "target": 3}]}
    ],
    "initial_layout": "identity",
    "routing_method": "shortest_path_swap"
  },
  "execution_mode": "logical_virtual_qpu"
}
```

Each v2 result persists `contract_version: "2.0"`, `inter_qpu_topology`,
`partition_chip_routing`, initial/final logical-to-physical layouts, routed gate
sequences, per-CX route evidence, original/routed two-qubit counts, and
`intra_chip_routing_cost`. These are intentionally separate from
`communication_events` and `cross_partition_communication_count`.

P0.1 adds a tenth `chip_topology_routing` stage and makes
`distribution.routed_execution_plan` the actual input of logical distributed
simulation. Every plan step has global `execution_index`, `original_gate_index`,
physical gate addresses, scope (`intra_qpu|inter_qpu`), and before/after layouts.
`actual_routed_plan_consumption: true` proves that the result was produced from
this plan. The simulator resolves physical operations through the current layout
and evaluates observables against the final logical-to-physical layout.

The depth-looking fields were replaced with operation counts:
`original_operation_count`, `routed_operation_count`,
`original_two_qubit_operation_count`, and
`routed_two_qubit_operation_count`. Routing cost separately exposes
`abstract_swap_count`, routed two-qubit operation count, and
`native_two_qubit_gate_equivalent_count` (one SWAP equals three native CX).
Physical addresses are local to each virtual chip (`0..N-1`); the default chip
capacity is the assigned partition size. Only `identity` layout is advertised in
P0.1; `dense_greedy` is intentionally not exposed.

For UI routing visualisation, use the zero-SWAP full response fixture above and
the [forced-SWAP execution-plan fixture](fixtures/molecule-workflow-v2-h2-forced-swap-success.json).

## Molecular deployment studies

`POST /api/molecular-studies` is an authenticated asynchronous API. It accepts
the existing molecule/VQE request fields plus at least three unique
`architectures`, each containing an `architecture_id` and a full `partition`
topology/virtual-chip request. It returns `202` with `study_id` and `problem_id`.
`GET /api/molecular-studies/{study_id}` restores the persisted study for its
owner only.

The service persists three layers: a `MolecularProblem` with one PySCF,
Hamiltonian mapping and VQE/QASM result; a `DeploymentStudy`; and one
`DeploymentEvaluation` per architecture. Every evaluation independently runs
partitioning, virtual-node mapping, physical routing and routed-plan logical
simulation. It reports deployability/failure, partition scale, SWAP count,
cross-QPU communication, original/routed operation counts, native two-qubit
equivalent cost, independently computed distributed energy/error, and routed
plan consumption evidence.

`vqe_fci_scientific_error_hartree` is currently `null` unless a constrained
active-space FCI runtime is configured. It is intentionally separate from
`distributed_vqe_vqe_execution_error_hartree`; the latter is never populated by
copying the unpartitioned VQE energy.

When the physical capacity is too small or no path exists, POST returns the
normal 422 business error shape with `physical_qubit_insufficient` or
`physical_coupling_disconnected`, stage `chip_topology_routing`. Existing
persisted workflows can omit v2 fields; their response has `contract_version`
and routing fields as `null` rather than failing GET.

The front-end-ready full H2 success fixture is
[`docs/fixtures/molecule-workflow-v2-h2-success.json`](fixtures/molecule-workflow-v2-h2-success.json).
It represents virtual-node logical distributed simulation only, never real-QPU
execution.

## Molecular Study API contract (P0.1.1)

`POST /api/molecular-studies` and `GET /api/molecular-studies/{study_id}` both
require `Authorization: Bearer <token>`. A submission contains the normal
molecular request plus at least three unique `architectures`; POST returns
`202 Accepted`. New clients must use `molecular_problem_id`. `problem_id` is a
deprecated compatibility alias only.

Study status is exactly `queued | running | completed | failed`. Continue
polling for `queued` and `running`, and stop for `completed` and `failed`.
During queued/running states `result` is a stable, typed partial skeleton:
`molecular_problem`, `deployment_evaluations`, and `summary` are always present
while fields not yet calculated are `null`. A Study can be `completed` with a
mix of deployable and non-deployable architectures. Only failure of the shared
molecular problem, scheduling, or an unrecoverable Study-level error yields
Study `failed`; an individual architecture runtime error is
`evaluation.status=failed`, `is_deployable=null` and does not alone fail its
parent Study.

The OpenAPI components are `MolecularStudyAcceptedResponse`,
`MolecularStudyResponse`, `MolecularStudyResult`, `MolecularProblemResult`,
`DeploymentEvaluationResult`, `MolecularStudySummary`, and
`MolecularStudyErrorResponse`. `MolecularStudyResponse.result` is explicitly
`MolecularStudyResult | null`, not an unstructured object. `MolecularProblemResult`
contains the full typed molecule/HF/active-space/Hamiltonian/VQE data, QASM and
iteration history. Its FCI object always has `status`, `method`,
`energy_hartree`, and `message`; when FCI is not configured the status is
`not_configured` and both energy fields are `null` (never zero).

Each `DeploymentEvaluationResult` reports the architecture, partition summary,
separate routing/communication metrics, independent energy validation, and the
reused typed `DistributionResult` evidence (`routed_execution_plan`, routing
evidence, communication events, consumption flags, final layout, and state
norm). Capacity or coupling-topology rejections are a business result:
`status=completed`, `is_deployable=false`, and a typed `failure_reason`.

The endpoint OpenAPI provides examples for the POST `202` response, running,
completed, failed, `401`, `404`, FastAPI request-validation `422` (detail array),
business `422` (typed detail object), and `503`. Background PySCF/VQE errors
after a request has been accepted are observed by `GET 200` with
`status=failed`; `503` is reserved for an unavailable scheduler/query service.

The schema-validated three-architecture H2 fixture records real execution
metadata from Study `study_b98937370e114449827c06e176beae59`, including the
zero-SWAP and forced-SWAP architectures:
[`docs/fixtures/molecular-study-h2-three-architecture-success.json`](fixtures/molecular-study-h2-three-architecture-success.json).
It is logical virtual-QPU simulation (`is_real_qpu: false`), not real-QPU
execution.
