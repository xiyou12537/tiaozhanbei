const RECENT_TASKS_KEY = 'molecule-workflow-recent-tasks'
const MAX_RECENT_TASKS = 10

export function readRecentMoleculeWorkflows() {
  try {
    const value = JSON.parse(localStorage.getItem(RECENT_TASKS_KEY) || '[]')
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

export function saveRecentMoleculeWorkflow(result) {
  const current = readRecentMoleculeWorkflows().filter(item => item.workflowId !== result.workflow_id)
  const next = [{
    workflowId: result.workflow_id,
    moleculeName: result.molecule?.molecule_name || '未命名分子',
    validationStatus: result.validation_status || null,
    completedAt: new Date().toISOString(),
  }, ...current].slice(0, MAX_RECENT_TASKS)
  localStorage.setItem(RECENT_TASKS_KEY, JSON.stringify(next))
  return next
}
