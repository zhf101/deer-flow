<template>
  <div class="header-field-mapper">
    <div class="hfm-header">
      <div class="hfm-title">
        <span>{{ label }}</span>
        <el-tooltip v-if="description" :content="description" placement="top">
          <font-awesome-icon icon="circle-info" class="hfm-info" />
        </el-tooltip>
      </div>
      <el-button type="text" class="hfm-add" @click="addField">
        <font-awesome-icon icon="plus" />
      </el-button>
    </div>

    <div class="hfm-rows">
      <div
        v-for="[key, val] in fields"
        :key="key"
        class="hfm-row"
        :class="{ 'hfm-row--desc': hasDesc }"
      >
        <!-- Key with header-name autocomplete -->
        <el-autocomplete
          :value="key"
          size="small"
          class="hfm-key"
          :placeholder="placeholder"
          :fetch-suggestions="querySuggestions"
          value-key="name"
          @input="updateField(key, $event, val)"
          @select="updateField(key, $event.name, val)"
        >
          <template #default="{ item }">
            <div class="hfm-suggest">
              <span class="hfm-suggest-name">{{ item.name }}</span>
              <span class="hfm-suggest-desc">{{ item.desc }}</span>
            </div>
          </template>
        </el-autocomplete>

        <!-- Value with variable selector -->
        <div class="hfm-value">
          <el-tooltip
            :disabled="!isVar(val)"
            :content="rawValue(val)"
            placement="top"
          >
            <el-input
              :value="displayValue(val)"
              size="small"
              class="hfm-value-input"
              :class="{ 'hfm-value-input--var': isVar(val) }"
              placeholder="值或变量 ${...}"
              :readonly="isVar(val)"
              @input="updateField(key, key, $event)"
            />
          </el-tooltip>
          <variable-selector
            v-if="scene"
            class="hfm-var-btn"
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

        <el-button type="text" class="hfm-del" @click="pendingDeleteKey = key">
          <font-awesome-icon icon="trash" />
        </el-button>
      </div>

      <div v-if="fields.length === 0" class="hfm-empty">
        暂无 Header，点击 + 添加
      </div>
    </div>

    <confirm-dialog
      :open="pendingDeleteKey !== null"
      title="删除请求头"
      :description="`确定删除请求头 &quot;${pendingDeleteKey}&quot; 吗？`"
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

/** 用于自动补全的常见 HTTP 请求头（与 React 源一致）。 */
const COMMON_HEADERS = [
  { name: 'Content-Type', desc: '内容类型' },
  { name: 'Accept', desc: '接受的响应类型' },
  { name: 'Authorization', desc: '认证信息' },
  { name: 'X-Request-Id', desc: '请求追踪 ID' },
  { name: 'X-Correlation-Id', desc: '关联 ID' },
  { name: 'X-Api-Key', desc: 'API 密钥' },
  { name: 'X-Api-Version', desc: 'API 版本' },
  { name: 'Cache-Control', desc: '缓存控制' },
  { name: 'Cookie', desc: 'Cookie' },
  { name: 'User-Agent', desc: '用户代理' },
  { name: 'Referer', desc: '来源页面' },
  { name: 'Origin', desc: '请求来源' },
  { name: 'If-None-Match', desc: '条件请求 ETag' },
  { name: 'If-Modified-Since', desc: '条件请求时间' },
  { name: 'X-Forwarded-For', desc: '转发来源 IP' },
  { name: 'X-Tenant-Id', desc: '租户 ID' },
  { name: 'X-Trace-Id', desc: '链路追踪 ID' },
  { name: 'X-Operator', desc: '操作人' },
  { name: 'X-Source', desc: '请求来源标识' },
  { name: 'X-Timestamp', desc: '请求时间戳' },
  { name: 'X-Sign', desc: '签名' },
  { name: 'X-Nonce', desc: '随机数' },
]

interface HeaderSuggestion {
  name: string
  desc: string
}

/**
 * 请求头键值映射编辑器。
 *
 * Ported from the React `HeaderFieldMapper`. The source's bespoke suggestion
 * dropdown is replaced by Element UI's `el-autocomplete` over the same
 * COMMON_HEADERS list; value editing + variable picker mirror FieldMapper.
 */
export default Vue.extend({
  name: 'HeaderFieldMapper',
  components: { ConfirmDialog, VariableSelector },
  props: {
    label: { type: String, required: true },
    description: { type: String, default: '' },
    value: { type: Object as PropType<Record<string, unknown>>, required: true },
    scene: { type: Object as PropType<SceneDefinition | undefined>, default: undefined },
    currentStepId: { type: String as PropType<string | undefined>, default: undefined },
    placeholder: { type: String, default: 'Header Key' },
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
    querySuggestions(
      queryString: string,
      cb: (results: HeaderSuggestion[]) => void,
    ) {
      const q = (queryString || '').toLowerCase()
      const results = q
        ? COMMON_HEADERS.filter(
            (h) => h.name.toLowerCase().includes(q) || h.desc.includes(q),
          ).slice(0, 8)
        : COMMON_HEADERS.slice(0, 8)
      cb(results)
    },
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
      this.$emit('change', {
        ...this.value,
        [`header_${this.fields.length + 1}`]: '',
      })
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
.header-field-mapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hfm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.hfm-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--foreground);
}

.hfm-info {
  color: var(--muted-foreground);
  font-size: 13px;
  cursor: help;
}

.hfm-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hfm-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.hfm-row--desc {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr 32px;
}

.hfm-key {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.hfm-row:not(.hfm-row--desc) .hfm-key {
  width: 33%;
}

.hfm-suggest {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.hfm-suggest-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 500;
  font-size: 11px;
}

.hfm-suggest-desc {
  color: var(--muted-foreground);
  font-size: 10px;
}

.hfm-value {
  position: relative;
  flex: 1;
}

.hfm-value-input--var >>> .el-input__inner {
  background-color: rgba(37, 99, 235, 0.06);
  color: #2563eb;
  font-weight: 500;
}

.hfm-var-btn {
  position: absolute;
  right: 2px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
}

.hfm-empty {
  padding: 12px;
  text-align: center;
  font-size: 10px;
  font-style: italic;
  color: var(--muted-foreground);
  border: 1px dashed var(--border);
  border-radius: 6px;
}
</style>
