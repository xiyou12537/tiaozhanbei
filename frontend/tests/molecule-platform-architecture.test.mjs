import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import * as workflowService from '../src/services/moleculeWorkflowService.js'
import forcedSwapFixture from './fixtures/forced-swap-molecule-workflow.mjs'
import zeroSwapFixture from './fixtures/zero-swap-molecule-workflow.mjs'

const source = async path => readFile(new URL(path, import.meta.url), 'utf8')
const [routerSource, layoutSource, homeSource, entrySource, resultSource, authPageSource, authCardSource] = await Promise.all([
  source('../src/router.js'),
  source('../src/views/Layout.vue'),
  source('../src/views/HomePage.vue'),
  source('../src/views/MoleculesPage.vue'),
  source('../src/views/MoleculeWorkflowResultPage.vue'),
  source('../src/views/AuthPage.vue'),
  source('../src/components/AuthFormCard.vue'),
])

const capabilities = {
  contract_version: '2.0',
  supported_elements: ['H', 'Li', 'O'],
  supported_basis_sets: ['sto-3g'],
  max_atom_count: 10,
  max_mapped_qubits: 12,
  partition_counts: [2, 3],
  partition_strategies: ['sequential_greedy'],
  inter_qpu_topologies: ['user_supplied_undirected_edge_list'],
  physical_coupling_maps: ['user_supplied_undirected_edge_list'],
  initial_layout_methods: ['identity'],
  routing_methods: ['shortest_path_swap'],
  execution_modes: ['logical_virtual_qpu'],
  is_real_qpu: false,
}

test('能力接口可注入请求并驱动表单支持范围', async () => {
  let requested = false
  const response = await workflowService.getMoleculeWorkflowCapabilities({
    request: async () => {
      requested = true
      return { data: capabilities }
    },
  })
  assert.equal(requested, true)
  assert.equal(response.max_mapped_qubits, 12)
  const form = workflowService.createCapabilityDrivenMoleculeForm(capabilities, 'H2')
  assert.equal(form.basisSet, 'sto-3g')
  assert.equal(form.partitionCount, 2)
  assert.equal(form.virtualQpus.length, 2)
  assert.equal(form.routingMethod, 'shortest_path_swap')
})

test('请求明确分离分区间拓扑和每颗芯片物理耦合拓扑', () => {
  const form = workflowService.createCapabilityDrivenMoleculeForm(capabilities, 'H2')
  form.interQpuTopology = [{ source: 0, target: 1 }]
  form.virtualQpus[0].physicalQubitCount = 3
  form.virtualQpus[0].physicalCouplingMap = [{ source: 0, target: 2 }, { source: 2, target: 1 }]
  const payload = workflowService.buildMoleculeWorkflowPayload(form)
  assert.deepEqual(payload.partition.inter_qpu_topology, [{ source: 0, target: 1 }])
  assert.deepEqual(payload.partition.virtual_qpus[0].physical_coupling_map, [{ source: 0, target: 2 }, { source: 2, target: 1 }])
  assert.equal(payload.partition.initial_layout, 'identity')
  assert.equal(payload.partition.routing_method, 'shortest_path_swap')
  assert.equal(payload.partition.partition_strategy, 'sequential_greedy')
  assert.equal('topology_edges' in payload.partition, false)
})

test('能力校验拒绝不支持的元素、基组、分区数和芯片边', () => {
  const form = workflowService.createCapabilityDrivenMoleculeForm(capabilities, 'H2')
  form.geometry[0].element = 'C'
  form.basisSet = '6-31g'
  form.partitionCount = 4
  form.virtualQpus[0].physicalQubitCount = 3
  form.virtualQpus[0].physicalCouplingMap = [{ source: 0, target: 3 }]
  const errors = workflowService.validateMoleculeWorkflowForm(form, capabilities).join('\n')
  assert.match(errors, /元素 C 不在当前能力范围/)
  assert.match(errors, /基组 6-31g 不在当前能力范围/)
  assert.match(errors, /分区数量 4 不在当前能力范围/)
  assert.match(errors, /物理耦合边/)
})

test('零 SWAP 与强制 SWAP Fixture 保留独立拓扑、布局、路径与开销', () => {
  const zero = workflowService.normalizeMoleculeRoutingResult(zeroSwapFixture)
  assert.equal(zero.routedPlanConsumed, true)
  assert.equal(zero.routingCost.abstract_swap_count, 0)
  assert.deepEqual(zero.interQpuTopology, [{ source: 0, target: 1 }])
  assert.deepEqual(zero.chips[0].physical_coupling_map, [{ source: 0, target: 1 }])

  const forced = workflowService.normalizeMoleculeRoutingResult(forcedSwapFixture)
  assert.equal(forced.routedPlanConsumed, true)
  assert.equal(forced.routingCost.abstract_swap_count, 1)
  assert.deepEqual(forced.evidence[0].path, [0, 2, 1])
  assert.deepEqual(forced.evidence[0].swap_path, [[0, 2]])
  assert.notDeepEqual(
    forced.chips[0].logical_to_physical_initial,
    forced.chips[0].logical_to_physical_final,
  )
})

test('应用信息架构仅保留分子计算、任务、结果和模拟能力', () => {
  assert.match(routerSource, /simulation-capabilities/)
  for (const removed of ['screening', 'structure-workbench', 'research-benchmarks', "path: 'results'", 'knowledge', "path: 'history'"]) {
    assert.doesNotMatch(routerSource, new RegExp(removed))
  }
  const visibleShell = `${layoutSource}\n${homeSource}\n${entrySource}\n${resultSource}`
  assert.match(visibleShell, /分子量子分布式计算平台/)
  assert.doesNotMatch(visibleShell, /锂硫电池|Li₂S₄|Li2S4|FeN₄|FeN4|吸附|文献基准/)
})

test('登录注册页与分子计算平台使用统一视觉体系', () => {
  const authVisualSource = `${authPageSource}\n${authCardSource}`
  for (const platformColor of ['#f2f3ef', '#17201d', '#b5f04c']) {
    assert.match(authVisualSource, new RegExp(platformColor, 'i'))
  }
  for (const legacyColor of ['#377dff', '#18baa9', '#041321', '#051626']) {
    assert.doesNotMatch(authVisualSource, new RegExp(legacyColor, 'i'))
  }
})

test('新建页为四步且结果页明确区分两类拓扑与路由消费', () => {
  for (const label of ['分子与几何', '电子结构 / VQE 参数', '分区、芯片拓扑和路由', '确认并执行']) {
    assert.match(entrySource, new RegExp(label.replace('/', '\\/')))
  }
  for (const label of ['线路分区', '分区间虚拟 QPU 拓扑', '芯片内部物理耦合拓扑', 'logical-to-physical 布局', 'SWAP 路径', '芯片内路由成本', '跨分区通信', '路由后计划已实际消费', '能量与质量状态']) {
    assert.match(resultSource, new RegExp(label))
  }
  assert.match(resultSource, /actual_routed_plan_consumption/)
  assert.match(resultSource, /非真实 QPU/)
  assert.match(resultSource, /模拟器/)
})
