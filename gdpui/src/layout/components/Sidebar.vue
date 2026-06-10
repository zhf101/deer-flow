<template>
  <aside class="sidebar-container" :class="{ collapsed }">
    <div class="sidebar-brand">
      <font-awesome-icon icon="industry" class="brand-icon" />
      <div v-if="!collapsed" class="brand-text">
        <h2>造数工厂</h2>
        <p>数据工厂管理平台</p>
      </div>
    </div>

    <el-menu
      :default-active="activeMenu"
      :unique-opened="false"
      :collapse="collapsed"
      mode="vertical"
      class="sidebar-menu"
      @select="handleSelect"
    >
      <template v-for="group in groups">
        <div v-if="!collapsed" :key="group.title" class="menu-group-label">{{ group.title }}</div>
        <el-menu-item
          v-for="item in group.items"
          :key="item.path"
          :index="item.path"
        >
          <font-awesome-icon :icon="item.icon" class="menu-icon" />
          <span slot="title">{{ item.title }}</span>
        </el-menu-item>
      </template>
    </el-menu>
  </aside>
</template>

<script lang="ts">
import Vue from 'vue'

interface NavItem {
  path: string
  title: string
  icon: string
}

interface NavGroup {
  title: string
  items: NavItem[]
}

/**
 * 分组导航菜单，对应 React 源码的 NAV_ITEMS（配置 / 编排）。
 * 选中菜单项时路由到对应列表页；activeMenu 由路由 meta.activeMenu 决定，
 * 使详情标签（如场景编辑/查看）仍能高亮其父菜单项。
 * 支持 collapsed 折叠模式：仅显示图标 + tooltip。
 */
const GROUPS: NavGroup[] = [
  {
    title: '配置',
    items: [
      { path: '/datagen/config', title: '基础配置', icon: 'gear' },
      { path: '/datagen/httpsource', title: 'HTTP 接口', icon: 'globe' },
      { path: '/datagen/sqlsource', title: 'SQL 配置', icon: 'database' },
    ],
  },
  {
    title: '编排',
    items: [
      { path: '/datagen/scenes', title: '造数场景', icon: 'list' },
      { path: '/datagen/scene-history', title: '执行历史', icon: 'clock-rotate-left' },
      { path: '/datagen/tasks', title: '造数任务', icon: 'diagram-project' },
    ],
  },
]

export default Vue.extend({
  name: 'AppSidebar',
  props: {
    collapsed: { type: Boolean, default: false },
  },
  data() {
    return { groups: GROUPS }
  },
  computed: {
    activeMenu(): string {
      const { meta, path } = this.$route
      return (meta && (meta.activeMenu as string)) || path
    },
  },
  methods: {
    handleSelect(index: string) {
      if (index !== this.$route.path) {
        this.$router.push(index).catch(() => {})
      }
    },
  },
})
</script>

<style scoped>
.sidebar-container {
  height: 100vh;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background-color: var(--card);
  border-right: 1px solid var(--border);
  overflow: hidden;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  overflow: hidden;
}

.collapsed .sidebar-brand {
  justify-content: center;
  padding: 14px 0;
}

.brand-icon {
  font-size: 20px;
  color: var(--foreground);
  flex-shrink: 0;
}

.brand-text h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--foreground);
}

.brand-text p {
  margin: 2px 0 0;
  font-size: 10px;
  color: var(--muted-foreground);
}

.sidebar-menu {
  flex: 1;
  border-right: none;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px;
  background-color: transparent;
}

.collapsed .sidebar-menu {
  padding: 8px 4px;
}

.menu-group-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted-foreground);
  padding: 12px 8px 4px;
}

.menu-icon {
  width: 16px;
  margin-right: 10px;
}

.collapsed .menu-icon {
  margin-right: 0;
}

/* Element UI menu item overrides to match the token-driven theme. */
.sidebar-menu >>> .el-menu-item {
  height: 38px;
  line-height: 38px;
  border-radius: 6px;
  margin-bottom: 2px;
  font-size: 13px;
  color: var(--muted-foreground);
}

.sidebar-menu >>> .el-menu-item:hover {
  background-color: var(--accent);
  color: var(--foreground);
}

.sidebar-menu >>> .el-menu-item.is-active {
  background-color: var(--accent);
  color: var(--foreground);
  font-weight: 600;
}

/* 折叠模式下 el-menu 宽度覆盖 */
.sidebar-menu:not(.el-menu--collapse) {
  width: 100%;
}
</style>
