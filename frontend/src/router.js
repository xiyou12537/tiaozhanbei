import { createRouter, createWebHistory } from 'vue-router'
import Layout from './views/Layout.vue'
import HistoryPage from './views/HistoryPage.vue'
import HomePage from './views/HomePage.vue'
import WorkbenchPage from './views/WorkbenchPage.vue'
import CapabilityPage from './views/CapabilityPage.vue'
import SystemPreviewPage from './views/SystemPreviewPage.vue'

const routes = [
  { path: '/', component: HomePage, meta: { title: '平台总览' } },
  // /login 和 /register 重定向到首页弹窗，保留直接路径可用性
  { path: '/login', redirect: '/?auth=login' },
  { path: '/register', redirect: '/?auth=register' },
  {
    path: '/app',
    component: Layout,
    redirect: '/app/workbench',
    children: [
      { path: 'preview', component: SystemPreviewPage, meta: { title: '系统蓝图' } },
      { path: 'overview', component: HomePage, meta: { title: '项目介绍' } },
      { path: 'workbench', component: WorkbenchPage, meta: { title: '实验工作台' } },
      { path: 'capability', component: CapabilityPage, meta: { title: '编译能力页' } },
      { path: 'partition', redirect: '/app/capability?tab=partition' },
      { path: 'mapping', redirect: '/app/capability?tab=mapping' },
      { path: 'history', component: HistoryPage, meta: { title: '历史记录' } },
      { path: 'chat', component: () => import('./views/ChatPage.vue'), meta: { title: 'AI助手' } },
    ],
  },
]

const router = createRouter({ history: createWebHistory(), routes })

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.path.startsWith('/app') && !token) next('/?auth=login')
  else next()
})

export default router
