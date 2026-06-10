<template>
  <div class="field-mapper">
    <div class="fm-header">
      <div class="fm-title">
        <span>{{ label }}</span>
        <el-tooltip v-if="description" :content="description" placement="top">
          <font-awesome-icon icon="circle-info" class="fm-info" />
        </el-tooltip>
      </div>
      <el-button type="text" class="fm-add" @click="addField">
        <font-awesome-icon icon="plus" />
      </el-button>
    </div>

    <div class="fm-rows">
      <div
        v-for="[key, val] in fields"
        :key="key"
        class="fm-row"
        :class="{ 'fm-row--desc': hasDesc }"
      >
        <el-input
          :value="key"
          size="small"
          class="fm-key"
          :placeholder="placeholder"
          @input="updateField(key, $event, val)"
        />

        <div class="fm-value">
          <el-tooltip
            :disabled="!isVar(val)"
            :content="rawValue(val)"
            placement="top"
          >
            <el-input
              :value="displayValue(val)"
              size="small"
              class="fm-value-input"
              :class="{ 'fm-value-input--var': isVar(val) }"
              placeholder="值或变量 ${...}"
              :readonly="isVar(val)"
              @input="updateField(key, key, $event)"
            />
          </el-tooltip>
          <variable-selector
            v-if="scene"
            class="fm-var-btn"
            :scene="scene"
            :current-step-id="currentStepId"
            @select="updateField(key, key, $event)"
          />
        </div>

        <el-input
          v-if="hasDesc"
          :value="(descriptions || {})[key] || ''"
          size="small"
          placeholder="说明"
          @input="updateDesc(key, $event)"
        />

        <el-button
          type="text"
          class="fm-del"
          @click="pendingDeleteKey = key"
        >
          <font-awesome-icon icon="trash" />
        </el-button>
      </div>

      <div v-if="fields.length === 0" class="fm-empty">暂无配置</div>
    </div>

    <confirm-dialog
      :open="pendingDeleteKey !== null"
      title="删除字段"
      :description="`确定删除字段 &quot;${pendingDeleteKey}&quot; 吗？`"
      @update:open="onDialogOpenChange"
      @confirm="removeField"
    />
  </div>
</template>

<script lang="ts">
import Vue, { type PropType } from 'vue'

import type { SceneDefinition } from '@/datagen/common/lib/types'
import { formatUnknownValue } from '@/datagen/common/lib/value-utils'
import { isVariableRef, resolveVariableLabel } from '@/datagen/common/lib/variable-utils'

import ConfirmDialog from './confirm-dialog.vue'
import VariableSelector from './variable-selector.vue'

/**
 * 通用键值映射编辑器（Query / urlencoded 表单等）。
 *
 * Ported from the React `FieldMapper`. Each row is key + value(+ optional
 * description); values can be literals or `${...}` variable references, in
 * which case the input shows the resolved human label (read-only) and the
 * variable picker writes the raw expression back. Renaming a key migrates its
 * description entry, matching the source.
 */
export default Vue.extend({
  name: 'FieldMapper',
  components: { ConfirmDialog, VariableSelector },
  props: {
    label: { type: String, required: true },
    description: { type: String, default: '' },
    value: { type: Object as PropType<Record<string, unknown>>, required: true },
    scene: { type: Object as PropType<SceneDefinition | undefined>, default: undefined },
    currentStepId: { type: String as PropType<string | undefined>, default: undefined },
    placeholder: { type: String, default: '字段名' },
    descriptions: {
      type: Object as PropType<Record<string, string> | undefined>,
      default: undefined,
    },
  },
  data() {
    return {
      pendingDeleteKey: null as string | null,
    }
  },
  computed: {
    fields(): Array<[string, unknown]> {
      return Object.entries(this.value)
    },
    hasDesc(): boolean {
      return this.descriptions != null
    },
  },
  methods: {
    isVar(val: unknown): boolean {
      const raw = formatUnknownValue(val)
      return !!this.scene && !!raw && isVariableRef(raw)
    },
    rawValue(val: unknown): string {
      return formatUnknownValue(val)
    },
    displayValue(val: unknown): string {
      const raw = formatUnknownValue(val)
      if (this.scene && raw && isVariableRef(raw)) {
        return resolveVariableLabel(raw, this.scene, this.currentStepId)
      }
      return raw
    },
    updateField(oldKey: string, newKey: string, newValue: unknown) {
      const next = { ...this.value }
      if (oldKey !== newKey) {
        if (this.hasDesc && this.descriptions && this.descriptions[oldKey] != null) {
          const nextDesc = { ...this.descriptions }
          nextDesc[newKey] = nextDesc[oldKey]!
          delete nextDesc[oldKey]
          this.$emit('update:descriptions', nextDesc)
        }
        delete next[oldKey]
      }
      next[newKey] = newValue
      this.$emit('change', next)
    },
    removeField() {
      const key = this.pendingDeleteKey
      if (key === null) return
      const next = { ...this.value }
      delete next[key]
      this.$emit('change', next)
      if (this.hasDesc && this.descriptions) {
        const nextDesc = { ...this.descriptions }
        delete nextDesc[key]
        this.$emit('update:descriptions', nextDesc)
      }
      this.pendingDeleteKey = null
    },
    addField() {
      this.$emit('change', { ...this.value, [`field_${this.fields.length + 1}`]: '' })
    },
    updateDesc(key: string, desc: string) {
      this.$emit('update:descriptions', { ...(this.descriptions ?? {}), [key]: desc })
    },
    /** 确认对话框关闭时清空待删除键 */
    onDialogOpenChange(o: boolean) {
      if (!o) this.pendingDeleteKey = null
    },
  },
})
</script>

<style scoped>
.field-mapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.fm-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--foreground);
}

.fm-info {
  color: var(--muted-foreground);
  font-size: 13px;
  cursor: help;
}

.fm-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.fm-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.fm-row--desc {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 32px;
}

.fm-key {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.fm-row:not(.fm-row--desc) .fm-key {
  width: 33%;
}

.fm-value {
  position: relative;
  flex: 1;
}

.fm-value-input--var >>> .el-input__inner {
  background-color: rgba(37, 99, 235, 0.06);
  color: #2563eb;
  font-weight: 500;
}

.fm-var-btn {
  position: absolute;
  right: 2px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
}

.fm-empty {
  padding: 12px;
  text-align: center;
  font-size: 10px;
  font-style: italic;
  color: var(--muted-foreground);
  border: 1px dashed var(--border);
  border-radius: 6px;
}
</style>
