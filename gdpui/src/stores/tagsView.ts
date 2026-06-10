import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { Route } from 'vue-router'

/**
 * 标签页状态管理，参考 vue-element-admin 的 tagsView Vuex 模块改用 Pinia。
 * affix 标签（如首页）固定不可关闭；cachedViews 控制 keep-alive 缓存。
 * visitedViews 会持久化到 localStorage，刷新浏览器后可恢复。
 */

const STORAGE_KEY = 'gdpui_tags_views'

export interface VisitedView {
  path: string
  fullPath: string
  name?: string | null
  title: string
  query: Route['query']
  affix: boolean
  /** 为 false 时组件不会被 keep-alive 缓存 */
  noCache: boolean
}

/** 路由对象的最小形状，用于注册标签页 */
export interface TagRoute {
  path: string
  fullPath: string
  name?: string | null
  query: Route['query']
  meta?: {
    title?: string
    affix?: boolean
    noCache?: boolean
  }
}

function toVisitedView(route: TagRoute): VisitedView {
  return {
    path: route.path,
    fullPath: route.fullPath,
    name: route.name ?? null,
    title: route.meta?.title || 'no-name',
    query: route.query ?? {},
    affix: !!route.meta?.affix,
    noCache: !!route.meta?.noCache,
  }
}

/** 从 localStorage 恢复已访问的标签页列表 */
function loadFromStorage(): VisitedView[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as VisitedView[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 将当前标签页列表持久化到 localStorage */
function saveToStorage(views: VisitedView[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(views))
  } catch {
    /* 忽略存储异常（隐私模式等） */
  }
}

export const useTagsViewStore = defineStore('tagsView', () => {
  const visitedViews = ref<VisitedView[]>(loadFromStorage())
  const cachedViews = ref<string[]>([])

  // 监听 visitedViews 变更，自动持久化到 localStorage
  watch(visitedViews, (val) => saveToStorage(val), { deep: true })

  /* ── add ── */

  function addVisitedView(route: TagRoute) {
    if (visitedViews.value.some((v) => v.path === route.path)) return
    visitedViews.value.push(toVisitedView(route))
  }

  function addCachedView(route: TagRoute) {
    const name = route.name
    if (!name) return
    if (cachedViews.value.includes(name)) return
    if (!route.meta?.noCache) cachedViews.value.push(name)
  }

  function addView(route: TagRoute) {
    addVisitedView(route)
    addCachedView(route)
  }

  /* ── delete single ── */

  function delVisitedView(view: VisitedView) {
    const idx = visitedViews.value.findIndex((v) => v.path === view.path)
    if (idx > -1) visitedViews.value.splice(idx, 1)
  }

  function delCachedView(view: VisitedView) {
    if (!view.name) return
    const idx = cachedViews.value.indexOf(view.name)
    if (idx > -1) cachedViews.value.splice(idx, 1)
  }

  function delView(view: VisitedView) {
    delVisitedView(view)
    delCachedView(view)
    return { visitedViews: [...visitedViews.value], cachedViews: [...cachedViews.value] }
  }

  /* ── delete others ── */

  function delOthersViews(view: VisitedView) {
    visitedViews.value = visitedViews.value.filter((v) => v.affix || v.path === view.path)
    if (view.name) {
      const idx = cachedViews.value.indexOf(view.name)
      cachedViews.value = idx > -1 ? cachedViews.value.slice(idx, idx + 1) : []
    } else {
      cachedViews.value = []
    }
    return { visitedViews: [...visitedViews.value], cachedViews: [...cachedViews.value] }
  }

  /* ── delete all ── */

  function delAllViews() {
    visitedViews.value = visitedViews.value.filter((v) => v.affix)
    cachedViews.value = []
    return { visitedViews: [...visitedViews.value], cachedViews: [...cachedViews.value] }
  }

  /* ── delete to one side ── */

  function delLeftViews(view: VisitedView) {
    const idx = visitedViews.value.findIndex((v) => v.path === view.path)
    if (idx === -1) return { visitedViews: [...visitedViews.value] }
    visitedViews.value = visitedViews.value.filter(
      (v, i) => v.affix || i >= idx,
    )
    syncCacheToVisited()
    return { visitedViews: [...visitedViews.value], cachedViews: [...cachedViews.value] }
  }

  function delRightViews(view: VisitedView) {
    const idx = visitedViews.value.findIndex((v) => v.path === view.path)
    if (idx === -1) return { visitedViews: [...visitedViews.value] }
    visitedViews.value = visitedViews.value.filter(
      (v, i) => v.affix || i <= idx,
    )
    syncCacheToVisited()
    return { visitedViews: [...visitedViews.value], cachedViews: [...cachedViews.value] }
  }

  /** Drop cached names that no longer have a corresponding visited view. */
  function syncCacheToVisited() {
    const liveNames = new Set(
      visitedViews.value.map((v) => v.name).filter(Boolean) as string[],
    )
    cachedViews.value = cachedViews.value.filter((n) => liveNames.has(n))
  }

  /* ── update (e.g. query changed for same path) ── */

  function updateVisitedView(route: TagRoute) {
    const target = visitedViews.value.find((v) => v.path === route.path)
    if (target) Object.assign(target, toVisitedView(route))
  }

  return {
    visitedViews,
    cachedViews,
    addView,
    addVisitedView,
    addCachedView,
    delView,
    delVisitedView,
    delCachedView,
    delOthersViews,
    delAllViews,
    delLeftViews,
    delRightViews,
    updateVisitedView,
  }
})
