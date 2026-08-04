const WORKFLOW_ARCHIVE_KEY = 'platform_workflow_archive'
const MAX_ARCHIVE_ITEMS = 50

function readArchivePayload() {
  try {
    return JSON.parse(localStorage.getItem(WORKFLOW_ARCHIVE_KEY) || '[]')
  } catch {
    return []
  }
}

function writeArchivePayload(items) {
  localStorage.setItem(WORKFLOW_ARCHIVE_KEY, JSON.stringify(items))
}

export function readArchivedWorkflows() {
  return readArchivePayload()
}

export function upsertArchivedWorkflow(record) {
  if (!record?.workflowId) return

  const items = readArchivePayload()
  const filtered = items.filter((item) => item.workflowId !== record.workflowId)
  const nextItems = [
    {
      ...record,
      updatedAt: record.updatedAt || new Date().toISOString(),
    },
    ...filtered,
  ].slice(0, MAX_ARCHIVE_ITEMS)

  writeArchivePayload(nextItems)
}

export function clearArchivedWorkflows() {
  localStorage.removeItem(WORKFLOW_ARCHIVE_KEY)
}
