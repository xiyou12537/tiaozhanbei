import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from './layouts/AppLayout.vue'
import PublicLayout from './layouts/PublicLayout.vue'
import { hasAuthSession } from './services/authStorage'

const HomePage = () => import('./views/HomePage.vue')
const WorkbenchPage = () => import('./views/WorkbenchPage.vue')
const AuthPage = () => import('./views/AuthPage.vue')
const MoleculesPage = () => import('./views/MoleculesPage.vue')
const MoleculeWorkflowHistoryPage = () => import('./views/MoleculeWorkflowHistoryPage.vue')
const MoleculeWorkflowResultPage = () => import('./views/MoleculeWorkflowResultPage.vue')
const MolecularStudyCreatePage = () => import('./views/MolecularStudyCreatePage.vue')
const MolecularStudyResultPage = () => import('./views/MolecularStudyResultPage.vue')
const MolecularBondScanCreatePage = () => import('./views/MolecularBondScanCreatePage.vue')
const MolecularBondScanResultPage = () => import('./views/MolecularBondScanResultPage.vue')
const SimulationCapabilitiesPage = () => import('./views/SimulationCapabilitiesPage.vue')
const MolecularCopilotPage = () => import('./views/MolecularCopilotPage.vue')

const routes = [
  {
    path: '/',
    component: PublicLayout,
    children: [
      { path: '', component: HomePage, meta: { title: '分子量子分布式计算平台' } },
      { path: 'auth', component: AuthPage, meta: { title: '账户中心' } },
    ],
  },
  { path: '/login', redirect: '/auth?tab=login' },
  { path: '/register', redirect: '/auth?tab=register' },
  {
    path: '/app',
    component: AppLayout,
    children: [
      { path: '', component: WorkbenchPage, meta: { title: '工作台', eyebrow: 'Molecular compute workbench' } },
      { path: 'molecules', component: MoleculesPage, meta: { title: '新建分子计算', eyebrow: 'Create workflow' } },
      { path: 'molecule-workflows', component: MoleculeWorkflowHistoryPage, meta: { title: '计算任务', eyebrow: 'Workflow ledger' } },
      { path: 'molecule-workflows/:workflowId', component: MoleculeWorkflowResultPage, meta: { title: 'Workflow 结果', eyebrow: 'Execution evidence' } },
      { path: 'molecular-studies/new', component: MolecularStudyCreatePage, meta: { title: '新建部署评估', eyebrow: 'Deployment study' } },
      { path: 'molecular-studies/:studyId', component: MolecularStudyResultPage, meta: { title: '部署评估报告', eyebrow: 'Deployment report' } },
      { path: 'molecular-bond-scans/new', component: MolecularBondScanCreatePage, meta: { title: '新建势能扫描', eyebrow: 'Potential energy scan' } },
      { path: 'molecular-bond-scans/:scanId', component: MolecularBondScanResultPage, meta: { title: '势能扫描结果', eyebrow: 'Bond scan report' } },
      { path: 'simulation-capabilities', component: SimulationCapabilitiesPage, meta: { title: '模拟能力说明', eyebrow: 'Capability contract' } },
      { path: 'copilot', component: MolecularCopilotPage, meta: { title: 'Molecular Copilot', eyebrow: 'Controlled assistant' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach(to => {
  if (to.path.startsWith('/app') && !hasAuthSession()) {
    return { path: '/auth', query: { tab: 'login', redirect: to.fullPath } }
  }
  return true
})

router.afterEach(to => {
  const appTitle = '分子量子分布式计算平台'
  document.title = to.meta?.title ? `${to.meta.title} · ${appTitle}` : appTitle
})

export default router
