<template>
  <section ref="scrollContainer" class="app-main" @scroll="onScroll">
    <transition name="fade-transform" mode="out-in">
      <keep-alive :include="cachedViews">
        <router-view :key="key" />
      </keep-alive>
    </transition>
  </section>
</template>

<script lang="ts">
import Vue from 'vue'
import { mapState } from 'pinia'
import { useTagsViewStore } from '@/stores/tagsView'

/**
 * 渲染路由组件并使用 keep-alive 保持标签页状态。
 * 支持滚动位置恢复：切换标签时自动保存/恢复滚动位置。
 */
export default Vue.extend({
  name: 'AppMain',
  data() {
    return {
      // 存储每个路由的滚动位置
      scrollPositions: new Map<string, number>(),
    }
  },
  computed: {
    ...mapState(useTagsViewStore, ['cachedViews']),
    key(): string {
      return this.$route.path
    },
  },
  watch: {
    // 路由切换前保存滚动位置
    '$route'(to, from) {
      if (from && this.$refs.scrollContainer) {
        const container = this.$refs.scrollContainer as HTMLElement
        this.scrollPositions.set(from.path, container.scrollTop)
      }
    },
  },
  mounted() {
    // 路由切换后恢复滚动位置
    this.$router.afterEach((to) => {
      this.$nextTick(() => {
        if (this.$refs.scrollContainer) {
          const container = this.$refs.scrollContainer as HTMLElement
          const savedPosition = this.scrollPositions.get(to.path) || 0
          container.scrollTop = savedPosition
        }
      })
    })
  },
  methods: {
    onScroll() {
      // 滚动事件监听，位置在 watch $route 中保存
    },
  },
})
</script>

<style scoped>
.app-main {
  /* Full viewport minus navbar (50px) + tags-view (34px). */
  height: calc(100vh - 84px);
  width: 100%;
  position: relative;
  overflow: hidden;
}

.fade-transform-leave-active,
.fade-transform-enter-active {
  transition: all 0.3s;
}

.fade-transform-enter {
  opacity: 0;
  transform: translateX(-12px);
}

.fade-transform-leave-to {
  opacity: 0;
  transform: translateX(12px);
}
</style>
