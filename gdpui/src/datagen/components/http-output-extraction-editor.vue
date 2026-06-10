<template>
  <section class="output-extraction">
    <div class="oe-trigger" @click="open = !open">
      <font-awesome-icon :icon="open ? 'chevron-down' : 'chevron-right'" class="oe-chevron" />
      <span>提取响应数据到变量</span>
      <span v-if="count > 0" class="oe-count">{{ count }}</span>
    </div>

    <div v-show="open" class="oe-body">
      <p class="oe-hint">
        从 Body / Headers / Cookies 中提取字段，定义下游步骤可引用的变量名。
      </p>

      <div :class="{ 'oe-disabled': disabled }">
        <div class="oe-table">
          <div class="oe-table-head">
            <div>来源</div>
            <div>响应字段</div>
            <div>下游变量名</div>
            <div>中文名</div>
            <div>备注</div>
            <div class="oe-center">操作</div>
          </div>

          <div class="oe-table-body">
            <div
              v-for="row in mappingRows"
              :key="row.varName"
              class="oe-row"
              :class="{ 'oe-row--incomplete': row.missingLabel || row.missingRemark }"
            >
              <div class="oe-center">
                <span class="oe-source" :class="'oe-source--' + row.source.toLowerCase()">
                  {{ row.source }}
                </span>
              </div>
              <div class="oe-field" :title="row.path">{{ row.fieldName }}</div>
              <div class="oe-varname">
                <span class="oe-eq">=</span>
                <el-input
                  :value="row.varName"
                  size="small"
                  placeholder="输入变量名"
                  class="oe-mono"
                  @input="renameVar(row.varName, $event)"
                />
              </div>
              <el-input
                :value="row.label"
                size="small"
                placeholder="中文名"
                :class="{ 'oe-warn': row.missingLabel }"
                @input="updateMeta(row.varName, 'label', $event)"
              />
              <el-input
                :value="row.remark"
                size="small"
                placeholder="业务说明"
                :class="{ 'oe-warn': row.missingRemark }"
                @input="updateMeta(row.varName, 'remark', $event)"
              />
              <div class="oe-center">
                <el-button type="text" class="oe-del" @click="pendingDeleteKey = row.varName">
                  <font-awesome-icon icon="trash" />
                </el-button>
              </div>
            </div>

            <div v-if="mappingRows.length === 0" class="oe-empty">
              未配置提取项，在下方选择字段添加
            </div>
          </div>
        </div>

        <!-- 快速添加下拉 -->
        <div class="oe-quickadd">
          <el-select
            v-if="extractableBodyFields.length > 0"
            :value="''"
            size="small"
            placeholder="+ Body 字段"
            class="oe-add-select"
            @change="addBodyField"
          >
            <el-option
              v-for="f in extractableBodyFields"
              :key="f.path"
              :label="f.label"
              :value="f.path"
            />
          </el-select>

          <el-select
            v-if="headerExtractable.length > 0"
            :value="''"
            size="small"
            placeholder="+ Header"
            class="oe-add-select"
            @change="addHeaderField"
          >
            <el-option
              v-for="h in headerExtractable"
              :key="h.name"
              :label="h.label ? `${h.name} (${h.label})` : h.name"
              :value="h.name"
            />
          </el-select>

          <el-select
            v-if="cookieExtractable.length > 0"
            :value="''"
            size="small"
            placeholder="+ Cookie"
            class="oe-add-select"
            @change="addCookieField"
          >
            <el-option
              v-for="c in cookieExtractable"
              :key="c.name"
              :label="c.label ? `${c.name} (${c.label})` : c.name"
              :value="c.name"
            />
          </el-select>
        </div>
      </div>
    </div>

    <confirm-dialog
      :open="pendingDeleteKey !== null"
      title="删除提取项"
      :description="`确定删除提取项 &quot;${pendingDeleteKey}&quot; 吗？`"
      @update:open="onDialogOpenChange"
      @confirm="handleDelete"
    />
  </section>
</template>

<script lang="ts">
import Vue, { type PropType } from 'vue'

import { flattenSchema, type FlatSchemaEntry } from '@/datagen/common/lib/schema-utils'
import type { HttpStepDefinition, InputFieldDefinition } from '@/datagen/common/lib/types'
import {
  bodyExpression,
  cookieExpression,
  headerExpression,
  isSameMapping,
  mappingDisplayName,
  mappingSource,
} from '@/datagen/common/lib/extraction-expression'

import ConfirmDialog from './confirm-dialog.vue'

interface OutputMeta {
  label?: string
  remark?: string
}

interface MappingRow {
  varName: string
  path: string
  source: 'Body' | 'Headers' | 'Cookies'
  fieldName: string
  label: string
  remark: string
  missingLabel: boolean
  missingRemark: boolean
}

/**
 * 响应数据提取编辑器（合并了 React 的 Section + Editor 两个导出）。
 *
 * Ported from `http-output-extraction-editor.tsx`. Maps response Body/Header/
 * Cookie fields to downstream variable names with optional 中文名/备注 metadata.
 * Emits `change` with `Partial<HttpStepDefinition>` (outputMapping/outputMeta),
 * matching the source's onChange contract.
 */
export default Vue.extend({
  name: 'HttpOutputExtractionSection',
  components: { ConfirmDialog },
  props: {
    step: { type: Object as PropType<HttpStepDefinition>, required: true },
    disabled: { type: Boolean, default: false },
  },
  data() {
    return {
      open: true,
      pendingDeleteKey: null as string | null,
    }
  },
  computed: {
    outputMapping(): Record<string, string> {
      return this.step.outputMapping ?? {}
    },
    count(): number {
      return Object.keys(this.outputMapping).length
    },
    schema(): InputFieldDefinition[] {
      return this.step.responseSchema ?? []
    },
    headersSchema(): InputFieldDefinition[] {
      return this.step.responseHeadersSchema ?? []
    },
    cookiesSchema(): InputFieldDefinition[] {
      return this.step.responseCookiesSchema ?? []
    },
    bodyFlatFields(): FlatSchemaEntry[] {
      return flattenSchema(this.schema, '$')
    },
    extractableBodyFields(): FlatSchemaEntry[] {
      return this.bodyFlatFields.filter((f) => f.type !== 'object' && f.type !== 'array')
    },
    headerExtractable(): InputFieldDefinition[] {
      return this.headersSchema.filter((h) => h.type !== 'object' && h.type !== 'array')
    },
    cookieExtractable(): InputFieldDefinition[] {
      return this.cookiesSchema.filter((c) => c.type !== 'object' && c.type !== 'array')
    },
    mappingRows(): MappingRow[] {
      const meta = this.step.outputMeta ?? {}
      return Object.entries(this.outputMapping).map(([varName, path]) => {
        const source = mappingSource(path)
        const matched = this.bodyFlatFields.find((f) => isSameMapping(bodyExpression(f.path), path))
        const m: OutputMeta = meta[varName] ?? {}
        return {
          varName,
          path,
          source,
          fieldName: matched ? matched.label : mappingDisplayName(path),
          label: m.label ?? '',
          remark: m.remark ?? '',
          missingLabel: !(m.label ?? '').trim(),
          missingRemark: !(m.remark ?? '').trim(),
        }
      })
    },
  },
  methods: {
    renameVar(oldName: string, newName: string) {
      if (newName === oldName) return
      const next: Record<string, string> = {}
      const nextMeta = { ...(this.step.outputMeta ?? {}) }
      Object.entries(this.outputMapping).forEach(([k, v]) => {
        const targetKey = k === oldName ? newName : k
        next[targetKey] = v
        if (k === oldName) {
          nextMeta[targetKey] = nextMeta[oldName] ?? {}
          delete nextMeta[oldName]
        }
      })
      this.$emit('change', { outputMapping: next, outputMeta: nextMeta })
    },
    updateMeta(varName: string, field: 'label' | 'remark', value: string) {
      const nextMeta = { ...(this.step.outputMeta ?? {}) }
      nextMeta[varName] = { ...nextMeta[varName], [field]: value }
      this.$emit('change', { outputMeta: nextMeta })
    },
    /** 确认对话框关闭时清空待删除键 */
    onDialogOpenChange(o: boolean) {
      if (!o) this.pendingDeleteKey = null
    },
    handleDelete() {
      const key = this.pendingDeleteKey
      if (!key) return
      const next = { ...this.outputMapping }
      const nextMeta = { ...(this.step.outputMeta ?? {}) }
      delete next[key]
      delete nextMeta[key]
      this.$emit('change', { outputMapping: next, outputMeta: nextMeta })
      this.pendingDeleteKey = null
    },
    uniqueName(base: string): string {
      let varName = base
      let suffix = 1
      while (varName in this.outputMapping) {
        varName = `${base}_${suffix++}`
      }
      return varName
    },
    addBodyField(path: string) {
      if (!path) return
      const base = path.split('.').pop()?.replace('[*]', '') ?? 'data'
      const varName = this.uniqueName(base)
      const matchedField = this.bodyFlatFields.find((f) => f.path === path)
      const nextMeta = { ...(this.step.outputMeta ?? {}) }
      nextMeta[varName] = {
        label: matchedField?.fieldLabel ?? '',
        remark: matchedField?.fieldRemark ?? '',
      }
      this.$emit('change', {
        outputMapping: { ...this.outputMapping, [varName]: bodyExpression(path) },
        outputMeta: nextMeta,
      })
    },
    addHeaderField(name: string) {
      if (!name) return
      const base = name.replace(/-/g, '_').toLowerCase()
      const varName = this.uniqueName(base)
      const header = this.headersSchema.find((h) => h.name === name)
      const nextMeta = { ...(this.step.outputMeta ?? {}) }
      nextMeta[varName] = { label: header?.label ?? '', remark: header?.remark ?? '' }
      this.$emit('change', {
        outputMapping: { ...this.outputMapping, [varName]: headerExpression(name) },
        outputMeta: nextMeta,
      })
    },
    addCookieField(name: string) {
      if (!name) return
      const varName = this.uniqueName(name)
      const cookie = this.cookiesSchema.find((c) => c.name === name)
      const nextMeta = { ...(this.step.outputMeta ?? {}) }
      nextMeta[varName] = { label: cookie?.label ?? '', remark: cookie?.remark ?? '' }
      this.$emit('change', {
        outputMapping: { ...this.outputMapping, [varName]: cookieExpression(name) },
        outputMeta: nextMeta,
      })
    },
  },
})
</script>

<style scoped>
.output-extraction {
  display: flex;
  flex-direction: column;
}

.oe-trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  font-size: 14px;
  font-weight: 700;
  color: #2563eb;
  cursor: pointer;
}

.oe-chevron {
  font-size: 13px;
}

.oe-count {
  margin-left: 4px;
  border-radius: 9999px;
  background-color: var(--muted);
  padding: 0 6px;
  font-size: 9px;
  font-weight: 700;
  color: var(--muted-foreground);
}

.oe-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 12px;
}

.oe-hint {
  margin: 0;
  font-size: 12px;
  color: var(--muted-foreground);
}

.oe-disabled {
  pointer-events: none;
  opacity: 0.5;
}

.oe-table {
  border: 1px solid var(--border);
  border-radius: 8px;
  background-color: var(--card);
  overflow: hidden;
}

.oe-table-head,
.oe-row {
  display: grid;
  grid-template-columns: 72px minmax(120px, 1fr) minmax(120px, 1fr) 110px minmax(140px, 1fr) 40px;
  gap: 8px;
  align-items: center;
}

.oe-table-head {
  padding: 8px 12px;
  background-color: var(--muted);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--muted-foreground);
  border-bottom: 1px solid var(--border);
}

.oe-table-body {
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.oe-row {
  padding: 4px 12px;
  border-radius: 4px;
  border: 1px solid transparent;
}

.oe-row:hover {
  border-color: var(--border);
}

.oe-row--incomplete {
  border-left: 2px solid #fbbf24;
}

.oe-center {
  display: flex;
  justify-content: center;
}

.oe-source {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
}

.oe-source--body {
  background-color: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.oe-source--headers {
  background-color: rgba(59, 130, 246, 0.1);
  color: #2563eb;
}

.oe-source--cookies {
  background-color: rgba(245, 158, 11, 0.1);
  color: #d97706;
}

.oe-field {
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oe-varname {
  display: flex;
  align-items: center;
  gap: 8px;
}

.oe-eq {
  font-size: 10px;
  color: var(--muted-foreground);
}

.oe-mono >>> .el-input__inner {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.oe-warn >>> .el-input__inner {
  border-left: 2px solid #fbbf24;
}

.oe-del {
  color: var(--muted-foreground);
  padding: 4px;
}

.oe-del:hover {
  color: var(--destructive);
}

.oe-empty {
  padding: 16px;
  text-align: center;
  font-size: 10px;
  font-style: italic;
  color: var(--muted-foreground);
}

.oe-quickadd {
  display: flex;
  gap: 8px;
}

.oe-add-select {
  width: 180px;
}
</style>
