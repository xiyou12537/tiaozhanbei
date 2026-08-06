import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const workbenchSource = await readFile(
  new URL('../src/views/StructureWorkbenchPage.vue', import.meta.url),
  'utf8'
)

test('工作台呈现从化学结构到芯片模拟的完整阶段', () => {
  const requiredStages = [
    '结构输入',
    '活性位点',
    '吸附构型',
    '几何与 DFT 证据',
    '量子区与活性空间',
    'Hamiltonian 与线路',
    '线路分组',
    '芯片映射',
    '芯片路由',
    '模拟执行',
    '结果与证据',
  ]

  for (const stage of requiredStages) {
    assert.match(workbenchSource, new RegExp(stage))
  }
})

test('未实现的路由与模拟能力保持禁用并说明边界', () => {
  assert.match(workbenchSource, /芯片路由后端尚未实现/)
  assert.match(workbenchSource, /路由后模拟执行接口尚未实现/)
  assert.match(workbenchSource, /<el-button type="primary" disabled>生成路由后线路<\/el-button>/)
  assert.match(workbenchSource, /<el-button type="primary" disabled>开始模拟执行<\/el-button>/)
})

test('基准 statevector 结果不冒充芯片路由后结果', () => {
  assert.match(workbenchSource, /非芯片路由后结果/)
  assert.match(workbenchSource, /不是芯片映射、路由后的执行结果/)
  assert.doesNotMatch(workbenchSource, /路由后模拟已完成/)
})
