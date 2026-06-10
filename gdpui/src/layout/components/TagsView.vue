<template>
  <div id="tags-view-container" class="tags-view-container">
    <scroll-pane ref="scrollPane" class="tags-view-wrapper" @scroll="handleScroll">
      <router-link
        v-for="tag in visitedViews"
        ref="tag"
        :key="tag.path"
        :class="isActive(tag) ? 'active' : ''"
        :to="{ path: tag.path, query: tag.query }"
        tag="span"
        class="tags-view-item"
        @click.middle.native="!tag.affix ? closeSelectedTag(tag) : ''"
        @contextmenu.prevent.native="openMenu(tag, $event)"
      >
        {{ tag.title }}
        <i
          v-if="!tag.affix"
          class="el-icon-close"
          @click.prevent.stop="closeSelectedTag(tag)"
        />
      </router-link>
    </scroll-pane>

    <ul
      v-show="visible"
      :style="{ left: left + 'px', top: top + 'px' }"
      class="contextmenu"
    >
      <li :class="{ disabled: !canCloseSelf }" @click="onCloseSelf">关闭</li>
      <li :class="{ disabled: !canCloseOthers }" @click="onCloseOthers">关闭其他</li>
      <li :class="{ disabled: !canCloseLeft }" @click="onCloseLeft">关闭左侧</li>
      <li :class="{ disabled: !canCloseRight }" @click="onCloseRight">关闭右侧</li>
      <li @click="onCloseAll">关闭全部</li>
    </ul>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'
import { mapState } from 'pinia'

import { useTagsViewStore, type VisitedView } from '@/stores/tagsView'
import ScrollPane from './ScrollPane.vue'

/**
 * Route-driven tab bar. Adapted from vue-element-admin's TagsView:
 * - watches `$route` to add/activate tabs and scroll the active one into view
 * - right-click opens a context menu (close self/others/left/right/all)
 * - affix tags are pinned and never closable
 */
export default Vue.extend({
  name: 'TagsView',
  components: { ScrollPane },
  data() {
    return {
      visible: false,
      top: 0,
      left: 0,
      selectedTag: {} as VisitedView,
    }
  },
  computed: {
    ...mapState(useTagsViewStore, ['visitedViews']),
    /** Index of the right-clicked tag within visitedViews. */
    selectedIdx(): number {
      return this.visitedViews.findIndex((v) => v.path === this.selectedTag.path)
    },
    canCloseSelf(): boolean {
      return !this.selectedTag.affix
    },
    canCloseOthers(): boolean {
      return this.visitedViews.some(
        (v) => !v.affix && v.path !== this.selectedTag.path,
      )
    },
    canCloseLeft(): boolean {
      if (this.selectedIdx < 0) return false
      return this.visitedViews.slice(0, this.selectedIdx).some((v) => !v.affix)
    },
    canCloseRight(): boolean {
      if (this.selectedIdx < 0) return false
      return this.visitedViews.slice(this.selectedIdx + 1).some((v) => !v.affix)
    },
  },
  watch: {
    $route() {
      this.addTags()
      this.moveToCurrentTag()
    },
    visible(value: boolean) {
      if (value) {
        document.body.addEventListener('click', this.closeMenu)
      } else {
        document.body.removeEventListener('click', this.closeMenu)
      }
    },
  },
  mounted() {
    this.addTags()
  },
  methods: {
    isActive(route: VisitedView): boolean {
      return route.path === this.$route.path
    },
    addTags() {
      const { name } = this.$route
      if (name) {
        useTagsViewStore().addView(this.$route)
      }
    },
    moveToCurrentTag() {
      const tags = this.$refs.tag as Array<Vue & { $el: HTMLElement; to: { path: string } }>
      this.$nextTick(() => {
        if (!tags) return
        for (const tag of tags) {
          if (tag.to.path === this.$route.path) {
            ;(this.$refs.scrollPane as InstanceType<typeof ScrollPane>).moveToTarget(tag)
            if (tag.to.path !== this.$route.path) {
              useTagsViewStore().updateVisitedView(this.$route)
            }
            break
          }
        }
      })
    },
    closeSelectedTag(view: VisitedView) {
      const { visitedViews } = useTagsViewStore().delView(view)
      if (this.isActive(view)) {
        this.toLastView(visitedViews, view)
      }
    },
    onCloseSelf() {
      if (!this.canCloseSelf) return
      this.closeSelectedTag(this.selectedTag)
      this.closeMenu()
    },
    onCloseOthers() {
      if (!this.canCloseOthers) return
      this.$router.push(this.selectedTag as any).catch(() => {})
      useTagsViewStore().delOthersViews(this.selectedTag)
      this.moveToCurrentTag()
      this.closeMenu()
    },
    onCloseLeft() {
      if (!this.canCloseLeft) return
      const store = useTagsViewStore()
      const wasActiveRemoved =
        this.selectedIdx > 0 &&
        store.visitedViews
          .slice(0, this.selectedIdx)
          .some((v) => !v.affix && v.path === this.$route.path)
      const { visitedViews } = store.delLeftViews(this.selectedTag)
      if (wasActiveRemoved) this.toLastView(visitedViews, this.selectedTag)
      this.closeMenu()
    },
    onCloseRight() {
      if (!this.canCloseRight) return
      const store = useTagsViewStore()
      const wasActiveRemoved = store.visitedViews
        .slice(this.selectedIdx + 1)
        .some((v) => !v.affix && v.path === this.$route.path)
      const { visitedViews } = store.delRightViews(this.selectedTag)
      if (wasActiveRemoved) this.toLastView(visitedViews, this.selectedTag)
      this.closeMenu()
    },
    onCloseAll() {
      const { visitedViews } = useTagsViewStore().delAllViews()
      if (this.selectedTag.affix) {
        this.closeMenu()
        return
      }
      this.toLastView(visitedViews, this.selectedTag)
      this.closeMenu()
    },
    toLastView(visitedViews: VisitedView[], _view?: VisitedView) {
      const latestView = visitedViews.slice(-1)[0]
      if (latestView) {
        this.$router.push(latestView.fullPath).catch(() => {})
      } else {
        this.$router.push('/').catch(() => {})
      }
    },
    openMenu(tag: VisitedView, e: MouseEvent) {
      const menuMinWidth = 105
      const offsetLeft = this.$el.getBoundingClientRect().left
      const offsetWidth = (this.$el as HTMLElement).offsetWidth
      const maxLeft = offsetWidth - menuMinWidth
      const left = e.clientX - offsetLeft + 15

      this.left = left > maxLeft ? maxLeft : left
      this.top = e.clientY
      this.visible = true
      this.selectedTag = tag
    },
    closeMenu() {
      this.visible = false
    },
    handleScroll() {
      this.closeMenu()
    },
  },
})
</script>

<style lang="scss" scoped>
.tags-view-container {
  height: 34px;
  width: 100%;
  background: var(--card);
  border-bottom: 1px solid var(--border);
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.06), 0 0 3px 0 rgba(0, 0, 0, 0.02);

  .tags-view-wrapper {
    .tags-view-item {
      display: inline-block;
      position: relative;
      cursor: pointer;
      height: 26px;
      line-height: 26px;
      border: 1px solid var(--border);
      color: var(--muted-foreground);
      background: var(--card);
      padding: 0 8px;
      font-size: 12px;
      margin-left: 5px;
      margin-top: 4px;
      border-radius: 3px;

      &:first-of-type {
        margin-left: 15px;
      }
      &:last-of-type {
        margin-right: 15px;
      }
      &.active {
        background-color: var(--primary);
        color: var(--primary-foreground);
        border-color: var(--primary);

        &::before {
          content: '';
          background: var(--primary-foreground);
          display: inline-block;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          position: relative;
          margin-right: 4px;
        }
      }
    }
  }

  .contextmenu {
    margin: 0;
    background: var(--popover);
    z-index: 3000;
    position: absolute;
    list-style-type: none;
    padding: 5px 0;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 400;
    color: var(--popover-foreground);
    box-shadow: 2px 2px 3px 0 rgba(0, 0, 0, 0.3);

    li {
      margin: 0;
      padding: 7px 16px;
      cursor: pointer;

      &:hover {
        background: var(--accent);
      }

      &.disabled {
        color: var(--muted-foreground);
        opacity: 0.4;
        cursor: not-allowed;

        &:hover {
          background: transparent;
        }
      }
    }
  }
}
</style>

<style lang="scss">
/* Style Element UI's close icon inside a tag (unscoped, matches reference). */
.tags-view-wrapper {
  .tags-view-item {
    .el-icon-close {
      width: 16px;
      height: 16px;
      vertical-align: 2px;
      border-radius: 50%;
      text-align: center;
      transition: all 0.3s cubic-bezier(0.645, 0.045, 0.355, 1);
      transform-origin: 100% 50%;

      &:before {
        transform: scale(0.6);
        display: inline-block;
        vertical-align: -3px;
      }
      &:hover {
        background-color: #b4bccc;
        color: #fff;
      }
    }
  }
}
</style>
