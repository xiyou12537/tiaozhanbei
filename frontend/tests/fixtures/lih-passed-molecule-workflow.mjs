import h2Fixture from './h2-molecule-workflow.json' with { type: 'json' }

const fixture = structuredClone(h2Fixture)

fixture.workflow_id = 'molwf_lih_passed_fixture'
fixture.validation_status = 'passed'
fixture.validation_issues = []
fixture.molecule = {
  ...fixture.molecule,
  molecule_name: 'LiH',
  geometry: [
    { element: 'Li', coordinates_angstrom: [0, 0, 0] },
    { element: 'H', coordinates_angstrom: [0, 0, 1.595] },
  ],
}
fixture.vqe = {
  ...fixture.vqe,
  optimizer: 'Powell',
  converged: true,
  optimizer_diagnostics: {
    scipy_success: true,
    scipy_status: 0,
    scipy_message: 'Optimization terminated successfully.',
    nfev: 142,
    termination_reason: 'optimizer_reported_success',
    best_iteration: 117,
    initial_energy_hartree: -7.6,
    final_energy_hartree: -7.8821,
    recent_energy_changes_hartree: [-0.0012, -0.00008, -0.000001],
  },
}

export default fixture
