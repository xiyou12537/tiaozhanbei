const RECENT_STUDIES_KEY = 'molecular-study-recent-studies'
const MAX_RECENT_STUDIES = 10

export function readRecentMolecularStudies() {
  try {
    const value = JSON.parse(localStorage.getItem(RECENT_STUDIES_KEY) || '[]')
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

export function saveRecentMolecularStudy(study) {
  const molecularProblemId = study?.molecular_problem_id ?? study?.problem_id ?? null
  if (!study?.study_id) return readRecentMolecularStudies()
  const current = readRecentMolecularStudies().filter(item => item.studyId !== study.study_id)
  const next = [{
    studyId: study.study_id,
    molecularProblemId,
    status: study.status || null,
    savedAt: new Date().toISOString(),
  }, ...current].slice(0, MAX_RECENT_STUDIES)
  localStorage.setItem(RECENT_STUDIES_KEY, JSON.stringify(next))
  return next
}
