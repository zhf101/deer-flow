<template>
  <div class="placeholder">
    <font-awesome-icon :icon="icon" class="placeholder-icon" />
    <h2>{{ title }}</h2>
    <p>该模块尚未迁移。占位页面用于验证标签页导航与 keep-alive 缓存。</p>
    <p class="route-path">{{ $route.fullPath }}</p>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

/**
 * Temporary stand-in for modules not yet ported. Its `name` is intentionally
 * generic; the router assigns each route a distinct component name via the
 * route's own `name`, so keep-alive still distinguishes tabs by route name.
 *
 * NOTE: because every placeholder route points at this same component, they
 * share one component definition — fine for a placeholder, but real modules
 * each get their own component file with a unique `name`.
 */
export default Vue.extend({
  name: 'DatagenPlaceholder',
  computed: {
    title(): string {
      return (this.$route.meta?.title as string) || '未命名模块'
    },
    icon(): string {
      return (this.$route.meta?.icon as string) || 'screwdriver-wrench'
    },
  },
})
</script>

<style scoped>
.placeholder {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--muted-foreground);
  background: var(--background);
}

.placeholder-icon {
  font-size: 40px;
  color: var(--muted-foreground);
  opacity: 0.5;
  margin-bottom: 8px;
}

.placeholder h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--foreground);
}

.placeholder p {
  margin: 0;
  font-size: 13px;
}

.route-path {
  font-family: monospace;
  font-size: 12px;
  opacity: 0.7;
}
</style>
