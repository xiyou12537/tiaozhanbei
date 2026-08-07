import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const readSource = path => readFile(new URL(path, import.meta.url), 'utf8')
const [homeSource, sceneSource] = await Promise.all([
  readSource('../src/views/HomePage.vue'),
  readSource('../src/components/home/MoleculeNarrativeCanvas.vue'),
])

test('首页首屏使用 (LiH)₄ 连续叙事并保留两个计算入口', () => {
  assert.match(homeSource, /分子量子/)
  assert.match(homeSource, /分布式计算平台/)
  assert.match(homeSource, /从分子结构，到可验证的协同计算。/)
  assert.match(homeSource, /开始计算/)
  assert.match(homeSource, /看见完整过程/)
  assert.match(homeSource, /逻辑分布式模拟，非真实 QPU。/)
  assert.match(homeSource, /MoleculeNarrativeCanvas/)
  assert.match(homeSource, /新建计算/)
  assert.match(homeSource, /计算任务/)
  assert.match(homeSource, /\(LiH\)₄/)
})

test('首页滚动叙事只有四句场景文案且不暴露开发者术语', () => {
  const narrativeSource = `${homeSource}\n${sceneSource}`
  for (const sentence of ['从一组原子开始。', '化作一条量子线路。', '在芯片之间展开。', '抵达同一个答案。']) {
    assert.match(narrativeSource, new RegExp(sentence))
  }
  assert.doesNotMatch(homeSource, /线路分区|拓扑映射|Hamiltonian/)
})

test('(LiH)₄ 场景使用立方交替团簇、阶段化指标和无障碍降级', () => {
  assert.match(sceneSource, /three/i)
  assert.match(sceneSource, /\(LiH\)₄/)
  assert.doesNotMatch(`${homeSource}\n${sceneSource}`, /LiH₄|LiH4/)
  assert.match(sceneSource, /cubane|立方/i)
  assert.match(sceneSource, /workflowEvidence/)
  assert.match(sceneSource, /visibleMetrics/)
  assert.match(sceneSource, /slice\(0, 4\)/)
  assert.match(sceneSource, /prefers-reduced-motion/)
  assert.match(sceneSource, /IntersectionObserver/)
  assert.match(sceneSource, /WebGL|webgl/)
  assert.match(sceneSource, /结构化占位|等待真实 Workflow/)
  assert.match(sceneSource, /chip_topology_routing/)
})

test('阶段对象按分子、线路、三颗虚拟 QPU 与能量结果依次交接', () => {
  for (const scenePart of ['moleculeOpacity', 'circuitOpacity', 'qpuOpacity', 'energyOpacity', 'localCircuit', 'interChip']) {
    assert.match(sceneSource, new RegExp(scenePart))
  }
  assert.match(sceneSource, /startY.*endY|endY.*startY/)
  assert.match(sceneSource, /compactLayout/)
})

test('量子线路使用可辨识的 X、RY(θ) 和 CX 标准符号', () => {
  for (const fragment of ['quantum-circuit-diagram', 'q0', 'q1', 'q2…', 'RY(θ)', 'cx-control', 'cx-target', '●', '⊕']) {
    assert.match(sceneSource, new RegExp(fragment.replace(/[()]/g, '\\$&')))
  }
  assert.match(sceneSource, /circuitEvidence/)
  assert.match(sceneSource, /等待真实 Workflow/)
})

test('三颗虚拟芯片区分芯片内路由、SWAP 与跨芯片通信', () => {
  for (const fragment of ['VIRTUAL QPU 01', 'VIRTUAL QPU 02', 'VIRTUAL QPU 03', 'physical-coupling', 'chip-route', 'SWAP', 'inter-chip-communication', '跨芯片通信']) {
    assert.match(sceneSource, new RegExp(fragment))
  }
})

test('芯片拓扑使用显式物理节点和无交叉耦合边表达芯片内 CX', () => {
  for (const fragment of ['chipTopologyNodes', 'chipTopologyEdges', 'topology-frame', 'coupling-vertical', 'chip-local-cx']) {
    assert.match(sceneSource, new RegExp(fragment))
  }
})

test('能量一致性仪表比较两种执行结果且不伪造数值', () => {
  for (const fragment of ['energy-consistency-instrument', '未分区 VQE 能量', '分布式模拟能量', '绝对误差 |ΔE|', '— Ha', 'energy-check']) {
    assert.match(sceneSource, new RegExp(fragment.replace(/[|()]/g, '\\$&')))
  }
  assert.doesNotMatch(sceneSource, /-?\d+\.\d+\s*Ha/)
})
