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
    description: '校验身份、参数和输入工件格式。',
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
    description: '构建活性位模型与电子结构输入。',
    availability: 'planned',
  },
  {
    key: 'quantum_encoding',
    label: '量子编码',
    owner: 'Quantum Problem Service',
    description: '生成 Hamiltonian、初态、ansatz 与 QASM 工件。',
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

export const presetCases = [
  {
    name: 'Fe-N4 单原子催化位',
    stage: '预置案例',
    focus: '吸附位筛选与分布式编译对比',
    note: '适合作为整条科研链路的演示入口。',
  },
  {
    name: 'CoS2 边缘位点',
    stage: '化学建模候选',
    focus: '活性位模型构建与中间体稳定性评估',
    note: '用于验证后续 Chemistry 与 Scoring 域对接。',
  },
  {
    name: 'Ni 团簇负载体系',
    stage: '编译能力联调',
    focus: 'QASM 工件上传与分区 / 映射工作台',
    note: '当前原型已可承接分布式编译子域实验。',
  },
]
