export const heroStats = [
  { label: '工作流阶段', value: '7', note: '覆盖候选筛选、化学建模、量子编码到结果聚合的完整链路' },
  { label: '联调模式', value: 'queued', note: '支持异步推进、阶段轮询、事件日志与最终结果汇总' },
  { label: '结果视图', value: '1', note: '统一输出 Summary、Scientific Snapshot 与 Artifacts' },
]

export const homeValueCards = [
  {
    title: '问题背景',
    text: '锂硫电池催化材料筛选横跨化学建模、量子问题构造与部署评估，传统展示方式难以把整条价值链讲清楚。',
  },
  {
    title: '平台目标',
    text: '把候选筛选、分布式量子编译、结果汇总和历史留痕组织进同一平台，让项目既能答辩展示，也能真实联调。',
  },
  {
    title: '落地方式',
    text: '展示层负责讲清项目背景、流程与结果，能力层负责证明系统已具备工作流编排、分区编译、映射分析与任务回溯能力。',
  },
]

export const homeCapabilityCards = [
  {
    title: '创建筛选工作流',
    text: '选择案例、候选材料和执行模式，直接发起平台工作流。',
    meta: 'workflow launch',
  },
  {
    title: '查看编译结果',
    text: '进入分布式编译能力页，查看电路分区、芯片映射和部署代价分析。',
    meta: 'partition / mapping',
  },
  {
    title: '查看综合评分',
    text: '统一查看 FinalScore、科学指标、拓扑信息和结果工件。',
    meta: 'scores / result view',
  },
  {
    title: '使用 AI 助手',
    text: '通过解释型助手追问概念、结果和能力细节，系统页中可继续保留历史会话。',
    meta: 'assistant / explanation',
  },
]

export const overviewCards = [
  {
    title: '项目背景',
    text: '锂硫电池体系中的候选催化材料存在搜索空间大、实验成本高、评价链路长的问题，需要一套可复用的数字化筛选路径。',
  },
  {
    title: '问题定义',
    text: '项目要解决的不只是单次量子线路编译，而是如何从候选材料出发，把科学建模、量子求解与部署评估串成可解释闭环。',
  },
  {
    title: '平台目标',
    text: '通过统一工作流把候选材料筛选、化学到量子的转换、分布式编译和综合评分衔接起来，形成可追踪、可复盘的实验平台。',
  },
  {
    title: '平台闭环',
    text: '展示层承担项目叙事和结果表达，工作台承接真实任务，分区编译与芯片映射能力页作为技术明细入口，三者共用同一品牌语言。',
  },
]

export const challengeCards = [
  {
    title: '跨域模型衔接',
    text: '化学域、量子域和部署域的数据结构天然不同，前端必须把后端原始结果收束成统一可视化模型。',
  },
  {
    title: '异步执行可观测',
    text: 'queued 模式下任务会跨多个阶段推进，工作台必须稳定展示进度、事件、阶段输出和最终结果。',
  },
  {
    title: '结果解释一致',
    text: '最终输出不能只有一个分数，还要同时给出科学指标、编译指标、部署信息和可回看的产物。',
  },
  {
    title: '展示与能力并存',
    text: '项目既要满足答辩投屏场景，也要保留底层能力页做真实性证明，因此展示层与能力层必须同品牌、不同密度。',
  },
]

export const workflowSteps = [
  {
    key: 'screening',
    title: '候选筛选',
    input: '预置案例、候选材料',
    process: '完成基础筛选，并生成候选上下文与初始筛选结论',
    output: 'candidate_context',
  },
  {
    key: 'chem_modeling',
    title: '化学建模',
    input: 'candidate_context',
    process: '构建活性位、电子结构与吸附特征相关的科学上下文',
    output: 'scientific_context',
  },
  {
    key: 'quantum_encoding',
    title: '量子编码',
    input: 'scientific_context',
    process: '构造 Hamiltonian、初态、ansatz 与线路工件',
    output: 'qasm / encoding artifacts',
  },
  {
    key: 'distributed_compiling',
    title: '分布式编译',
    input: 'qasm / topology constraints',
    process: '执行电路分区、芯片映射与跨芯片代价分析',
    output: 'partition result / mapping result',
  },
  {
    key: 'simulation_evaluating',
    title: '模拟评估',
    input: 'compiled circuit',
    process: '评估保真度、一致性和部署可执行性',
    output: 'simulation metrics',
  },
  {
    key: 'scoring',
    title: '综合评分',
    input: 'scientific + deployment metrics',
    process: '计算 ChemScore、DeployScore 与 FinalScore',
    output: 'summary',
  },
  {
    key: 'aggregating',
    title: '结果聚合',
    input: 'summary / artifacts / snapshots',
    process: '生成统一 result_view，供工作台、历史页与结果页消费',
    output: 'result_view',
  },
]

export const resultCards = [
  {
    label: '推荐候选',
    value: 'Li2S6',
    note: '当前联调样例中的默认推荐候选材料',
  },
  {
    label: 'Final Score',
    value: '88.6',
    note: '来自平台工作流 result_view.summary.final_score',
  },
  {
    label: '推荐拓扑',
    value: 'linear-3',
    note: '来自 result_view.artifacts.topology_name',
  },
]

export const resultMetrics = [
  { label: 'adsorption_energy', value: '-2.31' },
  { label: 'qubit_count', value: '8' },
  { label: 'partition_count', value: '3' },
  { label: 'teleportations', value: '2' },
  { label: 'fidelity_score', value: '0.93' },
  { label: 'energy_estimate', value: '-1.72' },
]

export const resultLeaderboard = [
  {
    name: 'Li2S6',
    chemScore: 91.4,
    deployScore: 85.8,
    finalScore: 88.6,
    rationale: '吸附表现和部署代价均衡，适合作为当前推荐候选。',
  },
  {
    name: 'Li2S4',
    chemScore: 87.2,
    deployScore: 80.5,
    finalScore: 83.9,
    rationale: '化学指标稳定，但部署侧收益略低于 Li2S6。',
  },
  {
    name: 'Li2S8',
    chemScore: 84.6,
    deployScore: 78.3,
    finalScore: 81.1,
    rationale: '具备可行性，但综合评分和稳定性不占优。',
  },
]

export const homeResultPreview = [
  { label: 'ChemScore', value: '91.4' },
  { label: 'DeployScore', value: '85.8' },
  { label: 'FinalScore', value: '88.6' },
]

export const architectureLayers = [
  {
    title: '展示层',
    desc: '负责项目叙事、流程解释、结果表达与答辩导向展示。',
  },
  {
    title: '工作台层',
    desc: '负责任务创建、阶段跟踪、结果视图与能力入口整合。',
  },
  {
    title: '平台编排层',
    desc: '负责 workflow 生命周期、阶段推进、事件记录与结果聚合。',
  },
  {
    title: '领域服务层',
    desc: '负责候选筛选、化学建模、量子编码、分布式编译、模拟评估与评分。',
  },
  {
    title: '结果与工件层',
    desc: '负责 summary、scientific snapshot、artifacts 以及历史归档。',
  },
]

export const boundaryCards = [
  {
    title: '前端职责',
    text: '负责状态可视化、任务发起、阶段与事件展示、结果组织、历史回看和能力页联动。',
  },
  {
    title: '后端职责',
    text: '负责提供统一工作流接口、阶段推进、结果聚合、结构化事件以及编译评分相关领域服务。',
  },
  {
    title: '联调边界',
    text: '前端优先消费 /api/platform/** 统一契约，原有能力页继续复用 QASM 上传、分区与映射接口。',
  },
]

export const highlightGroups = [
  {
    title: '场景创新',
    text: '把锂硫电池催化材料筛选与分布式量子编译放到同一个展示与执行平台中。',
  },
  {
    title: '架构创新',
    text: '展示层与能力层分离，既能讲清项目，又能证明系统真实可运行。',
  },
  {
    title: '工程创新',
    text: '工作流阶段、事件日志、结果视图和历史归档统一建模，便于扩展与联调。',
  },
  {
    title: '评价创新',
    text: '最终结果同时考虑科学指标与部署指标，而不是只关注单次编译结果。',
  },
]

export const homeSurfaceCards = [
  {
    title: '候选筛选工作台',
    route: '/app/screening',
    text: '进入正式联调工作区，创建任务、跟踪阶段推进并查看日志。',
    meta: 'workflow / execution / status',
  },
  {
    title: '综合结果页',
    route: '/app/results',
    text: '查看推荐候选、评分拆解、可追溯产物与解释性摘要。',
    meta: 'ranking / scores / traceability',
  },
  {
    title: '知识与 AI 支持',
    route: '/app/knowledge',
    text: '检索平台知识库、参考文献和 AI 问答支持内容。',
    meta: 'knowledge / reference / ai',
  },
  {
    title: '项目介绍页',
    route: '/overview',
    text: '查看背景、动机、难点与系统设计说明，不再挤占首页入口信息。',
    meta: 'background / challenge / overview',
  },
]
