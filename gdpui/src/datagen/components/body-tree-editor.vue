<template>
  <div class="body-tree-editor">
    <!-- 工具栏：视图切换 + 导入 -->
    <div class="bte-toolbar">
      <div class="bte-switch">
        <button
          type="button"
          class="bte-switch-btn"
          :class="{ active: bodyView === 'tree' }"
          @click="switchView('tree')"
        >
          <font-awesome-icon icon="folder-tree" />
          树状
        </button>
        <button
          type="button"
          class="bte-switch-btn"
          :class="{ active: bodyView === 'preview' }"
          @click="switchView('preview')"
        >
          <font-awesome-icon icon="eye" />
          预览
        </button>
      </div>

      <div class="bte-import">
        <el-button
          v-if="format === 'json'"
          size="small"
          @click="openJsonDialog"
        >
          <font-awesome-icon icon="file-code" />
          贴入 JSON
        </el-button>
        <el-button
          v-if="format === 'xml'"
          size="small"
          @click="openXmlDialog"
        >
          <font-awesome-icon icon="file-code" />
          贴入 XML
        </el-button>
      </div>
    </div>

    <!-- 树形视图 -->
    <div v-if="bodyView === 'tree'" class="bte-tree">
      <div class="bte-tree-head">
        <div>Key</div>
        <div class="bte-tree-head-value">Value</div>
        <div>Description</div>
      </div>

      <div v-if="bodyTree.length === 0" class="bte-empty">
        暂无结构定义，点击“贴入 {{ format.toUpperCase() }}” 导入报文样例
      </div>
      <div v-else class="bte-tree-body">
        <tree-node
          v-for="(field, idx) in bodyTree"
          :key="idx"
          :field="field"
          :depth="0"
          :scene="scene"
          :current-step-id="stepId"
          @update="updateNode(idx, $event)"
        />
      </div>
    </div>

    <!-- 预览（只读） -->
    <div v-else class="bte-preview">
      <span class="bte-preview-hint">
        {{ format === 'json'
          ? 'Content-Type: application/json · 只读预览'
          : 'Content-Type: application/xml · 只读预览' }}
      </span>
      <json-code-mirror
        v-if="format === 'json'"
        :value="previewText || '{\n  \n}'"
        :read-only="true"
        height="260px"
      />
      <textarea
        v-else
        :value="previewText"
        readonly
        class="bte-preview-xml"
      />
    </div>

    <!-- JSON 导入对话框 -->
    <el-dialog
      title="贴入 JSON 报文"
      :visible.sync="showJsonDialog"
      width="640px"
      append-to-body
    >
      <p class="bte-dialog-desc">
        支持 // 行注释，注释内容将自动提取为字段的 Description。例如: "userId": "abc" // 用户ID
      </p>
      <div class="bte-dialog-editor">
        <json-code-mirror
          :value="dialogInput"
          height="300px"
          placeholder="在此贴入 JSON 报文..."
          @change="onDialogInputChange"
        />
      </div>
      <span slot="footer">
        <el-button @click="showJsonDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!dialogInput.trim()" @click="handleImportJson">
          解析并导入
        </el-button>
      </span>
    </el-dialog>

    <!-- XML 导入对话框 -->
    <el-dialog
      title="贴入 XML 报文"
      :visible.sync="showXmlDialog"
      width="640px"
      append-to-body
    >
      <p class="bte-dialog-desc">系统将解析 XML 结构为树状表格，支持嵌套元素和属性。</p>
      <textarea
        v-model="dialogInput"
        class="bte-dialog-xml"
        placeholder="<?xml version=&quot;1.0&quot;?>&#10;<request>&#10;  <userId>abc</userId>&#10;</request>"
      />
      <span slot="footer">
        <el-button @click="showXmlDialog = false">取消</el-button>
        <el-button type="primary" :disabled="!dialogInput.trim()" @click="handleImportXml">
          解析并导入
        </el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import Vue, { type PropType } from 'vue'

import type { InputFieldDefinition, SceneDefinition } from '@/datagen/common/lib/types'
import { parseJsonWithComments, jsonToFields } from '@/datagen/common/lib/schema-utils'
import { isRecord } from '@/datagen/common/lib/value-utils'
import {
  treeToJson,
  jsonToXml,
  xmlToTree,
} from '@/datagen/common/lib/body-tree-utils'

import JsonCodeMirror from './json-code-mirror.vue'
import TreeNode from './tree-node.vue'

type SubView = 'tree' | 'preview'

interface BodyRequestMapping extends Record<string, unknown> {
  bodyTree?: InputFieldDefinition[]
  bodyView?: SubView
  rawBody?: string
}

/**
 * 请求体树状编辑器（JSON / XML）。
 *
 * Ported from the React `BodyTreeEditor`. Two sub-views — an editable tree of
 * `InputFieldDefinition`s and a read-only serialized preview (CodeMirror for
 * JSON, textarea for XML). Import dialogs parse pasted JSON (with `//` comment
 * → field label extraction) or XML into the tree. All state lives in the
 * step's `requestMapping` (bodyTree / bodyView / rawBody), emitted via `change`.
 */
export default Vue.extend({
  name: 'BodyTreeEditor',
  components: { JsonCodeMirror, TreeNode },
  props: {
    format: { type: String as PropType<'json' | 'xml'>, required: true },
    scene: { type: Object as PropType<SceneDefinition | undefined>, default: undefined },
    step: {
      type: Object as PropType<{ stepId?: string; requestMapping: Record<string, unknown> }>,
      required: true,
    },
  },
  data() {
    return {
      showJsonDialog: false,
      showXmlDialog: false,
      dialogInput: '',
    }
  },
  computed: {
    rm(): BodyRequestMapping {
      return (this.step.requestMapping ?? {}) as BodyRequestMapping
    },
    stepId(): string | undefined {
      return this.step.stepId
    },
    bodyTree(): InputFieldDefinition[] {
      return Array.isArray(this.rm.bodyTree) ? this.rm.bodyTree : []
    },
    bodyView(): SubView {
      return this.rm.bodyView === 'preview' ? 'preview' : 'tree'
    },
    previewText(): string {
      if (this.bodyTree.length === 0) return ''
      const obj = treeToJson(this.bodyTree)
      return this.format === 'xml' ? jsonToXml(obj) : JSON.stringify(obj, null, 2)
    },
  },
  methods: {
    emit(next: BodyRequestMapping) {
      this.$emit('change', next)
    },
    onDialogInputChange(v: string) {
      this.dialogInput = v
    },
    switchView(next: SubView) {
      if (next === 'preview' && this.bodyTree.length > 0) {
        const obj = treeToJson(this.bodyTree)
        const text = this.format === 'xml' ? jsonToXml(obj) : JSON.stringify(obj, null, 2)
        this.emit({ ...this.rm, bodyView: next, rawBody: text })
      } else {
        this.emit({ ...this.rm, bodyView: next })
      }
    },
    updateNode(index: number, updated: InputFieldDefinition) {
      const next = [...this.bodyTree]
      next[index] = updated
      this.emit({ ...this.rm, bodyTree: next })
    },
    openJsonDialog() {
      this.dialogInput = ''
      this.showJsonDialog = true
    },
    openXmlDialog() {
      this.dialogInput = ''
      this.showXmlDialog = true
    },
    handleImportJson() {
      try {
        const { cleanJson, labels } = parseJsonWithComments(this.dialogInput)
        const parsed = JSON.parse(cleanJson) as unknown
        if (!isRecord(parsed)) throw new Error('root must be object')
        const tree = jsonToFields(parsed, labels)
        const text = JSON.stringify(parsed, null, 2)
        this.emit({ ...this.rm, bodyTree: tree, rawBody: text, bodyView: 'tree' })
        this.showJsonDialog = false
        this.dialogInput = ''
        this.$message.success('JSON 报文已解析为树状结构')
      } catch {
        this.$message.error('JSON 解析失败，请检查格式')
      }
    },
    handleImportXml() {
      try {
        const tree = xmlToTree(this.dialogInput)
        if (tree.length === 0) throw new Error('empty')
        this.emit({ ...this.rm, bodyTree: tree, rawBody: this.dialogInput, bodyView: 'tree' })
        this.showXmlDialog = false
        this.dialogInput = ''
        this.$message.success('XML 报文已解析为树状结构')
      } catch {
        this.$message.error('XML 解析失败，请检查格式')
      }
    },
  },
})
</script>

<style scoped>
.body-tree-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bte-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bte-switch {
  display: flex;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 6px;
  background-color: var(--muted);
  padding: 2px;
}

.bte-switch-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: none;
  background: transparent;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 500;
  color: var(--muted-foreground);
  cursor: pointer;
}

.bte-switch-btn.active {
  background-color: var(--background);
  color: var(--foreground);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.bte-import {
  margin-left: auto;
  display: flex;
  gap: 6px;
}

.bte-tree {
  border: 1px solid var(--border);
  border-radius: 6px;
  background-color: var(--card);
  overflow: hidden;
}

.bte-tree-head {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 8px;
  padding: 6px 12px;
  background-color: var(--muted);
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--muted-foreground);
  border-bottom: 1px solid var(--border);
}

.bte-tree-head-value {
  color: #2563eb;
}

.bte-tree-body {
  max-height: 400px;
  overflow: auto;
}

.bte-empty {
  padding: 32px;
  text-align: center;
  font-size: 10px;
  font-style: italic;
  color: var(--muted-foreground);
}

.bte-preview {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bte-preview-hint {
  font-size: 10px;
  color: var(--muted-foreground);
}

.bte-preview-xml {
  width: 100%;
  height: 260px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background-color: var(--muted);
  padding: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  resize: vertical;
  cursor: default;
  opacity: 0.9;
}

.bte-dialog-desc {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--muted-foreground);
}

.bte-dialog-editor {
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}

.bte-dialog-xml {
  width: 100%;
  height: 300px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background-color: var(--muted);
  padding: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  resize: vertical;
}
</style>
