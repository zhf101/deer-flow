<template>
  <el-popover
    v-model="open"
    placement="bottom-start"
    trigger="click"
    :width="300"
    popper-class="variable-selector-popover"
  >
    <!-- 触发按钮（默认插槽未提供时使用） -->
    <template slot="reference">
      <slot name="trigger">
        <el-button class="vs-trigger" size="small">
          <font-awesome-icon icon="link" class="vs-trigger-icon" />
        </el-button>
      </slot>
    </template>

    <!-- 变量列表面板 -->
    <div class="vs-panel">
      <el-input
        v-model="keyword"
        size="small"
        placeholder="搜索变量..."
        clearable
        class="vs-search"
      >
        <font-awesome-icon slot="prefix" icon="magnifying-glass" class="vs-search-icon" />
      </el-input>

      <div class="vs-list">
        <template v-for="group in groupedVariables">
          <div :key="group.name + '-h'" class="vs-group-label">{{ group.name }}</div>
          <button
            v-for="item in group.items"
            :key="item.value"
            type="button"
            class="vs-item"
            @click="select(item)"
          >
            <span class="vs-item-label">{{ item.label }}</span>
            <span class="vs-item-value">{{ item.value }}</span>
          </button>
        </template>
        <div v-if="groupedVariables.length === 0" class="vs-empty">未找到变量</div>
      </div>
    </div>
  </el-popover>
</template>

<script lang="ts">
import Vue, { type PropType } from 'vue'

import type { SceneDefinition } from '@/datagen/common/lib/types'
import { buildVariableList, type VariableItem } from '@/datagen/common/lib/variable-utils'

const GROUP_ORDER = ['输入参数', '步骤输出', '认证信息', '系统变量']

/**
 * 变量选择器：弹出可搜索的 `${...}` 变量列表，按分组展示。
 *
 * Ported from the React `VariableSelector` (which used shadcn `Command` +
 * `Popover`). Element UI has no command palette, so the searchable grouped
 * list is rebuilt with `el-input` + plain buttons inside an `el-popover`.
 * Emits `select` with the chosen variable string (and the full item).
 */
export default Vue.extend({
  name: 'VariableSelector',
  props: {
    scene: { type: Object as PropType<SceneDefinition | undefined>, default: undefined },
    currentStepId: { type: String as PropType<string | null | undefined>, default: undefined },
    includeAllSteps: { type: Boolean, default: false },
  },
  data() {
    return {
      open: false,
      keyword: '',
    }
  },
  computed: {
    variables(): VariableItem[] {
      if (!this.scene) return []
      return buildVariableList(this.scene, this.currentStepId, this.includeAllSteps)
    },
    filtered(): VariableItem[] {
      const q = this.keyword.trim().toLowerCase()
      if (!q) return this.variables
      return this.variables.filter(
        (v) =>
          v.label.toLowerCase().includes(q) || v.value.toLowerCase().includes(q),
      )
    },
    groupedVariables(): Array<{ name: string; items: VariableItem[] }> {
      return GROUP_ORDER.map((name) => ({
        name,
        items: this.filtered.filter((v) => v.group === name),
      })).filter((g) => g.items.length > 0)
    },
  },
  methods: {
    select(item: VariableItem) {
      this.$emit('select', item.value, item)
      this.open = false
      this.keyword = ''
    },
  },
})
</script>

<style scoped>
.vs-trigger {
  padding: 4px 6px;
}

.vs-trigger-icon {
  color: var(--primary);
  font-size: 12px;
}

.vs-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.vs-search-icon {
  color: var(--muted-foreground);
  line-height: 32px;
}

.vs-list {
  max-height: 280px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.vs-group-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted-foreground);
  padding: 8px 6px 2px;
}

.vs-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  width: 100%;
  padding: 5px 8px;
  border: none;
  background: transparent;
  border-radius: 4px;
  cursor: pointer;
  text-align: left;
}

.vs-item:hover {
  background-color: var(--accent);
}

.vs-item-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--foreground);
}

.vs-item-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  color: var(--muted-foreground);
}

.vs-empty {
  padding: 16px;
  text-align: center;
  font-size: 12px;
  color: var(--muted-foreground);
}
</style>
