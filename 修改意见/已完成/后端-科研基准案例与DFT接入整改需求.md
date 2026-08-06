# 后端：科研基准案例与 DFT 接入整改需求

## 1. 目标

在已有“结构上传 -> 局部量子区 -> Hamiltonian -> 映射 -> VQE”原型基础上，建立一个可复现的 `Fe-N4 + Li2S4` 科研基准案例，并将“电荷、自旋、优化几何、DFT 来源”和“模拟器 VQE”作为可追溯的研究输入管理。

本次不要求接入真实 QPU。当前真实目标是：

```text
基准优化结构
-> 多自旋候选的电子结构计算
-> 选择可接受的自旋解
-> 活性空间与 Hamiltonian
-> simulator VQE
-> 与经典小体系基准对照
-> 形成可复现证据链
```

## 2. 调研结论与建模原则

`Fe-N4 + Li2S4` 不能由系统预先硬编码唯一的自旋多重度。

原因：

1. Li-S 研究表明 Fe-N4 的自旋态会随轴向配位和吸附环境变化。
2. Fe 等过渡金属体系存在开壳层和自旋极化问题；`RHF + 单重态` 失败不等于结构无效，而是说明当前电子结构模型不适用。
3. Li-S 催化的 DFT 研究通常通过自旋极化计算、优化构型、电子/自旋密度和吸附能共同判断，而不是仅根据初始结构决定结果。

因此，后端必须实现“候选自旋态比较、收敛质量检查、人工确认和全程留痕”，而不是让用户输入一个数字后直接进入 VQE。

## 3. P0：建立 Fe-N4 + Li2S4 基准数据包

### 3.1 基准对象

首期只定义一个版本化基准：

```text
催化剂：Fe@N4/C 或 FeN4-graphene 局部模型
吸附物种：Li2S4
目标：验证 Li2S4 在 Fe-N4 位点附近的局部吸附模型、电子结构和 VQE 计算链路
```

不得使用仅含 5 个原子的任意 FeN4 小团簇作为最终科研基准。该简化团簇可用于接口调试，但缺少碳载体与合理边界，容易造成不真实的电子结构和自旋解。

### 3.2 基准数据包内容

后端新增可版本化的 `research_case`/`benchmark_case` 数据对象，至少包括：

```text
benchmark_case_id
title
catalyst_model_type
adsorbate_species
structure_artifact_id
structure_origin
geometry_status
total_charge
spin_candidate_definitions
dft_metadata
accepted_reference_id
created_by
version
```

每个基准案例必须保存以下 Artifact：

1. 催化剂原始结构。
2. Li2S4 初始构型集合。
3. 每个自旋候选的优化后结构。
4. DFT 输入、输出和日志摘要。
5. 吸附前、吸附后、Li2S4 单体的能量结果。
6. 最终局部量子区、活性空间、Hamiltonian、Pauli 项、QASM 与 VQE 优化历史。

### 3.3 吸附构型管理

对同一 Fe-N4 位点至少保留多个 Li2S4 初始取向：Li 端、S 链端和侧向吸附。每个构型必须独立执行优化和自旋候选比较。

后端不应根据初始距离或几何质量分直接选出“最佳吸附构型”。优先顺序应为：

```text
DFT 优化成功
-> 自旋解可接受
-> 能量最低或按明确规则排序
-> 标记为 accepted_reference
```

## 4. P0：多自旋电子结构计算与质量控制

### 4.1 新增自旋候选任务

新增接口：

```http
POST /api/platform/quantum-regions/{quantum_region_id}/electronic-structure-candidates
GET /api/platform/electronic-structure-candidates/{candidate_id}
POST /api/platform/electronic-structure-candidates/{candidate_id}/confirm
```

请求不直接要求用户填写唯一自旋，而是允许提交候选策略：

```json
{
  "charge_candidates": [0],
  "spin_strategy": "transition_metal_auto_candidates",
  "requested_methods": ["UHF", "ROHF"],
  "basis_set": "def2-SVP",
  "max_scf_attempts": 3
}
```

具体自旋候选由化学配置文件定义。对 Fe-N4 这类体系，至少要能够比较低/中/高自旋相关候选；不能把单重态当作唯一默认值。

### 4.2 计算方法要求

1. 闭壳层可使用 `RHF`。
2. 开壳层优先使用 `UHF`，必要时支持 `ROHF`。
3. 默认基组不能固定为 `STO-3G`。`STO-3G` 仅用于接口调试，必须标注 `debug_basis_only`。
4. 面向 Fe-N4 基准，默认使用由化学负责人批准的过渡金属基组/ECP 方案；初始建议为 `def2-SVP` 或同等方案，但应允许按案例版本配置。
5. 每次 SCF 失败后，允许执行受控重试：调整初始猜测、DIIS、level shift、最大迭代数；每次尝试都要保存。
6. 计算必须异步执行，不能阻塞 HTTP 请求。

### 4.3 自旋污染与收敛判定

每个候选至少保存：

```text
candidate_id
total_charge
spin_multiplicity
scf_method
basis_set
converged
scf_iterations
total_energy_hartree
spin_square_s2
expected_spin_square_s2
spin_contamination_delta
quality_status
warnings
log_artifact_id
```

判定规则：

1. SCF 未收敛：`rejected` 或 `failed`，不可进入活性空间。
2. 自旋污染超出配置阈值：`needs_model_review`，不可自动进入 VQE。
3. 同一构型存在多个合格自旋解：按预先定义的能量与质量规则排序，保留全部候选，用户/化学负责人确认。
4. 不得仅因能量更低而自动接受明显自旋污染的解。

阈值不能在代码中写死；应由 `research_case` 配置或化学负责人确认后记录。

## 5. P0：外部 DFT 优化结果导入规范

平台暂不直接运行 Quantum ESPRESSO 或 CP2K 时，必须把外部 DFT 导入做成完整、可审计的能力。

### 5.1 接口

```http
POST /api/platform/adsorption-models/{adsorption_model_id}/dft-imports
GET /api/platform/dft-imports/{dft_import_id}
```

必须接收：

1. 优化后结构文件。
2. 软件名称和版本。
3. 计算类型：几何优化、单点能、吸附能、NEB 等。
4. 交换关联泛函。
5. 基组或赝势。
6. 色散修正。
7. 自旋极化/初始磁矩设置。
8. 总电荷和自旋信息。
9. 收敛阈值。
10. 总能量和单位。
11. 可选原始输出、日志和文献 DOI。

缺少结构、方法、收敛或自旋信息时，导入状态为 `metadata_incomplete`，不得标记为 `dft_optimized`。

### 5.2 吸附能可比性检查

若平台要展示吸附能，必须要求同一计算方案下同时提供：

```text
E(Fe-N4/C + Li2S4)
E(Fe-N4/C)
E(Li2S4)
```

并清楚保存公式：

```text
E_ads = E(Fe-N4/C + Li2S4) - E(Fe-N4/C) - E(Li2S4)
```

三项能量的软件、泛函、基组/赝势、色散修正、k 点和自旋设置不一致时，系统只存档，不生成可比较的吸附能。

## 6. P1：接入直接 DFT 引擎

外部导入稳定后，优先级为：

1. `Quantum ESPRESSO`：适合开源、周期性材料与比赛环境。
2. `CP2K`：适合大体系和嵌入/混合计算扩展。
3. `VASP`：可支持结果导入，但不作为默认自动依赖。

直接 DFT Adapter 必须具备：

1. 输入文件生成。
2. 异步任务队列。
3. 资源限制、超时、取消和失败重试。
4. 输出解析和日志 Artifact。
5. 结构、方法、赝势、k 点、自旋、收敛与能量的统一数据模型。
6. 不能把 DFT 引擎命令散落在业务 service 中，应使用统一 Adapter 接口。

## 7. P1：VQE 与经典基准对照

对于已确认的局部量子区，流程为：

```text
DFT 优化几何
-> 局部量子区与嵌入环境
-> 活性空间
-> CASCI/FCI 小体系参考（可行时）
-> 费米子 Hamiltonian
-> Parity/Jordan-Wigner 映射
-> VQE simulator
-> 与经典基准比较
```

必须返回：

```text
classical_reference_method
classical_reference_energy_hartree
vqe_energy_hartree
absolute_energy_error_hartree
relative_energy_error
vqe_converged
execution_backend_type
```

只有基准对照存在时，才可将结果标为 `benchmark_validated_simulator_vqe`。没有对照时只能标为 `exploratory_simulator_vqe`。

## 8. P2：真实 QPU 扩展

真实 QPU 不属于本次 P0/P1 验收项。接入时必须另行实现：

1. QPU Provider Adapter。
2. 认证信息安全管理。
3. backend、队列、shots、噪声缓解和费用控制。
4. 真实设备运行 ID、校准信息、排队时间和硬件版本记录。
5. 结果标识为 `qpu_vqe`，不能与 `simulator_vqe` 混用。

## 9. 自动化测试与验收

必须新增：

1. Fe-N4 + Li2S4 至少一个候选自旋解能稳定进入活性空间阶段。
2. SCF 不收敛和自旋污染超阈值正确进入 `needs_model_review`。
3. 合格 DFT 导入可形成 `dft_optimized` 几何；元数据不足的导入会被拦截。
4. 吸附能三项能量不一致时不生成可比较吸附能。
5. 基准模型可生成 Hamiltonian、Pauli 项、OpenQASM 2.0、模拟器 VQE 和迭代记录。
6. 有 CASCI/FCI 对照时，能生成误差报告。
7. 当前内置 demo workflow 不受影响，且用户结构不回退到 demo 固定评分。

完成定义：提供一个版本化的 Fe-N4 + Li2S4 基准案例，包含输入、DFT 来源或导入信息、自旋候选比较、选定结构、Hamiltonian、VQE 迭代记录和经典对照；他人可使用相同 Artifact 复现该案例。

## 10. 参考依据

1. [Fe-N4 自旋调控与 Li-S 催化研究](https://www.sciencedirect.com/science/article/pii/S2405829722006687)
2. [单原子 M@N4/G 的 Li-S 催化理论筛选研究](https://pubs.rsc.org/en/content/articlelanding/2021/ta/d1ta01948a)
3. [Li2S2/Li2S 转化中采用自旋极化 DFT、报告自旋密度和优化结构的研究](https://www.sciencedirect.com/science/article/pii/S2405829722000721)
4. [Li2S4 吸附构型、吸附能和电子转移的 Li-S 研究](https://www.nature.com/articles/s41467-022-35736-x)
