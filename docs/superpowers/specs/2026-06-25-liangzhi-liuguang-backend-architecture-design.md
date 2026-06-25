# 量智硫光后端架构设计说明

> 面向开发交付的后端设计文档。本文档用于指导“量智硫光”项目后端系统的目标平台设计与后续研发拆解，采用“微服务平台 + 统一编排中心”的架构模式，覆盖候选材料管理、化学建模、量子问题构造、分布式量子编译、模拟执行、综合评分、结果聚合与展示服务。

## 1. 文档目的

本文档定义“量智硫光”后端平台的总体定位、服务边界、工作流编排、数据域划分、存储架构、服务通信模式、任务状态机、基础设施要求、安全与可观测性要求，以及开发实施边界。

本文档不是现有 FastAPI 项目的说明文档，而是“量智硫光”目标后端平台的架构设计说明。开发团队可基于本文档拆解后续实现计划与工程任务。

## 2. 平台背景与问题定义

“量智硫光”项目的目标不是单纯提供一个量子线路划分工具，而是构建一条围绕锂硫电池催化材料筛选的量子-经典协同求解链路：

`候选材料输入 -> 活性位微模型构建 -> 化学建模 -> 量子问题构造 -> 分布式量子编译 -> 模拟执行与评估 -> 综合评分 -> 推荐输出`

在这个目标下，后端系统必须解决以下问题：

- 如何把多个专业计算阶段组织成一条完整、可回溯的工作流
- 如何管理长链路任务的状态、失败、重试与结果聚合
- 如何解耦化学建模、量子求解、分布式编译和评分逻辑
- 如何为前端展示层和能力工作台提供统一、稳定的结果视图
- 如何支持后续平台扩展，而不把所有复杂度继续堆在单体服务中

现有代码中的 FastAPI 后端已经具备以下雏形能力：

- 用户认证
- QASM 电路上传与解析
- 分区任务提交与轮询
- 芯片映射计算
- 历史记录查询
- 报告导出

这些能力可以视为目标平台中“分布式量子编译子域”的初始基础，但它们并不足以承载完整科研平台的后端职责。

## 3. 目标平台定位

后端目标平台定位为：

**一个面向锂硫电池催化材料筛选的微服务化科研计算平台，以统一编排中心为核心，组织化学建模、量子问题生成、分布式量子编译、模拟评估和综合推荐输出。**

平台必须具备以下特征：

- 强流程编排能力
- 多阶段异步任务能力
- 领域服务边界清晰
- 中间工件可追踪、可回溯
- 面向展示层和工作台输出统一结果
- 支持未来按服务独立扩展、替换和部署

## 4. 架构原则

### 4.1 平台原则

- 平台优先，不做接口拼装式系统
- 编排优先，不让前端承担流程控制
- 工件优先，确保中间结果可追踪
- 解耦优先，服务按领域职责分离

### 4.2 工程原则

- 使用统一编排中心管理完整实验任务
- 采用事件驱动与任务驱动结合的方式进行跨服务协作
- 事务型数据与大体量中间工件分层存储
- 前端不直接理解下游领域服务细节，只消费统一平台输出

### 4.3 演进原则

- 平台目标按微服务设计
- 各服务对外契约稳定，内部实现可演进
- 允许部分领域服务先使用占位实现或本地模拟实现
- 现有 FastAPI 单体可作为部分服务的早期原型来源

## 5. 总体架构概览

后端采用以下整体结构：

1. `API Gateway`
2. `Platform Orchestrator`
3. 领域服务集群
4. 元数据与工件存储层
5. 消息与任务基础设施
6. 可观测性与安全治理层

平台核心是 `Platform Orchestrator`。它不是业务算法服务，而是平台“大脑”，负责接收任务、编排流程、追踪状态、聚合结果和统一对外输出。

## 6. 核心服务划分

## 6.1 `API Gateway`

### 职责

- 统一前端入口
- 认证鉴权透传
- 请求路由
- API 版本控制
- 限流与审计
- 统一错误格式输出

### 不负责

- 不负责具体业务编排
- 不负责计算逻辑
- 不负责结果聚合

## 6.2 `Platform Orchestrator`

### 职责

- 创建实验工作流实例
- 维护阶段状态机
- 按顺序或条件触发下游服务
- 管理任务失败、超时、重试与补偿
- 汇总各阶段输出引用
- 输出统一任务视图

### 平台角色

它是整套平台的“总指挥”，前端只与网关和编排中心感知的任务视图交互，不直接理解化学服务、量子服务和编译服务的内部流程。

### 不负责

- 不负责具体化学计算
- 不负责量子线路生成
- 不负责分区映射算法
- 不负责评分公式本身

## 6.3 `Candidate Service`

### 职责

- 管理候选材料
- 管理活性位模板
- 管理硫化锂中间体模板
- 管理预置演示案例
- 管理实验配置模板

### 输出

- 候选任务清单
- 模板化输入配置
- 实验初始上下文

## 6.4 `Chemistry Modeling Service`

### 职责

- 构建活性位微模型
- 生成吸附构型
- 经典量子化学前处理
- 单电子/双电子积分计算
- 费米子问题输入准备
- 活性空间裁剪

### 输出

- 原子坐标与构型描述
- 电子结构元数据
- 积分集元数据
- 费米子哈密顿量输入工件

## 6.5 `Quantum Problem Service`

### 职责

- 费米子哈密顿量构造
- Jordan-Wigner 或等效映射
- 量子比特哈密顿量生成
- Hartree-Fock 初态构造
- 参数化 Ansatz 构造
- 基础门分解
- 量子线路骨架 / QASM 工件导出

### 输出

- qubit Hamiltonian
- initial state definition
- ansatz definition
- circuit skeleton
- qasm artifact

## 6.6 `Distributed Compiler Service`

### 职责

- 量子线路划分
- 多芯片映射
- 跨 QPU 路由优化
- 部署代价与指标统计
- 等效分布式线路输出

### 平台地位

该服务是现有量子线路划分优化系统能力的主要承接域。

### 输出

- partition result
- mapping result
- routing result
- deploy metrics

## 6.7 `Simulation & Evaluation Service`

### 职责

- 编译后线路模拟执行
- 基态能量或目标能量评估
- 编译前后结果一致性校验
- fidelity / error 分析
- 能量差与保持性评估

### 输出

- simulation run result
- energy result
- fidelity check
- error analysis

## 6.8 `Scoring Service`

### 职责

- 门控规则判定
- 化学性能分计算
- 分布式部署分计算
- 综合推荐分计算
- 排名与推荐解释生成

### 输出

- gatekeeping result
- ChemScore
- DeployScore
- FinalScore
- recommendation rank

## 6.9 `Result Aggregation Service`

### 职责

- 汇总多服务结果
- 生成前端可消费的统一结果视图
- 组装图表数据
- 组装工作台摘要数据
- 生成展示层推荐结果数据

### 目标

让前端面对的是“平台结果视图”，而不是多个底层服务的拼装结果。

## 6.10 `Workflow Metadata Service`

### 职责

- 保存工作流实例
- 保存阶段运行记录
- 保存任务事件日志
- 保存阶段输入输出引用
- 支持历史查询、回溯、审计

## 6.11 `Report & Visualization Service`

### 职责

- 生成展示层图表数据
- 导出报告
- 导出工件索引
- 生成结构化可视化数据

## 6.12 `User/Auth Service`

### 职责

- 用户身份管理
- 权限管理
- 会话与令牌管理
- 展示层与能力层访问控制

## 7. 服务边界总结

平台中最重要的边界如下：

- **流程控制** 只属于 `Platform Orchestrator`
- **领域计算** 各归其领域服务
- **统一结果视图** 属于 `Result Aggregation Service`
- **历史与回溯** 属于 `Workflow Metadata Service`
- **前端入口与安全边界** 属于 `API Gateway` 与 `User/Auth Service`

如果没有这个边界约束，平台很容易退化为“服务互调 + 前端拼装 + 状态分散”的混乱系统。

## 8. 核心调用链

标准实验任务链如下：

1. 前端向 `API Gateway` 发起实验请求
2. `Gateway` 校验身份并路由到 `Platform Orchestrator`
3. `Orchestrator` 创建 `workflow_instance`
4. `Orchestrator` 调用 `Candidate Service` 获取案例与输入配置
5. 调用 `Chemistry Modeling Service` 生成化学微模型与电子结构输入
6. 调用 `Quantum Problem Service` 生成量子问题与线路骨架
7. 调用 `Distributed Compiler Service` 进行划分、映射、路由与部署统计
8. 调用 `Simulation & Evaluation Service` 进行模拟执行与结果评估
9. 调用 `Scoring Service` 执行门控判定与评分计算
10. 调用 `Result Aggregation Service` 生成统一结果视图
11. `Orchestrator` 将工作流状态更新为完成
12. 前端通过统一任务接口获取结果与阶段状态

## 9. 任务状态机设计

统一编排中心必须维护明确的阶段状态，而不是只给出“queued/running/completed/failed”这类粗粒度状态。

建议工作流状态如下：

- `created`
- `validated`
- `screening`
- `chem_modeling`
- `quantum_encoding`
- `distributed_compiling`
- `simulation_evaluating`
- `scoring`
- `aggregating`
- `completed`
- `failed`
- `partial_completed`
- `cancelled`

### 状态设计说明

- `created`：工作流实例已创建
- `validated`：输入通过校验
- `screening`：经典粗筛阶段进行中
- `chem_modeling`：化学建模阶段进行中
- `quantum_encoding`：量子问题构造阶段进行中
- `distributed_compiling`：分布式编译阶段进行中
- `simulation_evaluating`：模拟执行与评估阶段进行中
- `scoring`：评分阶段进行中
- `aggregating`：结果聚合阶段进行中
- `completed`：全流程成功结束
- `failed`：关键阶段失败，无法继续
- `partial_completed`：存在非关键失败，但产出仍可展示
- `cancelled`：人工取消

### 阶段级状态

每个主状态之下还应记录阶段运行状态：

- `pending`
- `running`
- `success`
- `failed`
- `skipped`
- `retrying`

## 10. 通信模式设计

## 10.1 同步调用

适用于：

- 配置校验
- 元数据查询
- 展示层读请求
- 小型结果聚合查询

建议使用：

- HTTP/gRPC

## 10.2 异步调用

适用于：

- 长耗时化学建模
- 量子问题生成
- 编译求解
- 模拟执行
- 报告生成

建议使用：

- 消息队列 + 任务执行器

## 10.3 推荐模式

- 前端到平台：同步 API
- 编排到领域服务：任务驱动 + 异步回调/事件回传
- 结果读取：统一查询 API

## 11. 数据域划分

平台不应再使用“用户/电路/任务/映射”四表模型承载全部业务。目标平台至少按以下数据域组织：

## 11.1 Identity Domain

- `users`
- `roles`
- `permissions`
- `sessions`
- `api_tokens`

## 11.2 Experiment Domain

- `experiment_case`
- `workflow_instance`
- `workflow_stage_run`
- `experiment_snapshot`
- `task_event_log`

## 11.3 Candidate Domain

- `candidate_material`
- `active_site_template`
- `sulfur_intermediate_template`
- `experiment_configuration`

## 11.4 Chemistry Domain

- `molecular_structure`
- `adsorption_configuration`
- `integral_set_metadata`
- `fermionic_hamiltonian`
- `active_space_definition`

## 11.5 Quantum Domain

- `qubit_hamiltonian`
- `hf_initial_state`
- `ansatz_definition`
- `circuit_skeleton`
- `qasm_artifact`

## 11.6 Distributed Compilation Domain

- `partition_result`
- `mapping_result`
- `routing_result`
- `deploy_metric`

## 11.7 Evaluation Domain

- `simulation_run`
- `energy_result`
- `fidelity_check`
- `error_analysis`

## 11.8 Scoring Domain

- `gatekeeping_result`
- `chem_score`
- `deploy_score`
- `final_score`
- `recommendation_rank`

## 11.9 Presentation Domain

- `result_view`
- `chart_dataset`
- `report_artifact`
- `case_showcase_snapshot`

## 12. 存储架构设计

## 12.1 关系型数据库

建议使用 `PostgreSQL` 存储事务型元数据：

- 用户与权限
- 工作流实例
- 阶段状态
- 结果索引
- 排名与评分摘要

## 12.2 对象存储

建议使用对象存储保存大体量与中间工件：

- 原始分子结构文件
- 积分集文件
- 哈密顿量工件
- QASM 工件
- 编译结果包
- 报告文件

适用存储：

- MinIO
- S3 兼容对象存储

## 12.3 缓存与短期状态

建议使用 `Redis`：

- 任务运行中的热状态
- 会话缓存
- 结果缓存
- 前端展示层热点数据缓存

## 12.4 消息与任务系统

建议使用：

- `Kafka` 或 `RabbitMQ`

用于：

- 阶段任务下发
- 阶段完成事件上报
- 重试与死信处理
- 任务追踪与事件广播

## 12.5 检索与审计

可选引入：

- `OpenSearch / Elasticsearch`

用于：

- 工作流日志检索
- 任务事件检索
- 审计查询

## 13. 数据模型建议

## 13.1 工作流实例模型

```text
workflow_instance
- workflow_id
- case_id
- initiator_user_id
- current_stage
- overall_status
- created_at
- updated_at
- started_at
- finished_at
- priority
- input_snapshot_ref
- result_view_ref
```

## 13.2 阶段运行模型

```text
workflow_stage_run
- stage_run_id
- workflow_id
- stage_name
- stage_status
- attempt_no
- service_name
- input_ref
- output_ref
- error_code
- error_message
- started_at
- finished_at
```

## 13.3 结果聚合视图模型

```text
result_view
- workflow_id
- case_id
- recommended_candidate
- chem_score
- deploy_score
- final_score
- rank
- explanation_json
- chart_bundle_ref
- artifact_bundle_ref
```

## 13.4 评分模型

```text
score_bundle
- workflow_id
- gatekeeping_passed
- chem_score
- deploy_score
- final_score
- ads_score
- rxn_score
- stab_score
- fidelity_score
- comm_score
- depth_score
- eff_score
```

## 14. 统一对外 API 设计原则

前端不应分别调用化学服务、量子服务、编译服务和评分服务。对前端统一暴露的平台接口应由 `API Gateway + Platform Orchestrator + Result Aggregation Service` 共同形成。

建议对前端暴露以下 API 组：

### 14.1 展示层 API

- 获取项目预置案例列表
- 获取项目总览数据
- 获取流程链说明数据
- 获取推荐结果榜单
- 获取系统架构展示数据
- 获取技术亮点数据

### 14.2 工作台 API

- 创建实验任务
- 获取工作流实例状态
- 获取阶段状态详情
- 获取工作台摘要结果
- 获取分区结果视图
- 获取映射结果视图
- 获取综合评分视图

### 14.3 能力页 API

- 上传线路工件
- 触发分区计算
- 获取分区阶段结果
- 触发拓扑映射
- 获取映射分析结果
- 获取任务历史
- 获取报告导出链接

### 14.4 身份与辅助 API

- 登录/注册/登出
- 用户信息
- AI 助手会话

## 15. 失败、重试与补偿设计

统一编排中心必须管理全局失败，而不是由下游服务自由失败后返回简单错误。

### 15.1 失败类型

- 输入校验失败
- 阶段执行超时
- 下游服务不可用
- 中间工件缺失
- 结果不满足门控约束
- 结果校验失败

### 15.2 重试策略

- 幂等阶段允许自动重试
- 重试次数配置化
- 重试之间采用指数退避
- 超过次数进入 `failed` 或 `partial_completed`

### 15.3 补偿策略

- 非关键工件失败时允许降级展示
- 编译完成但模拟失败时允许保留编译结果并标记 `partial_completed`
- 评分失败不得伪造综合推荐结果

## 16. 安全设计

## 16.1 认证与授权

- 使用统一身份服务
- 能力层接口必须鉴权
- 展示层接口默认只读
- 管理与导出接口需更细粒度权限

## 16.2 数据安全

- 中间工件访问需签名或受限下载
- 服务间通信需启用服务身份认证
- 任务输入与结果输出要有审计痕迹

## 16.3 多租户与隔离

即使当前比赛版本不做严格多租户，也应保证：

- 用户数据逻辑隔离
- 工作流实例归属清晰
- 报告与工件访问受用户范围控制

## 17. 可观测性设计

## 17.1 指标

至少采集以下指标：

- 工作流创建数
- 各阶段平均耗时
- 各服务成功率/失败率
- 重试次数
- 阶段超时次数
- 推荐结果产出率

## 17.2 日志

日志必须具备：

- workflow_id
- stage_name
- service_name
- request_id
- user_id

## 17.3 链路追踪

建议采用分布式追踪：

- 将一次实验任务贯穿为一条 trace
- 服务间传播 trace_id

## 18. 基础设施建议

建议目标平台基础设施如下：

- API Gateway：Kong / APISIX / Nginx Gateway
- 编排中心：独立服务，自带状态机与任务管理
- 服务容器化：Docker
- 编排部署：Kubernetes
- 关系数据库：PostgreSQL
- 缓存：Redis
- 消息系统：Kafka 或 RabbitMQ
- 对象存储：MinIO / S3
- 监控：Prometheus + Grafana
- 日志：Loki / ELK
- 链路追踪：OpenTelemetry + Tempo / Jaeger

## 19. 当前系统到目标平台的映射

现有代码中的能力可映射为目标平台的早期原型：

- `backend/routers/auth.py` -> `User/Auth Service`
- `backend/routers/circuit.py` -> `Quantum Problem Service` 的输入工件入口雏形
- `backend/routers/partitioning.py` -> `Distributed Compiler Service` 的分区求解接口雏形
- `backend/routers/mapping.py` -> `Distributed Compiler Service` 的映射分析接口雏形
- `backend/routers/history.py` -> `Workflow Metadata Service` 的历史查询雏形
- `backend/routers/export.py` -> `Report & Visualization Service` 的导出接口雏形
- `backend/services/task_manager.py` -> 未来统一任务执行框架的早期简化版
- `backend/services/cache.py` -> 热状态缓存的简化版

### 结论

当前系统可被视为目标平台中“分布式编译子域 + 基础用户能力”的早期局部实现，而不是最终平台架构本身。

## 20. 实施建议

虽然本文档定义的是目标微服务平台，但研发时建议按能力域逐步落地：

### 阶段 1：统一编排中心原型

- 建立工作流实例模型
- 建立阶段状态机
- 将现有分区与映射任务纳入编排框架

### 阶段 2：结果聚合与展示契约

- 建立统一结果视图
- 为前端展示层提供稳定输出结构

### 阶段 3：候选与案例域

- 接入候选材料管理
- 接入预置案例与配置模板

### 阶段 4：化学建模与量子问题域

- 接入化学微模型
- 接入量子问题构造
- 打通编排链路

### 阶段 5：模拟执行与评分域

- 引入模拟评估服务
- 引入综合评分服务
- 打通推荐输出闭环

## 21. 非目标

本次后端架构设计不以以下内容为目标：

- 不要求一次性实现所有微服务
- 不要求当前代码立刻拆分部署到完整 K8s 集群
- 不要求本文档定义具体算法细节
- 不要求前端直接接入每个领域服务

## 22. 验收标准

目标平台后端设计应满足以下验收标准：

- 能清晰回答“平台由哪些服务组成，每个服务负责什么”
- 能清晰回答“一个实验任务如何从输入走到推荐输出”
- 能清晰回答“前端为什么不需要直接理解化学、量子、编译服务细节”
- 能清晰回答“现有系统能力在目标平台中的位置”
- 能为后续开发提供明确的服务拆分与边界指导

## 23. 对开发人员的明确要求

- 任何新服务设计不得绕开统一编排中心私自承担全流程控制
- 领域服务不得向前端直接暴露内部实现细节
- 工作流状态、阶段日志和中间工件引用必须可追踪
- 不得继续用单个任务表 JSON 字段无限堆积所有结果
- 所有服务接口都必须围绕平台边界设计，而不是围绕单页前端便利性设计

## 24. 结论

“量智硫光”后端目标平台的核心，不是把现有 FastAPI 单体继续扩大，而是围绕统一编排中心，组织多个专业领域服务形成一条完整、可追踪、可扩展的科研计算链。

这个平台的本质变化是：

- 从单体算法接口集合，转为统一编排的微服务平台
- 从页面驱动任务，转为工作流驱动任务
- 从结果零散存储，转为按领域和工件分层存储
- 从分布式编译单点能力，转为材料筛选全链路后端系统

后续开发应围绕这些变化推进，而不是仅在现有后端基础上继续堆砌路由与任务逻辑。
