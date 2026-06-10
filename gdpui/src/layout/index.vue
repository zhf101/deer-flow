<template>
  <div class="app-wrapper" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <sidebar :collapsed="sidebarCollapsed" class="sidebar-container" />
    <div class="main-container">
      <div class="fixed-header">
        <navbar :collapsed="sidebarCollapsed" @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed" />
        <tags-view />
      </div>
      <app-main />
    </div>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'
import AppMain from './components/AppMain.vue'
import Navbar from './components/Navbar.vue'
import Sidebar from './components/Sidebar.vue'
import TagsView from './components/TagsView.vue'

/**
 * 后台管理主框架：固定左侧导航栏（可折叠）+ 主内容区（Navbar + TagsView + AppMain）。
 * 参考 vue-element-admin 的 Layout 结构，支持侧边栏折叠/展开。
 */
export default Vue.extend({
  name: 'AppLayout',
  components: { AppMain, Navbar, Sidebar, TagsView },
  data() {
    return {
      sidebarCollapsed: false,
    }
  },
})
</script>

<style lang="scss" scoped>
.app-wrapper {
  position: relative;
  height: 100%;
  width: 100%;
  display: flex;
}

.sidebar-container {
  width: 200px;
  flex-shrink: 0;
  transition: width 0.28s ease;
}

.sidebar-collapsed .sidebar-container {
  width: 64px;
}

.main-container {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.fixed-header {
  flex-shrink: 0;
  z-index: 9;
}
</style>
