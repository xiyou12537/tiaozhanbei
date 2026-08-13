const RECENT_SCANS_KEY = 'molecular-bond-scan-recent'

export function saveRecentMolecularBondScan(scan) {
  if (!scan?.scan_id) return []
  let current = []
  try { current = JSON.parse(localStorage.getItem(RECENT_SCANS_KEY) || '[]') } catch {}
  const next = [{ scanId: scan.scan_id, status: scan.status || null, engineeringOnlyDeployment: scan.result?.engineering_only_deployment ?? null, savedAt: new Date().toISOString() }, ...(Array.isArray(current) ? current : []).filter(item => item.scanId !== scan.scan_id)].slice(0, 10)
  localStorage.setItem(RECENT_SCANS_KEY, JSON.stringify(next))
  return next
}
