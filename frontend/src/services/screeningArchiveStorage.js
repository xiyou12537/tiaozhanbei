const CURRENT_SCREENING_WORKFLOW_KEY = 'liangzhi-screening-workflow'
const SCREENING_WORKFLOW_ARCHIVE_KEY = 'liangzhi-screening-workflow-archive'
const MAX_ARCHIVE_RECORDS = 20

export function readCurrentScreeningWorkflow() {
  return readJson(CURRENT_SCREENING_WORKFLOW_KEY, {})
}

export function saveCurrentScreeningWorkflow(record) {
  if (!record?.workflowId) return
  writeJson(CURRENT_SCREENING_WORKFLOW_KEY, normalizeArchiveRecord(record))
}

export function readArchivedScreeningWorkflows() {
  const records = readJson(SCREENING_WORKFLOW_ARCHIVE_KEY, [])
  return Array.isArray(records) ? records : []
}

export function saveScreeningWorkflowArchive(record) {
  if (!record?.workflowId) return []

  const nextRecords = mergeScreeningArchiveRecord(readArchivedScreeningWorkflows(), record)
  writeJson(SCREENING_WORKFLOW_ARCHIVE_KEY, nextRecords)
  saveCurrentScreeningWorkflow(nextRecords[0])
  return nextRecords
}

export function mergeScreeningArchiveRecord(records, record) {
  if (!record?.workflowId) return Array.isArray(records) ? records : []

  const safeRecords = Array.isArray(records) ? records : []
  const previousRecord = safeRecords.find(item => item?.workflowId === record.workflowId) || {}
  const normalizedRecord = normalizeArchiveRecord({
    ...previousRecord,
    ...record,
    createdAt: previousRecord.createdAt || record.createdAt,
  })
  const dedupedRecords = safeRecords.filter(item => item?.workflowId && item.workflowId !== normalizedRecord.workflowId)

  return [normalizedRecord, ...dedupedRecords]
    .sort((left, right) => getTimeValue(right.updatedAt) - getTimeValue(left.updatedAt))
    .slice(0, MAX_ARCHIVE_RECORDS)
}

function normalizeArchiveRecord(record) {
  const now = new Date().toISOString()
  const selectedCandidates = Array.isArray(record.selectedCandidates) ? record.selectedCandidates : []

  return {
    workflowId: record.workflowId,
    caseId: record.caseId || '',
    createdAt: record.createdAt || record.updatedAt || now,
    updatedAt: record.updatedAt || now,
    selectedCandidates,
    candidateCount: Number(record.candidateCount || selectedCandidates.length || 0),
    recommendedMaterial: record.recommendedMaterial || '',
    status: record.status || 'created',
    source: record.source || 'local',
  }
}

function readJson(key, fallback) {
  if (typeof localStorage === 'undefined') return fallback

  try {
    return JSON.parse(localStorage.getItem(key) || JSON.stringify(fallback))
  } catch (error) {
    console.warn(`Failed to read ${key}`, error)
    return fallback
  }
}

function writeJson(key, value) {
  if (typeof localStorage === 'undefined') return

  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch (error) {
    console.warn(`Failed to write ${key}`, error)
  }
}
