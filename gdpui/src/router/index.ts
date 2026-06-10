import Vue from 'vue'
import VueRouter, { type RouteConfig } from 'vue-router'

import { buildLoginPath, validateNextParam } from '@/auth/types'
import Layout from '@/layout/index.vue'
import pinia from '@/stores'
import { useAuthStore } from '@/stores/auth'

Vue.use(VueRouter)

const DEFAULT_AUTH_REDIRECT = '/datagen/scenes'

const routes: RouteConfig[] = [
  { path: '/', redirect: '/datagen/scenes' },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/setup',
    name: 'Setup',
    component: () => import('@/views/SetupView.vue'),
    meta: { title: '初始化', public: true },
  },
  {
    path: '/datagen',
    component: Layout,
    redirect: '/datagen/scenes',
    children: [
      // ── 编排 ──
      {
        path: 'scenes',
        name: 'SceneDashboard',
        component: () => import('@/datagen/views/scene-dashboard.vue'),
        meta: { title: '造数场景', icon: 'list', affix: true },
      },
      {
        path: 'scene-history',
        name: 'SceneRunHistory',
        component: () => import('@/datagen/views/scene-run-history.vue'),
        meta: { title: '执行历史', icon: 'clock-rotate-left' },
      },
      {
        path: 'tasks',
        name: 'TaskDashboard',
        component: () => import('@/datagen/views/task-dashboard.vue'),
        meta: { title: '造数任务', icon: 'diagram-project' },
      },
      // ── 配置 ──
      {
        path: 'config',
        name: 'ConfigManagement',
        component: () => import('@/datagen/views/config-management.vue'),
        meta: { title: '基础配置', icon: 'gear' },
      },
      {
        path: 'httpsource',
        name: 'HttpSourceManagement',
        component: () => import('@/datagen/views/http-source-management.vue'),
        meta: { title: 'HTTP 接口', icon: 'globe' },
      },
      {
        path: 'sqlsource',
        name: 'SqlSourceManagement',
        component: () => import('@/datagen/views/sql-source-management.vue'),
        meta: { title: 'SQL 配置', icon: 'database' },
      },

      // ── 动态详情标签（场景）──
      {
        path: 'scene/new',
        name: 'SceneCreate',
        component: () => import('@/datagen/views/scene-editor.vue'),
        meta: { title: '新增场景', activeMenu: '/datagen/scenes', noCache: true },
      },
      {
        path: 'scene/edit/:code',
        name: 'SceneEdit',
        component: () => import('@/datagen/views/scene-editor.vue'),
        meta: { title: '编辑场景', activeMenu: '/datagen/scenes', noCache: true },
      },
      {
        path: 'scene/view/:code',
        name: 'SceneView',
        component: () => import('@/datagen/views/scene-editor.vue'),
        meta: { title: '查看场景', activeMenu: '/datagen/scenes', noCache: true },
      },
      {
        path: 'scene/run/:code',
        name: 'SceneRun',
        component: () => import('@/datagen/views/scene-execution.vue'),
        meta: { title: '执行场景', activeMenu: '/datagen/scenes', noCache: true },
      },

      // ── 动态详情标签（任务）──
      {
        path: 'task/new',
        name: 'TaskCreate',
        component: () => import('@/datagen/views/task-editor.vue'),
        meta: { title: '新增任务', activeMenu: '/datagen/tasks', noCache: true },
      },
      {
        path: 'task/edit/:code',
        name: 'TaskEdit',
        component: () => import('@/datagen/views/task-editor.vue'),
        meta: { title: '编辑任务', activeMenu: '/datagen/tasks', noCache: true },
      },
      {
        path: 'task/view/:code',
        name: 'TaskView',
        component: () => import('@/datagen/views/task-editor.vue'),
        meta: { title: '查看任务', activeMenu: '/datagen/tasks', noCache: true },
      },
    ],
  },
  {
    // 未匹配路由
    path: '*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
  },
]

const router = new VueRouter({
  mode: 'history',
  base: import.meta.env.BASE_URL,
  routes,
})

router.beforeEach(async (to, _from, next) => {
  const auth = useAuthStore(pinia)
  const isPublic = !!to.matched.some((record) => record.meta?.public)

  if (isPublic) {
    next()
    return
  }

  const user = await auth.ensureUser()
  if (!user) {
    next(buildLoginPath(to.fullPath || DEFAULT_AUTH_REDIRECT))
    return
  }

  if (user.needs_setup) {
    next('/setup')
    return
  }

  next()
})

router.afterEach((to) => {
  const code = to.params.code
  if (code && to.meta && typeof to.meta.title === 'string') {
    const base = to.meta.title.replace(/[:：].*$/, '')
    to.meta.title = `${base}: ${code}`
  }
  // 同步更新浏览器标签页标题
  const title = (to.meta?.title as string) || '造数工厂'
  document.title = `${title} - 造数工厂`
})

router.onReady(async () => {
  const auth = useAuthStore(pinia)
  const nextPath = validateNextParam(router.currentRoute.query.next)
  if (router.currentRoute.path === '/login' && auth.user && nextPath) {
    await router.replace(nextPath)
  }
})

export default router
