<template>
  <div class="navbar">
    <div class="navbar-left">
      <!-- 折叠/展开侧边栏 -->
      <div class="hamburger" @click="$emit('toggle-sidebar')">
        <font-awesome-icon :icon="collapsed ? 'bars' : 'bars'" />
      </div>
      <!-- 面包屑导航 -->
      <el-breadcrumb separator="/" class="breadcrumb">
        <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
        <el-breadcrumb-item v-for="item in breadcrumbs" :key="item.path">
          <span v-if="item.to" class="breadcrumb-link" @click="$router.push(item.to)">{{ item.title }}</span>
          <span v-else>{{ item.title }}</span>
        </el-breadcrumb-item>
      </el-breadcrumb>
    </div>
    <div class="navbar-right">
      <el-dropdown trigger="click" class="user-dropdown" @command="handleCommand">
        <span class="user-trigger">
          <span class="user-avatar">
            <font-awesome-icon icon="user" />
          </span>
          <span class="user-name">{{ username }}</span>
          <font-awesome-icon icon="chevron-down" class="dropdown-arrow" />
        </span>
        <el-dropdown-menu slot="dropdown">
          <el-dropdown-item command="about">
            <font-awesome-icon icon="circle-info" /> 关于系统
          </el-dropdown-item>
          <el-dropdown-item divided command="logout">
            <font-awesome-icon icon="right-from-bracket" /> 退出登录
          </el-dropdown-item>
        </el-dropdown-menu>
      </el-dropdown>
    </div>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import { useAuthStore } from '@/stores/auth'

interface BreadcrumbItem {
  title: string
  path: string
  to?: string
}

/** 侧边栏分组标题映射 */
const GROUP_MAP: Record<string, string> = {
  '/datagen/config': '配置',
  '/datagen/httpsource': '配置',
  '/datagen/sqlsource': '配置',
  '/datagen/scenes': '编排',
  '/datagen/scene-history': '编排',
  '/datagen/tasks': '编排',
}

/**
 * 顶部导航栏：左侧折叠按钮 + 面包屑导航，右侧用户菜单下拉。
 * 面包屑根据当前路由的 meta.activeMenu 和 meta.title 自动推导分组和页面层级。
 */
export default Vue.extend({
  name: 'Navbar',
  props: {
    collapsed: { type: Boolean, default: false },
  },
  created() {
    const auth = useAuthStore()
    void auth.ensureUser()
  },
  computed: {
    username(): string {
      const auth = useAuthStore()
      return auth.user?.email || '管理员'
    },
    breadcrumbs(): BreadcrumbItem[] {
      const { meta, path } = this.$route
      const title = (meta?.title as string) || ''
      // activeMenu 指向父菜单路径（详情页使用），否则取当前 path
      const parentPath = (meta?.activeMenu as string) || path
      const group = GROUP_MAP[parentPath]

      const items: BreadcrumbItem[] = []
      if (group) {
        items.push({ title: group, path: group, to: parentPath })
      }
      if (title) {
        // 最后一项不带链接（当前页）
        items.push({ title, path: path })
      }
      return items
    },
  },
  methods: {
    handleCommand(command: string) {
      if (command === 'logout') {
        this.$confirm('确定要退出登录吗？', '提示', {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          type: 'warning',
        }).then(() => {
          const auth = useAuthStore()
          void auth.logout().finally(() => {
            this.$message.info('已退出登录')
            void this.$router.push('/login')
          })
        }).catch(() => {})
      } else if (command === 'about') {
        this.$message.info('造数工厂 - 数据工厂管理平台 v1.0')
      }
    },
  },
})
</script>

<style lang="scss" scoped>
.navbar {
  height: 50px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  background: var(--card);
  border-bottom: 1px solid var(--border);

  .navbar-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .navbar-right {
    display: flex;
    align-items: center;
    gap: 16px;
  }
}

.hamburger {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--foreground);
  transition: background-color 0.2s;

  &:hover {
    background-color: var(--accent);
  }
}

.breadcrumb {
  font-size: 13px;
}

.breadcrumb-link {
  cursor: pointer;
  color: var(--primary);

  &:hover {
    text-decoration: underline;
  }
}

.user-dropdown {
  cursor: pointer;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background-color 0.2s;

  &:hover {
    background-color: var(--accent);
  }
}

.user-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background-color: var(--primary);
  color: var(--primary-foreground);
  font-size: 12px;
}

.user-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
}

.dropdown-arrow {
  font-size: 10px;
  color: var(--muted-foreground);
}
</style>
