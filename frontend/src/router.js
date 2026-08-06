import { createRouter, createWebHistory } from 'vue-router'
import AppLayout from './layouts/AppLayout.vue'
import PublicLayout from './layouts/PublicLayout.vue'
import { hasAuthSession } from './services/authStorage'

const HomePage = () => import('./views/HomePage.vue')
const AuthPage = () => import('./views/AuthPage.vue')
const OverviewPage = () => import('./views/OverviewPage.vue')
const WorkflowPage = () => import('./views/WorkflowPage.vue')
const ResultsPage = () => import('./views/ResultsPage.vue')
const ArchitecturePage = () => import('./views/ArchitecturePage.vue')
const HighlightsPage = () => import('./views/HighlightsPage.vue')
const ScreeningPage = () => import('./views/ScreeningPage.vue')
const StructureWorkbenchPage = () => import('./views/StructureWorkbenchPage.vue')
const WorkbenchPage = () => import('./views/WorkbenchPage.vue')
const AppResultsPage = () => import('./views/AppResultsPage.vue')
const CapabilityPage = () => import('./views/CapabilityPage.vue')
const HistoryPage = () => import('./views/HistoryPage.vue')
const KnowledgePage = () => import('./views/KnowledgePage.vue')
const ResearchBenchmarksPage = () => import('./views/ResearchBenchmarksPage.vue')
const StructureWorkflowDetailPage = () => import('./views/StructureWorkflowDetailPage.vue')
const MoleculesPage = () => import('./views/MoleculesPage.vue')
const MoleculeWorkflowHistoryPage = () => import('./views/MoleculeWorkflowHistoryPage.vue')
const MoleculeWorkflowResultPage = () => import('./views/MoleculeWorkflowResultPage.vue')

const routes = [
  {
    path: '/',
    component: PublicLayout,
    children: [
      { path: '', component: HomePage, meta: { title: '\u91cf\u667a\u786b\u5149' } },
      { path: 'auth', component: AuthPage, meta: { title: '\u8d26\u53f7\u4e2d\u5fc3' } },
      { path: 'overview', component: OverviewPage, meta: { title: '\u9879\u76ee\u6982\u89c8' } },
      { path: 'about', redirect: '/overview' },
      { path: 'workflow', component: WorkflowPage, meta: { title: '\u6d41\u7a0b' } },
      { path: 'results', component: ResultsPage, meta: { title: '\u7ed3\u679c' } },
      { path: 'architecture', component: ArchitecturePage, meta: { title: '\u67b6\u6784' } },
      { path: 'highlights', component: HighlightsPage, meta: { title: '\u80fd\u529b\u4eae\u70b9' } },
    ],
  },
  { path: '/login', redirect: '/auth?tab=login' },
  { path: '/register', redirect: '/auth?tab=register' },
  {
    path: '/app',
    component: AppLayout,
    redirect: '/app/molecules',
    children: [
      { path: 'preview', redirect: '/app/molecules' },
      { path: 'overview', redirect: '/overview' },
      { path: 'molecules', component: MoleculesPage, meta: { title: '小分子量子计算' } },
      { path: 'molecule-workflows', component: MoleculeWorkflowHistoryPage, meta: { title: '计算任务' } },
      { path: 'molecule-workflows/:workflowId', component: MoleculeWorkflowResultPage, meta: { title: '分子计算结果' } },
      { path: 'screening', component: ScreeningPage, meta: { title: '\u591a\u6750\u6599\u7b5b\u9009' } },
      { path: 'structure-workbench', component: StructureWorkbenchPage, meta: { title: '\u5316\u5b66\u7b5b\u9009\u4e0e\u91cf\u5b50\u8ba1\u7b97' } },
      { path: 'research-benchmarks', component: ResearchBenchmarksPage, meta: { title: '\u6587\u732e\u57fa\u51c6' } },
      { path: 'research-benchmarks/:benchmarkId', component: ResearchBenchmarksPage, meta: { title: '\u6587\u732e\u5019\u9009\u6784\u578b' } },
      { path: 'structure-workflows/:workflowId', component: StructureWorkflowDetailPage, meta: { title: '\u6587\u732e\u590d\u73b0\u5de5\u4f5c\u6d41' } },
      { path: 'workbench', component: WorkbenchPage, meta: { title: '\u5de5\u4f5c\u53f0' } },
      { path: 'results', component: AppResultsPage, meta: { title: '\u7b5b\u9009\u7ed3\u679c' } },
      { path: 'knowledge', component: KnowledgePage, meta: { title: '\u77e5\u8bc6\u5e93' } },
      { path: 'capability', component: CapabilityPage, meta: { title: '\u7f16\u8bd1\u80fd\u529b' } },
      { path: 'partition', redirect: '/app/capability?tab=partition' },
      { path: 'mapping', redirect: '/app/capability?tab=mapping' },
      { path: 'history', component: HistoryPage, meta: { title: '\u5386\u53f2' } },
      { path: 'chat', redirect: '/app/knowledge' },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const requiresAuth = to.path.startsWith('/app')

  if (requiresAuth && !hasAuthSession()) {
    next({ path: '/auth', query: { tab: 'login', redirect: to.fullPath } })
    return
  }

  next()
})

router.afterEach(to => {
  const appTitle = '\u91cf\u667a\u786b\u5149'
  document.title = to.meta?.title ? `${to.meta.title} - ${appTitle}` : appTitle
})

export default router
