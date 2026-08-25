const runningStatuses = new Set(['queued', 'running'])

function isPresent(value) {
  return value !== null && value !== undefined && value !== ''
}

function deploymentConclusion(result = {}, status) {
  if (result.engineering_only_deployment === true) return '仅工程部署证据'
  if (result.engineering_only_deployment === false) return '科学验证点部署'
  if (!['completed', 'failed'].includes(status)) return '尚未形成部署结论'
  if (result.summary?.issues?.some(issue => issue?.code === 'legacy_result_missing_release_fields')) return '旧版结果，未记录部署依据'
  return '尚未形成部署结论'
}

export function summarizeHistoryMetrics({ items = [], total = 0, dataSource = 'server' } = {}) {
  const records = Array.isArray(items) ? items : []
  const counts = {
    running: records.filter(item => runningStatuses.has(item?.status)).length,
    review: records.filter(item => item?.validation_status === 'needs_review' || item?.status === 'needs_review').length,
    failed: records.filter(item => item?.status === 'failed').length,
  }
  const hasServerTotal = dataSource === 'server' && Number.isFinite(Number(total))
  return {
    total: hasServerTotal ? Number(total) : records.length,
    totalLabel: hasServerTotal ? '服务端全部任务' : '本机缓存记录',
    scopeLabel: hasServerTotal ? '当前页状态分布' : '缓存状态分布',
    counts,
  }
}

export function studyDeploymentEvidence(evaluation = {}) {
  if (evaluation?.status === 'failed') return { verified: false, review: false, label: '评估失败', type: 'danger', message: '评估运行失败，不能作为部署候选。' }
  if (evaluation?.status !== 'completed') return { verified: false, review: evaluation?.is_deployable === true, label: '评估未完成，需复核', type: 'warning', message: '评估尚未完成，不能作为部署候选。' }
  if (evaluation?.is_deployable !== true) return { verified: false, review: false, label: '不可部署', type: 'danger', message: '后端未将该架构标记为可部署。' }

  const validationStatus = evaluation?.deployment_validation?.status
  if (validationStatus === 'passed') return { verified: true, review: false, label: '已通过部署验证', type: 'success', message: '已完成、标记为可部署，且部署验证明确通过。' }
  if (validationStatus === undefined || validationStatus === null || validationStatus === '') return { verified: false, review: true, label: '部署验证缺失，需复核', type: 'warning', message: '部署可行标记存在，但部署验证缺失，需要复核。' }
  if (validationStatus === 'queued' || validationStatus === 'running') return { verified: false, review: true, label: '部署验证未完成，需复核', type: 'warning', message: '部署可行标记存在，但部署验证尚未完成，需要复核。' }
  if (validationStatus === 'failed') return { verified: false, review: true, label: '部署验证未通过', type: 'danger', message: '部署可行标记存在，但部署验证未通过。' }
  return { verified: false, review: true, label: '部署验证状态未知，需复核', type: 'warning', message: '部署可行标记存在，但部署验证状态未知，需要复核。' }
}

export function summarizeStudyDeploymentEvidence(study = {}) {
  const evaluations = Array.isArray(study.result?.deployment_evaluations) ? study.result.deployment_evaluations : []
  const states = evaluations.map(studyDeploymentEvidence)
  return {
    evaluations,
    states,
    verifiedCandidateCount: states.filter(state => state.verified).length,
    reviewCount: states.filter(state => state.review).length,
    failedCount: evaluations.filter(item => item?.status === 'failed').length,
  }
}

export function summarizeStudyDecision(study = {}) {
  const { evaluations, failedCount } = summarizeStudyDeploymentEvidence(study)
  const candidates = evaluations.filter(item => studyDeploymentEvidence(item).verified)
  const names = candidates.map(item => item.architecture_name || item.architecture_id).filter(Boolean)
  const overall = {
    completed: '整体比较已完成。',
    partial: '整体比较尚未完成；以下只展示已验证子结果，不能作为最终推荐。',
    failed: '整体比较未完成；以下只展示已验证子结果，不能作为最终推荐。',
    needs_review: '整体比较需要复核；以下只展示已验证子结果，不能作为最终推荐。',
  }[study.status] || '整体比较状态待确认；不能形成最终推荐。'
  const candidateName = names.length === 1 ? names[0] : names.length > 1 ? `${names.length} 个已验证候选` : '尚无已验证候选'
  const candidate = study.status === 'completed' || !names.length ? candidateName : `已验证子结果：${candidateName}`
  const isCompleted = study.status === 'completed'
  return {
    overall,
    candidate,
    reason: names.length
      ? '候选已完成、标记为可部署，且部署验证明确通过；这不是综合最优结论，仍需同时比较通信量、SWAP、执行误差与适用约束。'
      : '当前没有同时满足完成、可部署和部署验证通过的架构，不能给出推荐。',
    confidence: !isCompleted ? overall : failedCount ? `比较中包含 ${failedCount} 个失败项，未纳入候选。` : '科学、优化器与部署验证仍需独立查看。',
    next: !isCompleted
      ? study.status === 'needs_review' ? '先复核科学、优化器或部署证据，再决定是否继续。' : '等待其余架构完成或查看失败原因后再比较。'
      : names.length ? '查看候选的科学、优化器与部署验证，再决定是否继续细化架构。' : '查看失败原因或等待其余架构完成后再比较。',
  }
}

export function summarizeScanDecision(scan = {}) {
  const result = scan.result || {}
  const minimum = result.scientific_vqe_discrete_minimum || null
  const completed = isPresent(scan.completed_point_count) ? scan.completed_point_count : 0
  const total = isPresent(scan.total_point_count) ? scan.total_point_count : '—'
  const hasDistance = isPresent(minimum?.distance_angstrom)
  const boundary = !minimum
    ? '尚无科学 VQE 离散最低点，无法判断扫描边界位置。'
    : minimum.minimum_at_boundary === true
      ? '最低离散点落在扫描边界，当前范围不足以判断更低位置。'
      : minimum.minimum_at_boundary === false
        ? '最低离散点位于当前扫描范围内部。'
        : '最低离散点的边界位置未知；旧记录未提供或未完成该字段。'
  const fciStatus = result.fci_discrete_minimum ? 'FCI 参考最低点已返回。' : 'FCI 参考最低点未返回或不可用。'
  const next = !minimum
    ? ['queued', 'running'].includes(scan.status)
      ? '等待更多扫描点完成后再判断趋势。'
      : scan.status === 'needs_review'
        ? '复核科学验证后再判断是否需要重新扫描。'
        : scan.status === 'failed'
          ? '检查失败点或重新扫描后再判断趋势。'
          : '查看失败点或复核科学验证后再判断趋势。'
    : minimum.minimum_at_boundary === true
      ? '建议扩大扫描范围后再判断趋势。'
      : minimum.minimum_at_boundary === false
        ? '建议缩小该区间的间隔，并复核科学验证。'
        : '边界位置未知；请查看旧记录字段、刷新结果或重新扫描。'
  return {
    progress: `${completed} / ${total} 个离散点`,
    minimum: minimum ? (hasDistance ? `${minimum.distance_angstrom} Å 的科学 VQE 离散候选点` : '距离未记录的科学 VQE 离散候选点') : '尚无科学 VQE 离散候选点',
    boundary,
    science: fciStatus,
    deployment: deploymentConclusion(result, scan.status),
    next,
  }
}
