# 前端：FeN4C66 + Li2S4 文献基准工作台需求

> 完成状态：已完成\
> 验收日期：2026-07-15\
> 验收记录：见《前端-FeN4C66-Li2S4文献基准工作台验收记录》

## 1. 背景与目标

系统后端已导入并校验公开的 `FeN4C66 + Li2S4` 文献基准数据集，包含 2,119 个文献候选构型。当前前端没有该基准的入口、候选选择页面或复现工作流证据链展示，用户只能通过后端接口操作。

本需求交付一个只面向已导入基准的 P0 工作台，使登录用户可以：

```text
查看文献与数据来源
-> 查看并筛选文献候选构型
-> 明确了解候选源能量的语义边界
-> 主动选择一个候选
-> 进入独立的文献复现工作流
-> 查看结构、构型、几何与后续量子步骤的状态和 Artifact
```

本期目标是“文献复现输入可追溯”，不是在前端宣称已完成平台独立 DFT 重算、吸附能计算或真机 QPU 验证。

相关科学约束以 [FeN4C66 + Li2S4 文献 Benchmark 协议](../../docs/fe-n4c66-li2s4-benchmark-protocol.md) 为准。

## 2. 范围与非范围

### 2.1 本期范围（P0）

1. 增加“文献基准”入口、基准概览页、候选构型页和复现工作流详情页。
2. 展示来源 DOI、公开数据集链接、许可、数据集版本、DFT 元数据、校验状态和科学验证等级。
3. 对 2,119 个候选提供搜索、排序、虚拟列表渲染和单选创建工作流。
4. 对已创建的文献复现工作流展示 8 个阶段、来源标签、警告、Artifact 元数据和下载入口。
5. 正确处理无权限、基准未导入、候选不存在、重复导入和网络失败。

### 2.2 明确不在本期范围

1. 前端不执行 DFT、VQE 或吸附能计算。
2. 前端不把 `source_energy` 显示为“吸附能”“结合能”或最终稳定性排名。
3. 前端不根据 `SPIN_FIX: 2`、Fe 初始磁矩或源能量自动得出最终自旋态。
4. 前端不提供“批量选择全部候选并运行”的入口。
5. 不新增或伪造候选坐标、DFT 输出、计算日志或科学结论。

## 3. 用户与权限

| 用户 | 可见能力 | 限制 |
| --- | --- | --- |
| 已登录用户 | 查看已导入基准、查看候选、选择候选、查看自己创建的文献复现工作流 | 只能查看自己的工作流和 Artifact |
| 研究基准管理员 | 以上能力，以及触发一次性导入 | 导入成功后不得以同一 `benchmark_key` 覆盖原始 Artifact |
| 未登录用户 | 无 | 跳转登录页 |

“导入”不是普通用户的必经步骤。生产入口默认展示已导入的 `fe-n4-c66-li2s4-literature-v1`；管理员导入动作应收纳在受权限保护的二级操作中。

## 4. 信息架构与路由

建议在应用主导航的“科研建模”下新增“文献基准”。路由名称可按现有项目规范调整，但页面职责不可合并到普通多材料筛选结果页。

```text
/app/research-benchmarks
  文献基准列表/默认基准概览

/app/research-benchmarks/:benchmarkId
  基准概览 + 候选构型工作台

/app/structure-workflows/:workflowId
  文献复现工作流详情（可复用或扩展现有结构建模结果页）
```

普通筛选任务、用户上传结构工作流和文献复现工作流必须使用不同的来源标签和文案，不能共用“筛选完成”状态。

## 5. 页面与交互要求

### 5.1 基准概览页

页面首屏必须展示以下事实：

| 字段 | 显示规则 |
| --- | --- |
| 标题 | `FeN4C66-Li2S4 Materials Cloud 文献复现基准` |
| 模型 | 周期性 `FeN4C66 + Li2S4` |
| 来源 | Materials Cloud 链接、论文 DOI 链接、`CC-BY-4.0`、数据集版本 |
| 数据来源 | 标签：`公开文献数据集` |
| 候选数量 | 由接口 `candidate_count` 返回；当前验收数据为 2,119 |
| 科学验证等级 | 标签：`仅文献复现基线`，对应 `reproduction_baseline_only` |
| DFT 元数据 | CASTEP、GGA-PBE、500 eV、`3 × 3 × 1` k 点、D2/G06、约 18 Å 真空层、自旋极化；仅显示后端实际返回的字段 |

页面必须固定显示如下提示：

> 当前数据为公开文献中已优化候选的复现输入。平台尚未完成独立 DFT 重算；候选源能量的单位语义未确认，不能作为吸附能或材料推荐结论。

主操作为“查看 2,119 个文献候选”。若基准不存在，展示空状态和“请管理员导入已审核数据集”，普通用户不得看到导入按钮。

### 5.2 候选构型工作台

候选列表数据来自 `GET /api/platform/research-benchmarks/{benchmarkId}/candidates`。当前接口一次返回全部候选，因此前端必须在本地完成搜索、排序和虚拟滚动；不得将 2,119 行同时渲染为 DOM 节点。

每行至少展示：

| 字段 | 数据来源 | 规则 |
| --- | --- | --- |
| 文献候选 ID | `source_candidate_id` | 支持精确搜索 |
| 优先序 | `priority_rank` | 默认升序；仅表示数据集中的源能量排序 |
| 源能量 | `source_energy` + `source_energy_unit` | 字段值原样显示，紧跟“源数据原始单位，未确认”标签 |
| 组成校验 | `source_metadata` | 显示 `C66 Fe1 N4 Li2 S4`；异常时禁止选择 |
| 构型状态 | `status` | `literature_candidate` 显示“文献候选构型” |
| 坐标 Artifact | `coordinate_artifact_id` | 支持查看元数据；下载能力依赖工作流创建后对应 Artifact 权限 |

支持以下交互：

1. 按候选 ID 搜索。
2. 按优先序升降序排列。
3. 仅筛选组成校验通过的候选。
4. 单选一个候选，并在详情抽屉查看来源元数据和坐标摘要。
5. 点击“以此构型创建文献复现工作流”。

选择确认弹窗必须写明：

```text
将把不可变的文献候选复制为一个属于当前用户的独立工作流。
系统会保留论文 DOI、数据集、候选 ID、源能量和 Artifact 追溯关系。
该操作不会执行独立 DFT 重算，也不会产生可用于材料推荐的吸附能。
```

创建请求为：

```http
POST /api/platform/research-benchmarks/{benchmarkId}/candidates/{candidateId}/select
Authorization: Bearer <token>
```

成功后以返回的 `workflow_id` 跳转工作流详情页，并在成功提示中显示“已创建文献复现输入”，不得显示“计算完成”。按钮请求期间禁用，避免双击创建重复工作流。

### 5.3 文献复现工作流详情页

详情数据来自：

```http
GET /api/platform/structure-screening-workflows/{workflowId}
GET /api/platform/structure-screening-workflows/{workflowId}/artifacts/{artifactId}
GET /api/platform/structure-screening-workflows/{workflowId}/artifacts/{artifactId}/download
```

页面顶部的来源与状态必须使用后端原值映射：

| 后端值 | 前端中文文案 | 展示要求 |
| --- | --- | --- |
| `literature_open_dataset` | 公开文献数据集 | 固定来源标签 |
| `reproduction_baseline_only` | 仅文献复现基线 | 固定科学验证等级标签 |
| `literature_reproduction_input_selected` | 已选定文献复现输入 | 选择动作的完成状态 |
| `literature_reproduction_geometry_ready` | 文献优化几何已就绪 | 工作流状态，不等于平台 DFT 已完成 |
| `literature_selected` | 已选择文献优化候选 | 吸附构型状态 |
| `completed`（几何记录） | 已登记文献优化几何 | 必须同时显示来源，而非简写为“DFT 优化完成” |
| `not_started` | 尚未开始 | 后续量子步骤的默认状态 |

工作流阶段以纵向步骤条展示，至少包括：

```text
结构解析
-> Fe-N4 活性位点
-> Li2S4 吸附构型
-> 文献优化几何
-> 量子区
-> 活性空间
-> Hamiltonian
-> VQE
```

前四项是文献复现输入链；后四项在当前选择后可以尚未开始。不得把未开始的 Hamiltonian/VQE 区域渲染为空白成功卡片，更不得提前显示能量曲线、QPU 状态或材料推荐。

每个已完成阶段显示：来源、状态、警告摘要、创建时间，以及 Artifact 名称/类型/哈希（接口有值时）。Artifact 下载失败或无权限时保留元数据并显示明确错误，不隐藏错误。

### 5.4 管理员导入（受控次级能力）

管理员可在基准概览页的“管理操作”中看到“导入已审核的 Materials Cloud 基准”。表单字段固定为：

```json
{
  "benchmark_key": "fe-n4-c66-li2s4-literature-v1",
  "dataset_url": "https://archive.materialscloud.org/records/f5t2r-6qf35",
  "source_license": "CC-BY-4.0",
  "adsorbate": "Li2S4",
  "retain_raw_artifacts": true
}
```

请求为 `POST /api/platform/research-benchmarks/import-materials-cloud`。页面不得允许用户编辑为任意 URL、任意吸附物或其他许可证；后端也会校验。

处理 `409 research_benchmark_exists` 时，显示“该基准已导入，请返回基准列表查看”，不提供覆盖或删除操作。处理 `403` 时，显示“仅研究基准管理员可导入”。

## 6. 后端协作前置条件

现有接口可按 ID 获取基准，但没有“列出基准”或“按 `benchmark_key` 查询”的接口。前端不能硬编码数据库生成的 `benchmark_id`，因此 P0 开发前需后端补充以下最小只读接口之一：

```http
GET /api/platform/research-benchmarks?benchmark_key=fe-n4-c66-li2s4-literature-v1
```

返回至少包含与单条基准查询相同的字段和 `items` 数组。若后端选择增加 `GET /api/platform/research-benchmarks`，前端应使用列表接口，再按 `benchmark_key` 定位默认基准。

其余已存在接口的契约如下：

| 能力 | 接口 | 前端依赖 |
| --- | --- | --- |
| 获取基准详情 | `GET /research-benchmarks/{benchmarkId}` | 概览数据 |
| 获取候选 | `GET /research-benchmarks/{benchmarkId}/candidates` | 全量候选列表 |
| 选择候选 | `POST /research-benchmarks/{benchmarkId}/candidates/{candidateId}/select` | 创建独立工作流 |
| 获取工作流 | `GET /structure-screening-workflows/{workflowId}` | 阶段与证据链 |
| Artifact 元数据/下载 | `GET /structure-screening-workflows/{workflowId}/artifacts/...` | 追溯与下载 |

前端不得自行推断缺失字段；例如候选的原子组成或坐标摘要若未在 `source_metadata` 返回，应由后端补充后再实现相应展示。

## 7. 文案与科学边界

必须使用：

```text
公开文献数据集
仅文献复现基线
文献优化候选
源数据原始能量（单位语义未确认）
平台独立 DFT 重算尚未完成
模拟器 VQE（仅在后端真实返回 VQE 后显示）
```

禁止使用：

```text
已验证吸附能
最佳催化剂
DFT 计算完成（用于仅文献导入结果）
真实 QPU 结果（用于 simulator）
文献最低能构型即最终稳定结构
```

## 8. 验收标准

1. 登录用户可在主导航进入“文献基准”，不需要知道数据库 ID。
2. 概览页显示论文、数据集、许可、版本、候选数、DFT 元数据和 `reproduction_baseline_only`，且包含科学边界提示。
3. 2,119 个候选可搜索、排序和虚拟滚动，页面没有一次性渲染 2,119 行 DOM 的卡顿。
4. `source_energy` 始终带 `dataset_native_unit_not_confirmed`（或后端返回的同义原值）提示，页面中不出现“吸附能”表述。
5. 用户选择候选后成功创建自己的工作流，并跳转到返回的 `workflow_id`；重复点击不会产生重复请求。
6. 工作流页将 `literature_reproduction_geometry_ready` 显示为“文献优化几何已就绪”，不会显示为平台独立 DFT 已完成。
7. 后续量子阶段未开始时明确显示“尚未开始”，不会伪造 Hamiltonian、VQE、推荐结论或 QPU 状态。
8. 用户仅能下载自己工作流的 Artifact；403、404 和下载失败均有可见错误反馈。
9. 管理员导入对非管理员不可见且不可操作；遇到已存在基准只能查看，不可覆盖。
10. 前端构建通过，并至少覆盖以下 E2E 路径：进入基准 -> 搜索候选 -> 选择候选 -> 跳转工作流 -> 查看来源标签与阶段状态。

## 9. 交付物

1. 文献基准概览与候选工作台页面。
2. 文献复现工作流详情展示（新增或扩展现有结构建模结果页）。
3. 基准 API 客户端、状态映射、错误提示与虚拟列表组件。
4. 后端补充的基准发现接口及前后端接口联调记录。
5. 单元测试与上述 P0 E2E 验收记录。
