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
