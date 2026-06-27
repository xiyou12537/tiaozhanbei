# 量智硫光后端平台原型实施设计

> 基于现有 FastAPI 项目，在单体部署形态下完成面向目标平台架构的后端重构与扩展设计。实现目标是形成一个可运行、可扩展、接近生产的后端原型，而不是继续堆叠算法接口。

## 1. 目标

本设计用于指导“量智硫光”后端从当前的量子线路划分工具型单体，演进为具备统一编排、阶段状态机、领域服务边界、异步任务执行、结果聚合和基础设施分层的科研计算平台原型。

本次实施目标明确如下：

- 保持单体 FastAPI 应用形态，避免本轮直接拆分为多服务部署
- 在代码结构上按微服务边界组织模块，确保后续可拆分
- 引入 PostgreSQL、Redis、RabbitMQ 作为正式基础设施
- 以统一编排中心为核心，串联候选材料、化学建模、量子问题、分布式编译、模拟评估、综合评分和结果聚合
- 重构现有接口，以目标平台 API 为准，不保留旧接口兼容性约束

## 2. 非目标

本次实施不包含以下目标：

- 不在本轮内拆分成独立部署的微服务集群
- 不要求一次性接入所有外部量化化学求解器或生产级 HPC 能力
- 不实现完整的 Kubernetes、APISIX、OpenTelemetry 生产部署体系
- 不围绕旧前端兼容保留现有 `/api/partition/*`、`/api/mapping/*` 接口契约

## 3. 现状问题

当前后端具备用户认证、QASM 上传、分区计算、拓扑映射、历史记录和导出能力，但存在以下结构问题：

- 路由层直接调用算法逻辑，缺乏平台级编排边界
- 任务管理依赖进程内线程池，无法支撑可靠异步执行
- 数据模型以 `users / circuits / tasks / mappings` 为中心，无法承载长链路科研工作流
- 任务结果依赖 `result_json` 聚合，结果域边界缺失
- 任务失败、重试、补偿、阶段日志缺乏统一管理
- 前端看到的是底层能力接口集合，而不是统一任务视图

这些问题决定了本次实施必须从平台骨架开始，而不是继续增量堆叠路由。

## 4. 总体实施策略

本次实施采用如下策略：

### 4.1 单体内分层重构

保留一个 FastAPI 应用作为部署单元，但内部代码按照未来微服务边界组织：

- `api`：平台接口层
- `orchestrator`：统一编排中心
- `domain services`：候选、化学、量子、编译、评估、评分、聚合
- `workers`：异步阶段执行器
- `infrastructure`：数据库、缓存、消息队列、配置、日志

### 4.2 编排优先

首先落地统一工作流模型、阶段状态机、事件日志、异步任务投递与状态查询，再把各领域能力接入编排链路。

### 4.3 基础设施一次到位

本轮直接接入：

- PostgreSQL：事务型元数据存储
- Redis：热状态、进度、短期结果缓存
- RabbitMQ：阶段任务派发与执行解耦

选用 RabbitMQ 而非 Kafka，是因为当前平台仍处于单体原型阶段，任务编排和可靠消费是核心诉求，消息吞吐并非主矛盾。RabbitMQ 的复杂度更低，更适合本轮实现规模。

## 5. 架构设计

## 5.1 逻辑层次

### API Layer

职责：

- 接收前端请求
- 执行认证鉴权
- 调用编排入口或查询服务
- 返回统一任务视图、阶段详情、聚合结果

不负责：

- 直接执行长耗时算法
- 控制阶段流转
- 拼装跨域底层结果

### Orchestrator Layer

职责：

- 创建工作流实例
- 建立阶段运行记录
- 按状态机推进下游阶段
- 处理失败、重试、补偿和取消
- 写入事件日志
- 管理阶段输出引用

### Domain Services Layer

包括：

- Candidate Service
- Chemistry Modeling Service
- Quantum Problem Service
- Distributed Compiler Service
- Simulation & Evaluation Service
- Scoring Service
- Result Aggregation Service

原则：

- 每个服务只负责本域计算与数据输出
- 不直接操作全流程状态机
- 不向前端暴露内部中间结构

### Worker Layer

职责：

- 消费 RabbitMQ 中的阶段任务
- 调用对应领域服务
- 回写阶段输出、状态、事件和异常信息

### Infrastructure Layer

职责：

- PostgreSQL 会话和迁移
- Redis 客户端和缓存封装
- RabbitMQ 连接、发布与消费
- 应用配置
- 日志与可观测性扩展点

## 5.2 目录组织建议

建议将 `backend` 组织为如下结构：

```text
backend/
├── api/
│   ├── dependencies/
│   ├── routers/
│   └── schemas/
├── core/
│   ├── config.py
│   ├── enums.py
│   └── security.py
├── db/
│   ├── base.py
│   ├── models/
│   ├── repositories/
│   └── session.py
├── orchestrator/
│   ├── engine.py
│   ├── stage_machine.py
│   ├── dispatcher.py
│   └── progress.py
├── services/
│   ├── candidate/
│   ├── chemistry/
│   ├── quantum/
│   ├── compiler/
│   ├── evaluation/
│   ├── scoring/
│   └── aggregation/
├── workers/
│   ├── consumer.py
│   ├── handlers/
│   └── tasks.py
├── infrastructure/
│   ├── cache/
│   ├── messaging/
│   └── logging/
└── main.py
```

## 6. 核心数据模型

## 6.1 身份域

保留用户能力，但升级为平台基础域：

- `users`
- `sessions` 或令牌表
- 可扩展的 `roles`、`permissions`

本轮可先完成 `users` 和令牌认证，角色权限为预留扩展。

## 6.2 工作流域

### `workflow_instances`

用于表示一次完整实验任务。

关键字段：

- `workflow_id`
- `case_id`
- `initiator_user_id`
- `current_stage`
- `overall_status`
- `priority`
- `input_snapshot_ref`
- `result_view_ref`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

### `workflow_stage_runs`

用于记录各阶段的执行历史。

关键字段：

- `stage_run_id`
- `workflow_id`
- `stage_name`
- `stage_status`
- `attempt_no`
- `service_name`
- `input_ref`
- `output_ref`
- `error_code`
- `error_message`
- `started_at`
- `finished_at`

### `task_event_logs`

用于记录平台级操作事件。

事件示例：

- workflow_created
- stage_dispatched
- stage_started
- stage_succeeded
- stage_failed
- stage_retrying
- workflow_completed
- workflow_partial_completed
- workflow_cancelled

### `experiment_snapshots`

保存任务输入快照，避免运行过程依赖可变外部状态。

内容包括：

- 候选材料输入
- 活性位模板选择
- 实验配置
- 初始 QASM 或量子问题输入
- 用户提交参数

## 6.3 候选域

- `candidate_materials`
- `active_site_templates`
- `sulfur_intermediate_templates`
- `experiment_configurations`
- `experiment_cases`

这些表用于支撑真实案例选择和实验输入管理，而不是仅靠前端临时提交 JSON。

## 6.4 化学域

- `molecular_structures`
- `adsorption_configurations`
- `integral_set_metadata`
- `fermionic_hamiltonians`
- `active_space_definitions`

本轮不追求完整量化化学平台，但要保证中间结构和工件引用清晰可追踪。

## 6.5 量子域

- `qubit_hamiltonians`
- `hf_initial_states`
- `ansatz_definitions`
- `circuit_skeletons`
- `qasm_artifacts`

## 6.6 分布式编译域

- `partition_results`
- `mapping_results`
- `routing_results`
- `deploy_metrics`

## 6.7 评估域

- `simulation_runs`
- `energy_results`
- `fidelity_checks`
- `error_analyses`

## 6.8 评分域

- `gatekeeping_results`
- `score_bundles`
- `recommendation_ranks`

## 6.9 展示域

- `result_views`
- `chart_datasets`
- `report_artifacts`

## 7. 状态机设计

## 7.1 工作流主状态

工作流主状态采用以下集合：

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

### 状态推进顺序

```text
created
-> validated
-> screening
-> chem_modeling
-> quantum_encoding
-> distributed_compiling
-> simulation_evaluating
-> scoring
-> aggregating
-> completed
```

异常出口：

- 任一关键阶段不可恢复失败 -> `failed`
- 非关键阶段失败但可展示部分结果 -> `partial_completed`
- 人工终止 -> `cancelled`

## 7.2 阶段执行状态

每个阶段运行记录拥有独立状态：

- `pending`
- `running`
- `success`
- `failed`
- `retrying`
- `skipped`

主状态和阶段状态分离，是为了同时支持工作流总览和阶段级诊断。

## 8. 任务执行与消息流转

## 8.1 创建工作流

前端调用：

- `POST /api/platform/workflows`

执行流程：

1. API 校验用户和输入参数
2. 生成 `experiment_snapshot`
3. 创建 `workflow_instance`
4. 创建首批 `workflow_stage_run`
5. 写入 `workflow_created` 事件
6. 将首阶段任务投递到 RabbitMQ

## 8.2 阶段执行

Worker 从 RabbitMQ 拉取阶段任务后：

1. 将阶段状态更新为 `running`
2. 写入 `stage_started`
3. 调用对应领域服务
4. 写入领域结果表
5. 更新 `output_ref`
6. 标记阶段为 `success`
7. 由 Orchestrator 计算下一个阶段并继续派发

## 8.3 失败与重试

当阶段执行异常时：

1. 记录异常类型与错误码
2. 标记阶段为 `failed`
3. 判断是否允许自动重试
4. 如果允许则更新为 `retrying` 并重新投递
5. 如果超过阈值，更新工作流为 `failed` 或 `partial_completed`

## 8.4 Redis 热状态

Redis 保存短期热数据：

- 工作流当前阶段
- 工作流进度百分比
- 最近阶段摘要
- API 高频读取的统一状态视图缓存

Redis 不是事实来源。事实来源仍为 PostgreSQL。

## 9. 统一 API 设计

## 9.1 工作流接口

- `POST /api/platform/workflows`
  创建实验任务
- `GET /api/platform/workflows/{workflow_id}`
  获取统一任务状态视图
- `GET /api/platform/workflows/{workflow_id}/stages`
  获取阶段详情
- `GET /api/platform/workflows/{workflow_id}/events`
  获取事件日志
- `POST /api/platform/workflows/{workflow_id}/cancel`
  取消任务

## 9.2 结果接口

- `GET /api/platform/workflows/{workflow_id}/result`
  获取统一聚合结果
- `GET /api/platform/workflows/{workflow_id}/summary`
  获取工作台摘要
- `GET /api/platform/workflows/{workflow_id}/artifacts`
  获取工件索引

## 9.3 基础数据接口

- `GET /api/platform/cases`
- `GET /api/platform/candidates`
- `GET /api/platform/configurations`

## 9.4 身份接口

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`

身份接口可保留路径风格，但内部实现升级到新数据和依赖结构。

## 10. 各领域服务实现策略

## 10.1 Candidate Service

真实实现范围：

- 候选材料实体管理
- 活性位模板管理
- 中间体模板管理
- 实验配置模板管理
- 预置案例管理

输出：

- 标准化任务输入上下文

## 10.2 Chemistry Modeling Service

本轮采用工程化真实实现：

- 根据候选材料和活性位模板构建微模型描述
- 生成吸附构型候选
- 生成活性空间定义
- 形成后续量子问题所需的结构化输入

不在本轮实现完整从头量化化学求解，但保留积分集、费米子哈密顿量元数据结构。

## 10.3 Quantum Problem Service

实现内容：

- 从化学阶段输出构建 qubit Hamiltonian
- 生成 Hartree-Fock 初态描述
- 生成 Ansatz 定义
- 生成 circuit skeleton
- 导出 QASM artifact

## 10.4 Distributed Compiler Service

本域将复用并正式承接现有 `quantum_partitioning` 能力：

- 分区计算
- 拓扑映射
- 路由统计
- 部署指标统计

但调用方式必须从“router 直接调用算法”改为“领域服务被 worker 调用”。

## 10.5 Simulation & Evaluation Service

本轮实现：

- 线路模拟执行
- 编译前后基础一致性校验
- fidelity 统计
- error 分析
- 能量结果记录

## 10.6 Scoring Service

本轮实现真实但简化的规则化评分模型：

- gatekeeping 规则
- ChemScore
- DeployScore
- FinalScore
- recommendation rank

评分必须保留可解释字段，避免黑盒输出。

## 10.7 Result Aggregation Service

负责：

- 汇总各阶段输出
- 生成统一工作台结果视图
- 生成图表数据
- 生成报告工件引用

前端最终读取的是 `result_view`，不是底层域表的拼装结果。

## 11. 错误处理与补偿

统一编排中心负责处理全局失败。

### 输入校验失败

- 不进入执行队列
- 工作流直接标记为 `failed`

### 幂等阶段失败

- 自动重试
- 使用指数退避
- 重试次数配置化

### 非关键阶段失败

- 如果已有可展示结果，则进入 `partial_completed`
- 保留成功阶段产物

### 评分失败

- 不生成伪造综合推荐
- 仅返回上游真实阶段产物和错误描述

## 12. 基础设施设计

## 12.1 PostgreSQL

用于保存：

- 身份数据
- 工作流元数据
- 阶段记录
- 事件日志
- 分域结果索引
- 聚合结果视图

## 12.2 Redis

用于保存：

- 热状态
- 任务进度
- 短时缓存
- 高频查询摘要

## 12.3 RabbitMQ

用于：

- 阶段任务发布
- 消费者执行解耦
- 重试与重新投递

建议按阶段或统一工作流任务主题组织队列，并在消息体中明确：

- `workflow_id`
- `stage_name`
- `attempt_no`
- `trace_id`

## 13. 测试策略

开发采用 TDD。

至少覆盖以下测试层：

- 状态机单元测试
- Orchestrator 服务测试
- RabbitMQ 消息派发和消费适配测试
- Redis 状态缓存测试
- 各领域服务核心行为测试
- API 集成测试
- 端到端工作流测试
- 失败、重试、补偿路径测试

## 14. 交付拆分

为保证实现可控，整体开发分为三个子项目：

### 子项目 1：平台骨架

- 新基础设施接入
- 新数据库模型
- 统一编排中心
- 工作流状态机
- 事件日志
- 统一任务接口

### 子项目 2：领域执行链

- Candidate
- Chemistry Modeling
- Quantum Problem
- Distributed Compiler
- Simulation & Evaluation
- Scoring

### 子项目 3：结果与交付层

- Result Aggregation
- 工作台摘要与结果查询
- 报告导出
- 工件索引
- 可观测性扩展点

## 15. 验收标准

本次实施完成后，应满足：

- 后端不再依赖进程内线程池作为核心任务机制
- 前端通过统一工作流接口驱动任务和读取结果
- 工作流状态、阶段记录、事件日志可追踪
- 分域结果不再堆积在单个 JSON 结果字段中
- 现有分区和映射能力已被纳入正式编译服务链路
- 平台具备从创建任务到返回统一结果视图的完整闭环

## 16. 结论

本设计的核心，不是扩展旧的量子线路分区 API，而是在单体部署约束下，先建立一个按目标平台架构组织的后端原型。该原型以统一编排中心为核心，使用 PostgreSQL、Redis、RabbitMQ 提供稳定的元数据、热状态和异步任务基础设施，并将各领域能力纳入统一工作流和结果视图。

这条路线兼顾了当前仓库现实、目标平台约束和后续可拆分性，是本项目当前阶段的最优实施路径。
