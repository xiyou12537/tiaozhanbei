import assert from 'node:assert/strict'
import test from 'node:test'
import {
  summarizeHistoryMetrics,
  summarizeScanDecision,
  studyDeploymentEvidence,
  summarizeStudyDecision,
} from '../src/services/productExperienceService.js'

test('历史指标保留服务端总量，并明确状态计数只覆盖当前页', () => {
  const metrics = summarizeHistoryMetrics({
    dataSource: 'server',
    total: 42,
    items: [
      { status: 'running', validation_status: null },
      { status: 'completed', validation_status: 'needs_review' },
      { status: 'failed', validation_status: null },
    ],
  })
  assert.equal(metrics.total, 42)
  assert.equal(metrics.totalLabel, '服务端全部任务')
  assert.equal(metrics.scopeLabel, '当前页状态分布')
  assert.deepEqual(metrics.counts, { running: 1, review: 1, failed: 1 })
})

test('Study 决策只把通过部署验证的项目列为候选，不把单项指标宣称为全面最优', () => {
  const decision = summarizeStudyDecision({
    status: 'completed',
    result: {
      deployment_evaluations: [
        { architecture_name: 'linear-a', status: 'completed', is_deployable: true, deployment_validation: { status: 'passed' } },
        { architecture_name: 'forced-swap', status: 'completed', is_deployable: false, metrics: { abstract_swap_count: 0 } },
      ],
    },
  })
  assert.equal(decision.candidate, 'linear-a')
  assert.match(decision.reason, /不是综合最优结论/)
  assert.match(decision.next, /科学、优化器与部署验证/)
})

test('Bond Scan 决策将离散边界最低点、FCI 缺失与三态部署结论分别表达', () => {
  const decision = summarizeScanDecision({
    status: 'completed',
    total_point_count: 8,
    completed_point_count: 8,
    result: {
      scientific_vqe_discrete_minimum: { distance_angstrom: 1.0, minimum_at_boundary: true },
      fci_discrete_minimum: null,
      engineering_only_deployment: true,
      summary: { issues: [] },
    },
  })
  assert.equal(decision.progress, '8 / 8 个离散点')
  assert.match(decision.minimum, /1 Å/)
  assert.match(decision.boundary, /扫描边界/)
  assert.match(decision.science, /FCI/)
  assert.equal(decision.deployment, '仅工程部署证据')
  assert.match(decision.next, /扩大扫描范围/)
})

test('Study 只有明确通过部署验证的完成架构才能成为首屏候选', () => {
  const makeStudy = deploymentValidation => ({
    status: 'completed',
    result: {
      deployment_evaluations: [{
        architecture_name: 'linear-a', status: 'completed', is_deployable: true,
        ...(deploymentValidation === undefined ? {} : { deployment_validation: deploymentValidation }),
      }],
    },
  })
  assert.equal(summarizeStudyDecision(makeStudy({ status: 'passed' })).candidate, 'linear-a')
  for (const validation of [{ status: 'failed' }, { status: 'running' }, { status: 'unknown' }, undefined]) {
    const decision = summarizeStudyDecision(makeStudy(validation))
    assert.equal(decision.candidate, '尚无已验证候选')
    assert.match(decision.reason, /部署验证通过/)
  }
})

test('Study 部署状态将 passed、缺失、未知、运行与失败分为互不混淆的用户语义', () => {
  const base = { status: 'completed', is_deployable: true }
  assert.deepEqual(studyDeploymentEvidence({ ...base, deployment_validation: { status: 'passed' } }).label, '已通过部署验证')
  assert.deepEqual(studyDeploymentEvidence(base).label, '部署验证缺失，需复核')
  assert.deepEqual(studyDeploymentEvidence({ ...base, deployment_validation: { status: 'unknown' } }).label, '部署验证状态未知，需复核')
  assert.deepEqual(studyDeploymentEvidence({ ...base, deployment_validation: { status: 'running' } }).label, '部署验证未完成，需复核')
  assert.deepEqual(studyDeploymentEvidence({ ...base, deployment_validation: { status: 'failed' } }).label, '部署验证未通过')
  assert.deepEqual(studyDeploymentEvidence({ ...base, status: 'failed' }).label, '评估失败')
})

test('Study 非 completed 状态明确不形成完整成功任务的推荐口径', () => {
  for (const [status, expectedOverall] of [
    ['completed', '整体比较已完成。'],
    ['partial', '整体比较尚未完成；以下只展示已验证子结果，不能作为最终推荐。'],
    ['failed', '整体比较未完成；以下只展示已验证子结果，不能作为最终推荐。'],
    ['needs_review', '整体比较需要复核；以下只展示已验证子结果，不能作为最终推荐。'],
  ]) {
    const decision = summarizeStudyDecision({
      status,
      result: { deployment_evaluations: [{ architecture_name: 'linear-a', status: 'completed', is_deployable: true, deployment_validation: { status: 'passed' } }] },
    })
    assert.equal(decision.overall, expectedOverall)
    if (status === 'completed') assert.equal(decision.candidate, 'linear-a')
    else assert.equal(decision.candidate, '已验证子结果：linear-a')
  }
})

test('Bond Scan 下一步按科学最低点的边界证据分支，并保留三态部署结论', () => {
  const scan = minimum => ({ status: 'completed', result: { scientific_vqe_discrete_minimum: minimum, engineering_only_deployment: false } })
  const boundary = summarizeScanDecision(scan({ distance_angstrom: 1, minimum_at_boundary: true }))
  assert.match(boundary.next, /扩大扫描范围/)

  const interior = summarizeScanDecision(scan({ distance_angstrom: 1, minimum_at_boundary: false }))
  assert.match(interior.boundary, /范围内部/)
  assert.match(interior.next, /缩小该区间/)

  for (const minimum of [{ distance_angstrom: 1, minimum_at_boundary: null }, { distance_angstrom: 1 }]) {
    const decision = summarizeScanDecision(scan(minimum))
    assert.match(decision.boundary, /未知|未记录/)
    assert.match(decision.next, /旧记录字段、刷新结果或重新扫描/)
    assert.doesNotMatch(decision.minimum, /undefined Å/)
  }
  const missingDistance = summarizeScanDecision(scan({ minimum_at_boundary: false }))
  assert.match(missingDistance.boundary, /范围内部/)
  assert.doesNotMatch(missingDistance.minimum, /undefined Å/)
  assert.equal(boundary.deployment, '科学验证点部署')
})

test('Bond Scan 没有科学 VQE 最低点时不建议围绕距离细化', () => {
  const waiting = summarizeScanDecision({ status: 'running', result: { vqe_discrete_minimum: { distance_angstrom: 1, minimum_at_boundary: false }, engineering_only_deployment: null } })
  assert.match(waiting.boundary, /尚无科学 VQE 离散最低点/)
  assert.match(waiting.next, /等待/)
  assert.doesNotMatch(waiting.next, /缩小该区间|扩大扫描范围/)

  const review = summarizeScanDecision({ status: 'needs_review', result: { engineering_only_deployment: true } })
  assert.match(review.next, /复核科学验证/)
  assert.equal(review.deployment, '仅工程部署证据')
})
