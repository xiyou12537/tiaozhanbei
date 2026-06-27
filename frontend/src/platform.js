export const workflowStages = [
  {
    key: 'created',
    label: '任务创建',
    owner: 'Platform Orchestrator',
    description: '创建 workflow_instance 并登记输入快照。',
    availability: 'online',
  },
  {
    key: 'validated',
    label: '输入校验',
    owner: 'API Gateway',
    description: '校验身份、参数和工件格式。',
    availability: 'online',
  },
  {
    key: 'screening',
    label: '候选筛选',
    owner: 'Candidate Service',
    description: '生成候选材料任务清单与实验模板。',
    availability: 'planned',
  },
  {
    key: 'chem_modeling',
    label: '化学建模',
    owner: 'Chemistry Modeling Service',
    description: '构建活性位微模型与电子结构输入。',
    availability: 'planned',
  },
  {
    key: 'quantum_encoding',
    label: '量子问题构造',
    owner: 'Quantum Problem Service',
    description: '生成哈密顿量、初态、ansatz 与 QASM 工件。',
    availability: 'planned',
  },
  {
    key: 'distributed_compiling',
    label: '分布式编译',
    owner: 'Distributed Compiler Service',
    description: '执行量子线路划分、映射与跨芯片代价分析。',
    availability: 'online',
  },
  {
    key: 'simulation_evaluating',
    label: '模拟评估',
    owner: 'Simulation & Evaluation Service',
    description: '验证编译后线路的一致性与保真度。',
    availability: 'planned',
  },
  {
    key: 'scoring',
    label: '综合评分',
    owner: 'Scoring Service',
    description: '计算 ChemScore、DeployScore 与 FinalScore。',
    availability: 'planned',
  },
  {
    key: 'aggregating',
    label: '结果聚合',
    owner: 'Result Aggregation Service',
    description: '生成前端消费的统一结果视图。',
    availability: 'partial',
  },
  {
    key: 'completed',
    label: '任务完成',
    owner: 'Workflow Metadata Service',
    description: '记录完成状态、事件日志与结果引用。',
    availability: 'partial',
  },
]

export const platformServices = [
  {
    name: 'API Gateway',
    icon: 'Connection',
    boundary: '前端统一入口',
    responsibility: '认证透传、路由、版本控制、统一错误输出',
    status: 'online',
  },
  {
    name: 'Platform Orchestrator',
    icon: 'Operation',
    boundary: '流程控制边界',
    responsibility: '维护状态机、触发下游服务、聚合阶段视图',
    status: 'target',
  },
  {
    name: 'Candidate Service',
    icon: 'Tickets',
    boundary: '候选与案例域',
    responsibility: '候选材料、模板、实验配置管理',
    status: 'planned',
  },
  {
    name: 'Chemistry Modeling Service',
    icon: 'MagicStick',
    boundary: '化学建模域',
    responsibility: '构型生成、积分计算、活性空间裁剪',
    status: 'planned',
  },
  {
    name: 'Quantum Problem Service',
    icon: 'Cpu',
    boundary: '量子编码域',
    responsibility: 'Hamiltonian、初态、ansatz、QASM 工件输出',
    status: 'partial',
  },
  {
    name: 'Distributed Compiler Service',
    icon: 'Grid',
    boundary: '分布式编译域',
    responsibility: '分区、映射、路由、部署代价分析',
    status: 'online',
  },
  {
    name: 'Simulation & Evaluation Service',
    icon: 'Histogram',
    boundary: '评估域',
    responsibility: '模拟执行、保真度分析、误差评估',
    status: 'planned',
  },
  {
    name: 'Scoring Service',
    icon: 'DataLine',
    boundary: '评分域',
    responsibility: '门控规则、推荐排序、解释生成',
    status: 'planned',
  },
  {
    name: 'Result Aggregation Service',
    icon: 'DataAnalysis',
    boundary: '展示契约边界',
    responsibility: '统一结果视图、图表数据、工作台摘要',
    status: 'target',
  },
]

export const presetCases = [
  {
    name: 'Fe-N4 单原子催化位',
    stage: '预置案例',
    focus: '吸附位筛选 + 分布式编译对比',
    note: '适合作为整条科研链路的演示入口。',
  },
  {
    name: 'CoS2 边缘位点',
    stage: '化学建模候选',
    focus: '活性位微模型构建 + 中间体稳定性评估',
    note: '用于验证后续 Chemistry / Scoring 域对接。',
  },
  {
    name: 'Ni 团簇负载体系',
    stage: '编译能力联调',
    focus: 'QASM 工件上传 + 分区 / 映射工作台',
    note: '当前原型已可承接分布式编译子域实验。',
  },
]

export const recommendationBoard = [
  {
    candidate: 'Fe-N4 / Ring-4',
    chemScore: '89.2',
    deployScore: '76.4',
    finalScore: '83.7',
    explanation: '部署代价稳定，适合作为平台基线案例。',
  },
  {
    candidate: 'CoS2 edge / Grid-2x2',
    chemScore: '84.6',
    deployScore: '81.9',
    finalScore: '83.1',
    explanation: '网格拓扑下的跨芯片通信更均衡。',
  },
  {
    candidate: 'Ni cluster / Linear-4',
    chemScore: '78.8',
    deployScore: '72.1',
    finalScore: '75.4',
    explanation: '适合展示映射策略变化对代价的影响。',
  },
]

export const capabilityGroups = [
  {
    title: '展示层',
    items: ['项目总览', '流程链说明', '推荐榜单', '系统架构展示'],
  },
  {
    title: '工作台',
    items: ['创建实验任务', '阶段状态跟踪', '结果摘要视图', '统一结果聚合'],
  },
  {
    title: '能力页',
    items: ['QASM 上传', '分区求解', '芯片映射', '报告导出'],
  },
]

export const previewExperimentQueue = [
  {
    id: 'WF-20260627-001',
    caseName: 'Fe-N4 吸附位筛选',
    owner: 'Platform Orchestrator',
    status: 'running',
    stage: 'distributed_compiling',
    progress: 68,
  },
  {
    id: 'WF-20260627-002',
    caseName: 'CoS2 中间体稳定性评估',
    owner: 'Chemistry Modeling Service',
    status: 'queued',
    stage: 'chem_modeling',
    progress: 12,
  },
  {
    id: 'WF-20260627-003',
    caseName: 'Ni 团簇部署代价对比',
    owner: 'Result Aggregation Service',
    status: 'completed',
    stage: 'completed',
    progress: 100,
  },
]

export const previewServiceHealth = [
  { name: 'API Gateway', latency: '42 ms', successRate: '99.9%', status: 'healthy' },
  { name: 'Platform Orchestrator', latency: '73 ms', successRate: '99.2%', status: 'healthy' },
  { name: 'Distributed Compiler Service', latency: '1.8 s', successRate: '96.4%', status: 'healthy' },
  { name: 'Result Aggregation Service', latency: '118 ms', successRate: '98.7%', status: 'healthy' },
  { name: 'Chemistry Modeling Service', latency: '--', successRate: '--', status: 'planned' },
  { name: 'Scoring Service', latency: '--', successRate: '--', status: 'planned' },
]

export const previewArtifacts = [
  { name: 'input_snapshot.json', domain: 'Experiment Domain', type: 'snapshot', owner: 'Platform Orchestrator' },
  { name: 'hamiltonian.fcidump', domain: 'Chemistry Domain', type: 'artifact', owner: 'Chemistry Modeling Service' },
  { name: 'compiled_partition.json', domain: 'Distributed Compilation Domain', type: 'result', owner: 'Distributed Compiler Service' },
  { name: 'result_view.json', domain: 'Presentation Domain', type: 'view', owner: 'Result Aggregation Service' },
  { name: 'report_bundle.zip', domain: 'Presentation Domain', type: 'export', owner: 'Report & Visualization Service' },
]

export const previewRecommendationCards = [
  {
    title: '推荐催化位',
    primary: 'Fe-N4 / Bridge Site',
    secondary: 'FinalScore 83.7 · ChemScore 89.2 · DeployScore 76.4',
    note: '兼顾吸附活性与分布式部署成本，适合作为当前基线方案。',
  },
  {
    title: '推荐拓扑',
    primary: 'Grid 2x2',
    secondary: 'EPR cost 14 · fidelity retention 0.93',
    note: '对当前四分区任务更均衡，较环形拓扑减少跨芯片热点。',
  },
  {
    title: '推荐交付物',
    primary: '统一结果视图 + 报告导出',
    secondary: 'result_view / chart_dataset / artifact_bundle',
    note: '前端只消费聚合层输出，不直连领域服务内部结构。',
  },
]
