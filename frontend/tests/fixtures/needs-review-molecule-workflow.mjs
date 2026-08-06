import h2Fixture from './h2-molecule-workflow.json' with { type: 'json' }

const fixture = structuredClone(h2Fixture)

fixture.workflow_id = 'molwf_needs_review_fixture'
fixture.validation_status = 'needs_review'
fixture.validation_issues = [
  {
    code: 'vqe_not_converged',
    stage: 'vqe_optimization',
    iteration_count: 80,
    message: 'VQE 优化器未报告收敛，需要复核能量曲线和终止诊断。',
  },
]
fixture.vqe = {
  ...fixture.vqe,
  optimizer: 'Powell',
  converged: false,
  optimizer_diagnostics: {
    scipy_success: false,
    scipy_status: 2,
    scipy_message: 'Maximum number of iterations has been exceeded.',
    nfev: 131,
    termination_reason: 'scipy_status_2',
    best_iteration: 74,
    initial_energy_hartree: -1.1,
    final_energy_hartree: -1.1198,
    recent_energy_changes_hartree: [-0.0002, -0.00003, -0.000001],
  },
}

export default fixture
