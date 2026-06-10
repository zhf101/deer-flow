<template>
  <div class="tree-node">
    <div class="tn-row">
      <!-- 键列 -->
      <div class="tn-key">
        <button
          v-if="hasChildren"
          type="button"
          class="tn-toggle"
          @click="expanded = !expanded"
        >
          <font-awesome-icon :icon="expanded ? 'chevron-down' : 'chevron-right'" />
        </button>
        <span v-else class="tn-toggle-spacer" />
        <span class="tn-name" :style="{ paddingLeft: depth * 12 + 'px' }">
          {{ field.name }}
        </span>
        <span class="tn-type">{{ typeBadge }}</span>
      </div>

      <!-- 值列 -->
      <div v-if="isLeaf" class="tn-value">
        <el-tooltip :disabled="!isVar" :content="rawVal" placement="top">
          <el-input
            :value="displayVal"
            size="small"
            class="tn-value-input"
            :class="{ 'tn-value-input--var': isVar }"
            placeholder="值或 ${...}"
            :readonly="isVar"
            @input="onValueInput"
          />
        </el-tooltip>
        <variable-selector
          v-if="scene"
          class="tn-var-btn"
          :scene="scene"
          :current-step-id="currentStepId"
          @select="onVarSelect"
        />
      </div>
      <span v-else class="tn-container-label">
        ({{ field.type === 'array' ? `array[${(field.children || []).length}]` : 'object' }})
      </span>

      <!-- 描述列 -->
      <el-input
        :value="field.label || ''"
        size="small"
        placeholder="字段说明"
        @input="onLabelInput"
      />
    </div>

    <!-- 子节点 -->
    <template v-if="hasChildren && expanded">
      <tree-node
        v-for="(child, i) in field.children"
        :key="i"
        :field="child"
        :depth="depth + 1"
        :scene="scene"
        :current-step-id="currentStepId"
        @update="updateChild(i, $event)"
      />
    </template>
  </div>
</template>

<script lang="ts">
import Vue, { type PropType } from 'vue'

import type { InputFieldDefinition, SceneDefinition } from '@/datagen/common/lib/types'
import { formatUnknownValue } from '@/datagen/common/lib/value-utils'
import { isVariableRef, resolveVariableLabel } from '@/datagen/common/lib/variable-utils'

import VariableSelector from './variable-selector.vue'

/**
 * 递归树节点（body-tree-editor 内部使用）。
 *
 * Ported from the React `TreeNode`. Leaf nodes edit their `defaultValue`
 * (literal or `${...}` variable, shown resolved + read-only when a variable);
 * container nodes (object/array) render their children recursively. Updates
 * bubble up immutably via the `update` event, matching the source's
 * onUpdate-with-cloned-children pattern.
 */
export default Vue.extend({
  name: 'TreeNode',
  components: { VariableSelector },
  props: {
    field: { type: Object as PropType<InputFieldDefinition>, required: true },
    depth: { type: Number, default: 0 },
    scene: { type: Object as PropType<SceneDefinition | undefined>, default: undefined },
    currentStepId: { type: String as PropType<string | undefined>, default: undefined },
  },
  data() {
    return {
      expanded: this.depth < 2,
    }
  },
  computed: {
    hasChildren(): boolean {
      return this.field.type === 'object' || this.field.type === 'array'
    },
    isLeaf(): boolean {
      return !this.hasChildren
    },
    rawVal(): string {
      return formatUnknownValue(this.field.defaultValue)
    },
    isVar(): boolean {
      return !!this.scene && !!this.rawVal && isVariableRef(this.rawVal)
    },
    displayVal(): string {
      if (this.isVar && this.scene) {
        return resolveVariableLabel(this.rawVal, this.scene, this.currentStepId)
      }
      return this.rawVal
    },
    typeBadge(): string {
      if (this.hasChildren) {
        return this.field.type === 'array'
          ? `array${this.field.children ? `[${this.field.children.length}]` : ''}`
          : 'object'
      }
      return this.field.type
    },
  },
  methods: {
    emitUpdate(updated: InputFieldDefinition) {
      this.$emit('update', updated)
    },
    onValueInput(v: string) {
      this.emitUpdate({ ...this.field, defaultValue: v })
    },
    /** 变量选择器选中后更新 defaultValue */
    onVarSelect(v: string) {
      this.emitUpdate({ ...this.field, defaultValue: v })
    },
    /** 字段说明输入后更新 label */
    onLabelInput(v: string) {
      this.emitUpdate({ ...this.field, label: v })
    },
    updateChild(index: number, updated: InputFieldDefinition) {
      const nextChildren = [...(this.field.children ?? [])]
      nextChildren[index] = updated
      this.emitUpdate({ ...this.field, children: nextChildren })
    },
  },
})
</script>

<style scoped>
.tn-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
  align-items: center;
  padding: 6px 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}

.tn-row:hover {
  background-color: var(--accent);
}

.tn-key {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.tn-toggle {
  flex-shrink: 0;
  padding: 2px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--muted-foreground);
  font-size: 11px;
}

.tn-toggle-spacer {
  width: 16px;
  flex-shrink: 0;
}

.tn-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  font-weight: 500;
  color: var(--foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tn-type {
  flex-shrink: 0;
  font-size: 8px;
  text-transform: uppercase;
  color: var(--muted-foreground);
  background-color: var(--muted);
  padding: 1px 4px;
  border-radius: 3px;
}

.tn-value {
  position: relative;
}

.tn-value-input--var >>> .el-input__inner {
  background-color: rgba(37, 99, 235, 0.06);
  color: #2563eb;
  font-weight: 500;
}

.tn-var-btn {
  position: absolute;
  right: 2px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
}

.tn-container-label {
  font-size: 10px;
  font-style: italic;
  color: var(--muted-foreground);
  padding-left: 8px;
}
</style>
