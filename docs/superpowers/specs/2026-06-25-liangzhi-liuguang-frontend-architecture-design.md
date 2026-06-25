# 量智硫光前端架构设计说明

> 面向开发交付的前端设计文档。本文档用于指导“量智硫光”项目的前端重构与新增开发，目标是将现有“量子线路划分优化系统”升级为适合比赛展示、答辩讲解与产品化表达的前端平台。

## 1. 文档目的

本文档定义“量智硫光”前端的目标定位、信息架构、页面结构、状态模型、模块拆分、接口协作边界、视觉方向与实施顺序。开发人员应以本文档为基准完成前端重构与新增页面开发。

本文档不是产品方案书的重复整理，而是将现有产品叙事转译为可落地的前端架构说明。

## 2. 项目背景

当前项目代码库的前端基础是一个基于 Vue 3 + Element Plus + Vite 的“量子线路划分优化系统”，已有能力集中在：

- QASM 电路上传与解析
- 电路分区计算
- 芯片拓扑映射
- 历史记录查询
- AI 助手问答

当前前端更接近“算法工具台”，而不是“面向评委展示的完整平台”。其主要问题如下：

- 首页叙事仍围绕“量子线路划分”，与“量智硫光”项目主叙事不一致
- 登录后主导航直接暴露分区、映射等能力页，缺少项目级总览入口
- 业务链路没有被完整展示，页面之间缺少统一上下文
- 页面职责过重，页面内部混合了表单、轮询、数据转换和图渲染逻辑
- 共享状态采用 `provide/inject` 临时组织，难以支撑扩展后的展示层与工作台层

## 3. 前端目标定位

前端的定位不是“现场从头完整操作的实验系统”，而是“配合 PPT 的可视化展示平台 + 可深入演示的能力工作台”。

前端必须同时满足以下目标：

- 页面视觉足够精美，适合答辩投屏展示
- 项目流程表达完整，能讲清从候选材料到综合推荐的全链路
- 可快速向评委解释“为什么这个项目成立”
- 可在需要时进入底层能力页，证明已有分布式量子编译系统真实存在且可运行
- 首页可免登录进入，避免展示时被认证流程阻断
- 深层能力页仍保留登录访问，保持产品完整度

## 4. 设计原则

### 4.1 产品表达原则

- 先讲“项目”，再讲“工具”
- 先讲“价值链路”，再讲“算法细节”
- 先讲“综合推荐结果”，再讲“底层分区映射能力”

### 4.2 架构原则

- 展示层与能力层分离
- 页面负责展示，逻辑下沉到 composables 与 services
- 数据状态按领域划分，不再由单个页面或布局层临时托管
- 图表组件和网络图组件只消费标准化数据，不直接依赖后端原始返回格式

### 4.3 实施原则

- 最大化复用现有 Vue 技术栈和已完成页面能力
- 不推倒重写现有分区/映射逻辑，采用“外层重组 + 内层提纯”的方式演进
- 优先完成“展示层闭环”，再推进“底层能力页重构”

## 5. 总体架构

前端采用“两层产品结构”：

1. 展示层（免登录访问）
2. 能力层（登录后访问）

### 5.1 展示层

展示层用于建立项目认知，服务于评委、老师和答辩观众，核心目标是“看懂项目全貌”。

展示层页面包括：

- 项目首页
- 项目总览
- 筛选流程
- 综合结果
- 系统架构
- 技术亮点

### 5.2 能力层

能力层用于展示底层技术能力，服务于需要进一步验证系统可行性的场景，核心目标是“证明系统真的能做这些事”。

能力层页面包括：

- 核心工作台
- 分区编译页
- 芯片映射页
- 历史记录页
- AI 助手页

## 6. 目标信息架构

### 6.1 导航层级

#### 一级导航：展示层

- 首页
- 项目总览
- 筛选流程
- 综合结果
- 系统架构
- 技术亮点
- 进入工作台

#### 一级导航：能力层

- 核心工作台
- 分区编译
- 芯片映射
- 历史记录
- AI 助手

### 6.2 路由设计

建议路由结构如下：

```text
/
/overview
/workflow
/results
/architecture
/highlights
/app
/app/workbench
/app/partition
/app/mapping
/app/history
/app/chat
```

### 6.3 登录策略

采用“首页免登录，能力层登录”的访问策略：

- 所有展示层路由可匿名访问
- `/app` 及其子路由需要登录
- 未登录访问 `/app/**` 时统一跳转到首页并唤起登录弹窗
- 登录成功后优先回跳原目标地址

## 7. 页面规划

## 7.1 项目首页 `/`

### 页面定位

项目入口页，不再是“量子线路划分工具 Landing Page”，而是“量智硫光”品牌首页。

### 页面目标

- 建立项目第一印象
- 清楚表达项目名称、场景、价值
- 提供简洁导航进入总览、流程、结果、系统架构
- 提供进入工作台入口

### 页面结构

- Hero 区
- 项目价值摘要
- 三段式技术路线简介
- 核心结果预览
- 系统能力预览
- 底部导航与入口区

### 需要替换的现有内容

现有 [HomePage.vue](C:/Users/15750/Desktop/分布式大系统/frontend/src/views/HomePage.vue) 中关于“上传 QASM、电路分区、芯片映射”的工具型文案应整体重写，仅保留部分视觉语言与动画结构。

## 7.2 项目总览 `/overview`

### 页面定位

项目解释页，用于讲清问题、目标、技术路线和创新点。

### 页面结构

- 项目背景与问题定义
- 项目目标
- 核心创新点
- 技术路线总览
- 平台闭环说明

### 页面内容来源

主要来自项目方案书的第 2 至第 6 章。

## 7.3 筛选流程 `/workflow`

### 页面定位

展示“从候选材料到综合推荐”的完整流程链。

### 页面结构

- 全链路流程图
- 每一步的输入/处理/输出说明
- 化学到量子的转换说明
- 分布式编译在链路中的角色说明

### 页面表现方式

建议采用纵向叙事 + 横向阶段卡结合的方式，避免纯流程图堆砌。

## 7.4 综合结果 `/results`

### 页面定位

展示项目输出结果，而不是展示算法操作过程。

### 页面结构

- 推荐候选榜单
- ChemScore / DeployScore / FinalScore 对比
- 指标雷达图或条形图
- 推荐逻辑解释区
- 案例切换区

### 数据策略

该页面允许优先使用预置演示数据，不依赖现场重新跑任务。

## 7.5 系统架构 `/architecture`

### 页面定位

用于解释平台分层与模块协同关系。

### 页面结构

- 五层架构图
- 模块职责说明
- 数据流说明
- 前端与后端的职责边界

## 7.6 技术亮点 `/highlights`

### 页面定位

凝练展示项目特色，用于答辩中的“优势总结”。

### 页面结构

- 场景创新
- 架构创新
- 工程创新
- 评价创新
- 现有能力复用点

## 7.7 核心工作台 `/app/workbench`

### 页面定位

能力层的中枢页，用于把项目业务链与底层能力统一起来。

### 页面目标

- 作为登录后第一页面
- 不要求用户现场从头操作
- 用统一视图承接当前案例、流程状态、结果摘要和能力入口

### 页面结构

#### 顶部项目摘要区

- 当前案例名称
- 当前阶段状态
- 推荐结论
- 综合评分
- 快速入口按钮

#### 中部流程链区

按阶段展示：

- 候选材料
- 活性位微模型
- 化学问题建模
- 量子线路生成
- 分布式编译
- 映射部署
- 综合评分

每一步展示：

- 输入对象
- 状态标签
- 关键指标
- 详情跳转

#### 底部结果区

- 分区指标摘要
- 映射指标摘要
- 综合评分摘要
- 图表卡片

#### 侧边能力入口区

- 进入分区编译页
- 进入芯片映射页
- 查看历史记录
- 打开 AI 助手

## 7.8 分区编译页 `/app/partition`

### 页面定位

底层技术能力页，展示分区求解过程与结果细节。

### 改造方向

保留现有 [PartitionPage.vue](C:/Users/15750/Desktop/分布式大系统/frontend/src/views/PartitionPage.vue) 的核心能力，但将其定位从“主业务页”改为“技术明细页”。

### 需要调整的内容

- 页面标题、说明文案改为“分布式编译能力”
- 增加与项目案例的关联说明
- 上传、参数、结果、图可视化结构保留
- 页面逻辑下沉，减少页面脚本体量

## 7.9 芯片映射页 `/app/mapping`

### 页面定位

展示拓扑设计、映射求解和部署代价分析。

### 改造方向

保留现有 [MappingPage.vue](C:/Users/15750/Desktop/分布式大系统/frontend/src/views/MappingPage.vue) 核心结构，但增强其作为“部署分析页”的定位。

### 需要调整的内容

- 页面顶部加入与当前案例、当前分区任务的关联信息
- 映射结果区加入“部署可执行性”解释区
- 一键拓扑对比图表与综合评分结果建立关联

## 7.10 历史记录页 `/app/history`

### 页面定位

用于展示系统具备任务留痕、结果回溯和能力沉淀。

### 改造方向

在现有 [HistoryPage.vue](C:/Users/15750/Desktop/分布式大系统/frontend/src/views/HistoryPage.vue) 基础上保留时间线结构，但建议增加：

- 任务类型标签
- 所属案例标签
- 结果摘要卡
- 跳回工作台或能力页入口

## 7.11 AI 助手页 `/app/chat`

### 页面定位

作为辅助说明能力存在，不作为主舞台。

### 改造方向

保留现有 [ChatPage.vue](C:/Users/15750/Desktop/分布式大系统/frontend/src/views/ChatPage.vue) 和 [useChat.js](C:/Users/15750/Desktop/分布式大系统/frontend/src/composables/useChat.js)，但在导航与文案上强调“解释型助手”，弱化其主功能地位。

## 8. 前端状态架构

现有的 `Layout provide/inject shared` 方式不再适合作为全局主状态组织方案。建议按领域拆分状态。

### 8.1 `auth context`

负责：

- token 管理
- 用户信息管理
- 登录态判断
- 登录后回跳
- 登出处理

建议抽离为：

```text
src/composables/useAuth.js
src/services/authStorage.js
```

### 8.2 `showcase context`

负责展示层状态：

- 当前展示案例
- 当前高亮流程步骤
- 预置图表数据
- 推荐候选
- 展示层使用的静态或半静态结果

建议抽离为：

```text
src/composables/useShowcase.js
src/data/showcase/
```

### 8.3 `workflow context`

负责能力层主业务状态：

- 当前电路
- 当前任务 ID
- 当前分区结果
- 当前映射结果
- 当前评分结果
- 图渲染所需派生数据
- 当前工作台激活步骤

建议抽离为：

```text
src/composables/useWorkflow.js
src/services/workflowService.js
src/services/workflowMappers.js
```

### 8.4 `assistant context`

负责聊天消息单例状态。现有做法可以保留，但文件位置和命名应更清晰。

## 9. 模块拆分设计

## 9.1 目录建议

建议将前端目录演进为：

```text
frontend/src/
  api/
    authApi.js
    circuitApi.js
    partitionApi.js
    mappingApi.js
    historyApi.js
    chatApi.js
    index.js
  composables/
    useAuth.js
    useShowcase.js
    useWorkflow.js
    useChat.js
  services/
    authStorage.js
    partitionPolling.js
    workflowService.js
    workflowMappers.js
  data/
    showcase/
      overview.js
      workflow.js
      results.js
  layouts/
    PublicLayout.vue
    AppLayout.vue
  views/
    showcase/
      HomePage.vue
      OverviewPage.vue
      WorkflowPage.vue
      ResultsPage.vue
      ArchitecturePage.vue
      HighlightsPage.vue
    app/
      WorkbenchPage.vue
      PartitionPage.vue
      MappingPage.vue
      HistoryPage.vue
      ChatPage.vue
  components/
    common/
    showcase/
    workbench/
    partition/
    mapping/
    charts/
    graphs/
```

## 9.2 页面职责边界

### 页面层

只负责：

- 组织页面布局
- 响应用户交互
- 调用 composable 提供的方法
- 传递标准化数据到子组件

### composable 层

负责：

- 聚合页面需要的状态
- 对页面暴露可直接消费的数据结构
- 编排服务调用流程

### service 层

负责：

- 调后端 API
- 执行轮询
- 处理数据标准化
- 生成页面无关的业务派生数据

### visualization 组件层

负责：

- 图表绘制
- 网络图绘制
- 结果卡展示

不得在组件内部直接请求后端接口。

## 10. 现有代码重构建议

## 10.1 路由

现有 [router.js](C:/Users/15750/Desktop/分布式大系统/frontend/src/router.js) 需要重构为展示层与能力层双布局结构。

建议：

- 抽出 `PublicLayout`
- 将展示层页面挂载到 `PublicLayout`
- 将能力层页面挂载到 `AppLayout`
- 路由守卫仅拦截 `/app/**`

## 10.2 布局

现有 [Layout.vue](C:/Users/15750/Desktop/分布式大系统/frontend/src/views/Layout.vue) 应迁移到 `layouts/AppLayout.vue`，并进行如下改造：

- 从“单纯功能导航”升级为“工作台导航 + 用户区 + 全局状态入口”
- 去除在布局层维护具体业务结果对象的做法
- 将布局层变成上下文容器，而不是状态仓库

## 10.3 API 层

现有 [api.js](C:/Users/15750/Desktop/分布式大系统/frontend/src/api.js) 职责过重，应按领域拆分。

拆分目标：

- 每个文件只面向一个业务领域
- `index.js` 仅负责复用 axios 实例
- 页面不再从单文件中混取所有接口

## 10.4 分区页

[PartitionPage.vue](C:/Users/15750/Desktop/分布式大系统/frontend/src/views/PartitionPage.vue) 应拆出：

- 上传逻辑 composable
- 分区任务轮询 service
- 图渲染组件
- 参数表单组件
- 结果摘要组件

## 10.5 映射页

[MappingPage.vue](C:/Users/15750/Desktop/分布式大系统/frontend/src/views/MappingPage.vue) 应拆出：

- 拓扑设计组件
- 拓扑预览图组件
- 映射结果组件
- 对比图表组件
- 映射 service

## 10.6 聊天模块

现有 [useChat.js](C:/Users/15750/Desktop/分布式大系统/frontend/src/composables/useChat.js) 可以保留单例模式，但建议：

- 明确其为独立子系统
- 不参与工作台主流程状态
- 不在工作台层共享其消息对象

## 11. 数据模型建议

前端内部建议形成统一的数据视图模型，避免页面直接依赖后端原始结构。

### 11.1 工作台案例模型

```ts
type ShowcaseCase = {
  id: string
  name: string
  scenario: string
  candidateCount: number
  status: 'idle' | 'running' | 'completed'
  recommendedCandidate?: string
  chemScore?: number
  deployScore?: number
  finalScore?: number
}
```

### 11.2 工作流步骤模型

```ts
type WorkflowStep = {
  key: string
  title: string
  status: 'pending' | 'active' | 'completed'
  summary: string
  metrics?: Array<{ label: string; value: string | number }>
  targetRoute?: string
}
```

### 11.3 分区结果视图模型

```ts
type PartitionViewModel = {
  taskId: string
  partitionCount: number
  teleportations: number
  globalGates: number
  elapsedSeconds: number
  partitions: Array<{
    id: string
    size: number
    qubits: number[]
  }>
  edgeCosts: Record<string, number>
}
```

### 11.4 映射结果视图模型

```ts
type MappingViewModel = {
  valid: boolean
  totalEprCost: number
  subgraphCost: number
  mappingPairs: Array<{
    chipId: string
    partitionId: string
  }>
  topologyEdges: Array<{
    source: number
    target: number
  }>
}
```

### 11.5 综合评分模型

```ts
type ScoreViewModel = {
  chemScore: number
  deployScore: number
  finalScore: number
  rank: number
  explanation: string[]
}
```

## 12. 前后端协作边界

前端不负责真实化学求解，仅负责：

- 展示链路
- 承接已有量子编译与映射结果
- 展示预置案例与综合结果
- 对后端结果进行页面级解释

### 12.1 前端可直接复用的现有接口

- `/api/auth/*`
- `/api/circuit/upload`
- `/api/partition/run`
- `/api/partition/status/{task_id}`
- `/api/partition/result/{task_id}`
- `/api/mapping/find`
- `/api/mapping/compare`
- `/api/export/graph-data/{task_id}`
- `/api/user/history`
- `/api/chat/*`

### 12.2 前端为展示层建议新增或约定的接口

如果希望展示层不完全依赖静态前端数据，建议后端后续补充：

- 预置案例列表接口
- 综合评分结果接口
- 推荐候选详情接口
- 展示层图表数据接口

在这些接口未实现前，展示层可先基于本地 `showcase data` 开发。

## 13. 视觉设计方向

## 13.1 总体风格

前端不应延续典型后台管理台风格，应采用“研究展示平台”视觉方向。

建议风格：

- 深色背景与亮色强调相结合
- 大标题、大留白、强层次
- 卡片化但不过度工具化
- 图形、流程线、数据卡共同构成展示感

## 13.2 展示层视觉关键词

- 未来感
- 精密感
- 可信赖
- 科研平台感

## 13.3 能力层视觉关键词

- 清晰
- 专业
- 可读
- 稳定

## 13.4 设计注意事项

- 展示层与能力层应保持同一品牌语言，但密度不同
- 首页与总览页更偏叙事
- 工作台与能力页更偏结构化信息展示
- 图表颜色需与品牌主色统一，不应使用杂乱默认配色

## 14. 非目标

本次前端重构不以以下事项为目标：

- 不在前端实现真实化学建模逻辑
- 不要求现场从零手动走完全链路
- 不在本次范围内引入全新 UI 框架
- 不要求一次性重写所有现有逻辑

## 15. 实施顺序建议

建议按以下顺序实施：

### 阶段 1：展示层搭建

- 重构路由
- 重写首页
- 新增总览、流程、结果、架构、亮点页
- 打通免登录访问

### 阶段 2：能力层壳体重构

- 重构 AppLayout
- 新增 WorkbenchPage
- 调整导航层级
- 接入 auth context

### 阶段 3：分区与映射页提纯

- 拆分页面逻辑
- 抽离 service 与 composable
- 提取图表组件和图网络组件

### 阶段 4：工作台整合

- 将分区、映射、结果摘要统一接入工作台
- 增加评分视图与阶段卡
- 增加展示案例切换

### 阶段 5：历史与 AI 页面收尾

- 历史记录页升级
- AI 助手定位弱化并统一样式

## 16. 验收标准

前端重构完成后，应满足以下验收条件：

- 评委从首页进入后，能够在 3 分钟内理解项目做什么、怎么做、输出什么
- 展示层能够完整表达“经典粗筛 + 分布式量子精修 + 综合评分推荐”的闭环
- 登录后能够进入统一工作台，而不是直接面对孤立算法页
- 分区页和映射页仍能保留现有核心能力
- 页面状态不再依赖 `Layout provide/inject shared` 直接跨页传递
- API 调用、任务轮询、数据映射从页面中下沉
- 视觉风格统一，展示层与能力层保持同一品牌语言

## 17. 对开发人员的明确要求

- 优先遵守本文档的信息架构，不得把新增展示层继续做成工具型页面拼接
- 重构时优先保留现有可用算法能力，不得为了改视觉破坏现有分区映射功能
- 页面开发时必须拆分 composable、service 和 visualization component，不允许继续把整套逻辑堆在单页脚本中
- 所有新页面必须适配桌面答辩投屏场景，同时兼容基本移动端浏览
- 展示层开发可先使用静态示例数据，但结构必须可替换为后端真实数据

## 18. 结论

本次前端重构的核心，不是把现有页面“换个皮肤”，而是把项目从“量子线路划分工具”升级为“量智硫光展示平台”。

其本质变化是：

- 从功能导向，转为项目叙事导向
- 从单点算法页面，转为展示层与能力层双层结构
- 从页面各自为战，转为工作台统一组织
- 从页面内耦合逻辑，转为按领域拆分状态与服务

开发应围绕这四个变化展开，避免只做视觉替换而不调整产品结构。
