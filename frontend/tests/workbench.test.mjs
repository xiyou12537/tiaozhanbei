import test from 'node:test'
import assert from 'node:assert/strict'
import { summarizeWorkbenchTasks, workflowStatusMeta } from '../src/services/workbenchService.js'

test('工作台按真实执行和质量状态归并任务，不把完成误写为通过', () => {
  const summary = summarizeWorkbenchTasks([
    { status: 'running' },
    { status: 'queued' },
    { status: 'completed', validation_status: 'needs_review' },
    { status: 'completed', validation_status: 'passed' },
  ])

  assert.deepEqual(summary, {
    total: 4,
    running: 2,
    review: 1,
    recent: summary.recent,
  })
  assert.equal(workflowStatusMeta('completed').label, '已完成')
  assert.equal(workflowStatusMeta('completed').tone, 'completed')
  assert.equal(workflowStatusMeta('unexpected').label, '状态待确认')
})
