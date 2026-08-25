const runningStates = new Set(['queued', 'running'])

export function workflowStatusMeta(status) {
  if (status === 'completed') return { label: '已完成', tone: 'completed' }
  if (status === 'partial') return { label: '部分完成', tone: 'partial' }
  if (status === 'failed') return { label: '未完成', tone: 'failed' }
  if (runningStates.has(status)) return { label: status === 'queued' ? '已排队' : '计算中', tone: 'running' }
  return { label: '状态待确认', tone: 'unknown' }
}

export function summarizeWorkbenchTasks(items = []) {
  const tasks = Array.isArray(items) ? items : []
  return {
    total: tasks.length,
    running: tasks.filter(item => runningStates.has(item?.status)).length,
    review: tasks.filter(item => item?.validation_status === 'needs_review' || item?.status === 'needs_review').length,
    recent: tasks.slice(0, 6),
  }
}
