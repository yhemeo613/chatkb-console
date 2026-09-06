import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import http from '../api'

const routes = [
  { path: '/login', name: '登录', component: () => import('../views/LoginView.vue') },
  { path: '/register', name: '注册', component: () => import('../views/RegisterView.vue') },
  {
    path: '/',
    component: () => import('../layouts/BasicLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: '工作台', component: () => import('../views/Dashboard.vue') },
      { path: 'kbs', name: '知识库管理', component: () => import('../views/KbList.vue'), meta: { perm: 'kb' } },
      { path: 'kbs/:id', name: '知识库详情', component: () => import('../views/KbDetail.vue'), meta: { perm: 'kb' } },
      { path: 'reply', name: '对话回复', component: () => import('../views/ReplyView.vue') },
      { path: 'search', name: '语义搜索', component: () => import('../views/SearchView.vue') },
      { path: 'profiles', name: '个人档案', component: () => import('../views/ProfilesView.vue'), meta: { perm: 'profile' } },
      { path: 'system/users', name: '账号管理', component: () => import('../views/system/UsersView.vue'), meta: { perm: 'sys:user' } },
      { path: 'system/roles', name: '角色管理', component: () => import('../views/system/RolesView.vue'), meta: { perm: 'sys:role' } },
      { path: 'system/menus', name: '菜单管理', component: () => import('../views/system/MenusView.vue'), meta: { perm: 'sys:menu' } },
      { path: 'llm', name: '模型中心', component: () => import('../views/llm/LlmView.vue') },
      { path: 'ext/db', name: '数据库管理', component: () => import('../views/ext/DbView.vue'), meta: { perm: 'ext:db' } },
      { path: 'ext/redis', name: 'Redis管理', component: () => import('../views/ext/RedisView.vue'), meta: { perm: 'ext:redis' } },
      { path: 'ext/skills', name: '技能管理', component: () => import('../views/ext/SkillsView.vue'), meta: { perm: 'ext:skills' } },
      { path: 'ext/plugins', name: '插件管理', component: () => import('../views/ext/PluginsView.vue'), meta: { perm: 'ext:plugins' } },
      { path: 'ext/mcp', name: 'MCP接入', component: () => import('../views/ext/McpView.vue'), meta: { perm: 'ext:mcp' } },
      { path: 'ext/canvas', name: '编排画布', component: () => import('../views/ext/CanvasView.vue'), meta: { perm: 'ext:canvas' } },
      { path: 'ops/status', name: '服务状态', component: () => import('../views/ops/OpsStatusView.vue'), meta: { perm: 'ops:status' } },
      { path: 'ops/tasks', name: '任务中心', component: () => import('../views/ops/TasksView.vue'), meta: { perm: 'ops:tasks' } },
      { path: 'ops/logs', name: '操作日志', component: () => import('../views/ops/AuditLogsView.vue'), meta: { perm: 'ops:logs' } },
      { path: 'settings', name: '系统设置', component: () => import('../views/SettingsView.vue'), meta: { perm: 'sys:menu' } },
    ],
  },
  { path: '/:pathMatch(.*)*', name: '404', component: () => import('../views/ForbiddenView.vue') },
]

const router = createRouter({ routes, history: createWebHistory() })

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.path === '/login' || to.path === '/register') {
    if (auth.isLoggedIn && to.path === '/login') return { path: '/dashboard' }
    return true
  }
  if (!auth.isLoggedIn) return { path: '/login' }
  try {
    await auth.ensure() // 硬刷新后恢复用户/权限/菜单
  } catch {
    auth.logout()
    return { path: '/login' }
  }
  // 页面级权限：菜单权限码不匹配则 403
  if (to.meta?.perm && !auth.hasPerm(to.meta.perm)) return { path: '/403' }
  return true
})

export default router
