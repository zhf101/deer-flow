<template>
  <div class="http-response-mapping-editor">
    <!-- Section Header -->
    <div class="section-header">
      <font-awesome-icon icon="file-code" class="section-icon" />
      <span class="section-title">响应报文定义</span>
    </div>

    <!-- Tabs -->
    <el-tabs v-model="activeTab" type="card" class="response-tabs">
      <!-- Body Tab -->
      <el-tab-pane name="body">
        <span slot="label">
          Body
          <el-badge v-if="bodyFieldCount > 0" :value="bodyFieldCount" class="tab-badge" />
        </span>

        <div class="tab-content">
          <!-- Toolbar -->
          <div class="toolbar">
            <div class="view-toggle">
              <el-radio-group v-model="bodyView" size="mini">
                <el-radio-button label="tree">树状</el-radio-button>
                <el-radio-button label="preview">预览</el-radio-button>
              </el-radio-group>
            </div>

            <div class="format-selector">
              <el-select v-model="bodyFormat" size="mini" style="width: 100px" @change="onFormatChange">
                <el-option label="JSON" value="json" />
                <el-option label="XML" value="xml" />
                <el-option label="Text" value="text" />
              </el-select>
            </div>

            <el-button size="mini" @click="openImportDialog">
              <font-awesome-icon :icon="formatIcon" class="format-icon" />
              贴入报文样例
            </el-button>
          </div>

          <!-- Tree View -->
          <div v-if="bodyView === 'tree'" class="tree-view" :class="{ disabled }">
            <div v-if="schema.length === 0" class="empty-state">
              暂无报文结构，点击"贴入报文样例"导入
            </div>
            <div v-else class="tree-container">
              <div class="tree-header">
                <div class="col-key">Key</div>
                <div class="col-type">Type</div>
                <div class="col-sample">示例值</div>
                <div class="col-desc">Description</div>
              </div>
              <div class="tree-body">
                <response-schema-node
                  v-for="(field, idx) in schema"
                  :key="idx"
                  :field="field"
                  :depth="0"
                  :path="`$[${idx}]`"
                  @update="onUpdateSchema"
                />
              </div>
            </div>
          </div>

          <!-- Preview View -->
          <div v-else class="preview-view">
            <span class="preview-label">预览模式 · 基于树状结构生成的 {{ bodyFormat.toUpperCase() }} 样例</span>
            <pre class="preview-content">{{ previewText }}</pre>
          </div>
        </div>
      </el-tab-pane>

      <!-- Headers Tab -->
      <el-tab-pane name="headers">
        <span slot="label">
          Headers
          <el-badge v-if="headersSchema.length > 0" :value="headersSchema.length" class="tab-badge" />
        </span>

        <div class="tab-content" :class="{ disabled }">
          <div class="toolbar">
            <el-button size="mini" @click="openHeadersImport">贴入 Headers</el-button>
            <el-button size="mini" icon="el-icon-plus" circle @click="addHeader" />
          </div>

          <div class="headers-table">
            <div class="table-header">
              <div class="col-key">KEY</div>
              <div class="col-value">VALUE</div>
              <div class="col-label">LABEL</div>
              <div class="col-action">操作</div>
            </div>
            <div class="table-body">
              <div v-for="(header, idx) in headersSchema" :key="idx" class="table-row">
                <div class="col-key">
                  <el-input v-model="header.name" size="mini" @input="onHeaderChange" />
                </div>
                <div class="col-value">
                  <el-input v-model="header.defaultValue" size="mini" @input="onHeaderChange" />
                </div>
                <div class="col-label">
                  <el-input v-model="header.label" size="mini" @input="onHeaderChange" />
                </div>
                <div class="col-action">
                  <el-button type="text" size="mini" @click="removeHeader(idx)">
                    <font-awesome-icon icon="trash" />
                  </el-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- Cookies Tab -->
      <el-tab-pane name="cookies">
        <span slot="label">
          Cookies
          <el-badge v-if="cookiesSchema.length > 0" :value="cookiesSchema.length" class="tab-badge" />
        </span>

        <div class="tab-content" :class="{ disabled }">
          <div class="toolbar">
            <el-button size="mini" icon="el-icon-plus" circle @click="addCookie" />
          </div>

          <div class="cookies-table">
            <div class="table-header">
              <div class="col-name">NAME</div>
              <div class="col-value">VALUE</div>
              <div class="col-domain">DOMAIN</div>
              <div class="col-path">PATH</div>
              <div class="col-action">操作</div>
            </div>
            <div class="table-body">
              <div v-for="(cookie, idx) in cookiesSchema" :key="idx" class="table-row">
                <div class="col-name">
                  <el-input v-model="cookie.name" size="mini" @input="onCookieChange" />
                </div>
                <div class="col-value">
                  <el-input v-model="cookie.defaultValue" size="mini" @input="onCookieChange" />
                </div>
                <div class="col-domain">
                  <el-input v-model="cookie.domain" size="mini" @input="onCookieChange" />
                </div>
                <div class="col-path">
                  <el-input v-model="cookie.path" size="mini" @input="onCookieChange" />
                </div>
                <div class="col-action">
                  <el-button type="text" size="mini" @click="removeCookie(idx)">
                    <font-awesome-icon icon="trash" />
                  </el-button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- Response Handling Section -->
    <div class="response-handling-section">
      <div class="section-header" @click="showResponseHandling = !showResponseHandling">
        <font-awesome-icon :icon="showResponseHandling ? 'chevron-down' : 'chevron-right'" />
        <font-awesome-icon icon="shield-check" class="section-icon" />
        <span class="section-title">业务成功/失败判定</span>
      </div>

      <div v-if="showResponseHandling" class="section-content">
        <p class="section-desc">定义响应报文中的业务成功/失败判定规则</p>

        <!-- Success Rules -->
        <div class="rules-group">
          <div class="rules-header">
            <font-awesome-icon icon="check-circle" class="success-icon" />
            <span>业务成功条件（全部满足）</span>
          </div>
          <div class="rules-list">
            <div v-for="(rule, idx) in successRules" :key="idx" class="rule-item">
              <el-input v-model="rule.path" size="mini" placeholder="路径" class="rule-path" @input="onRuleChange" />
              <el-select v-model="rule.op" size="mini" placeholder="操作符" class="rule-op" @change="onRuleChange">
                <el-option label="=" value="EQ" />
                <el-option label="≠" value="NE" />
                <el-option label="包含" value="CONTAINS" />
                <el-option label="存在" value="EXISTS" />
                <el-option label="非空" value="NOT_EMPTY" />
              </el-select>
              <el-input v-model="rule.value" size="mini" placeholder="值" class="rule-value" @input="onRuleChange" />
              <el-button type="text" size="mini" @click="removeSuccessRule(idx)">
                <font-awesome-icon icon="trash" />
              </el-button>
            </div>
            <el-button size="mini" plain @click="addSuccessRule">
              <font-awesome-icon icon="plus" /> 添加规则
            </el-button>
          </div>
        </div>

        <!-- Failure Rules -->
        <div class="rules-group">
          <div class="rules-header">
            <font-awesome-icon icon="times-circle" class="failure-icon" />
            <span>业务失败条件（任一满足）</span>
          </div>
          <div class="rules-list">
            <div v-for="(rule, idx) in failureRules" :key="idx" class="rule-item">
              <el-input v-model="rule.path" size="mini" placeholder="路径" class="rule-path" @input="onRuleChange" />
              <el-select v-model="rule.op" size="mini" placeholder="操作符" class="rule-op" @change="onRuleChange">
                <el-option label="=" value="EQ" />
                <el-option label="≠" value="NE" />
                <el-option label="包含" value="CONTAINS" />
                <el-option label="存在" value="EXISTS" />
                <el-option label="非空" value="NOT_EMPTY" />
              </el-select>
              <el-input v-model="rule.value" size="mini" placeholder="值" class="rule-value" @input="onRuleChange" />
              <el-button type="text" size="mini" @click="removeFailureRule(idx)">
                <font-awesome-icon icon="trash" />
              </el-button>
            </div>
            <el-button size="mini" plain @click="addFailureRule">
              <font-awesome-icon icon="plus" /> 添加规则
            </el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- Import Dialog -->
    <el-dialog
      :visible.sync="showImportDialog"
      :title="importDialogTitle"
      width="600px"
      append-to-body
    >
      <div class="import-dialog-content">
        <el-input
          v-model="dialogInput"
          type="textarea"
          :rows="12"
          :placeholder="importPlaceholder"
        />
      </div>
      <div slot="footer">
        <el-button size="small" @click="showImportDialog = false">取消</el-button>
        <el-button type="primary" size="small" @click="handleImport">解析并导入</el-button>
      </div>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'
import type {
  HttpStepDefinition,
  InputFieldDefinition,
  ConditionRule,
  ResponseHandling,
} from '../common/lib/types'
import { parseJsonWithComments, jsonToFields, flattenSchema } from '../common/lib/schema-utils'
import ResponseSchemaNode from './response-schema-node.vue'

export default Vue.extend({
  name: 'HttpResponseMappingEditor',
  components: { ResponseSchemaNode },
  props: {
    step: {
      type: Object as () => HttpStepDefinition,
      required: true,
    },
    disabled: {
      type: Boolean,
      default: false,
    },
  },
  data() {
    return {
      activeTab: 'body',
      bodyView: 'tree',
      bodyFormat: 'json',
      showResponseHandling: true,
      showImportDialog: false,
      importFormat: 'json',
      dialogInput: '',
    }
  },
  computed: {
    schema(): InputFieldDefinition[] {
      return this.step.responseSchema || []
    },
    headersSchema(): InputFieldDefinition[] {
      return this.step.responseHeadersSchema || []
    },
    cookiesSchema(): any[] {
      return this.step.responseCookiesSchema || []
    },
    responseHandling(): ResponseHandling {
      return this.step.responseHandling || {
        expectedContentType: 'JSON',
        statusCode: { success: [200] },
        businessSuccess: { allOf: [] },
        businessFailure: { anyOf: [] },
      }
    },
    successRules(): ConditionRule[] {
      return this.responseHandling.businessSuccess?.allOf || []
    },
    failureRules(): ConditionRule[] {
      return this.responseHandling.businessFailure?.anyOf || []
    },
    bodyFieldCount(): number {
      return flattenSchema(this.schema, '$').length
    },
    formatIcon(): string {
      const icons: Record<string, string> = {
        json: 'file-code',
        xml: 'file-code',
        text: 'file-alt',
      }
      return icons[this.bodyFormat] || 'file-code'
    },
    importDialogTitle(): string {
      const titles: Record<string, string> = {
        json: '贴入 JSON 报文样例',
        xml: '贴入 XML 报文样例',
        text: '贴入文本报文样例',
        headers: '贴入 Headers',
      }
      return titles[this.importFormat] || '贴入报文样例'
    },
    importPlaceholder(): string {
      if (this.importFormat === 'headers') {
        return 'Content-Type: application/json\nX-Request-Id: abc123'
      }
      return this.importFormat === 'json'
        ? '{\n  "code": 200,  // 响应码\n  "message": "success"  // 响应消息\n}'
        : '粘贴报文样例内容...'
    },
    previewText(): string {
      if (this.schema.length === 0) return '暂无样例'
      const obj = this.schemaToSample(this.schema)
      if (this.bodyFormat === 'json') {
        return JSON.stringify(obj, null, 2)
      }
      return JSON.stringify(obj, null, 2)
    },
  },
  methods: {
    onFormatChange(format: string) {
      const ctMap: Record<string, string> = {
        json: 'JSON',
        xml: 'XML',
        text: 'TEXT',
      }
      this.$emit('change', {
        responseHandling: {
          ...this.responseHandling,
          expectedContentType: ctMap[format],
        },
      })
    },
    onUpdateSchema(newSchema: InputFieldDefinition[]) {
      this.$emit('change', { responseSchema: newSchema })
    },
    onHeaderChange() {
      this.$emit('change', { responseHeadersSchema: this.headersSchema })
    },
    onCookieChange() {
      this.$emit('change', { responseCookiesSchema: this.cookiesSchema })
    },
    addHeader() {
      const headers = [...this.headersSchema]
      headers.push({
        name: `header_${headers.length + 1}`,
        type: 'string',
        required: false,
        batchEnabled: false,
        defaultValue: '',
        label: '',
      })
      this.$emit('change', { responseHeadersSchema: headers })
    },
    removeHeader(idx: number) {
      const headers = this.headersSchema.filter((_, i) => i !== idx)
      this.$emit('change', { responseHeadersSchema: headers })
    },
    addCookie() {
      const cookies = [...this.cookiesSchema]
      cookies.push({
        name: `cookie_${cookies.length + 1}`,
        type: 'string',
        required: false,
        batchEnabled: false,
        defaultValue: '',
        label: '',
        domain: '',
        path: '/',
      })
      this.$emit('change', { responseCookiesSchema: cookies })
    },
    removeCookie(idx: number) {
      const cookies = this.cookiesSchema.filter((_, i) => i !== idx)
      this.$emit('change', { responseCookiesSchema: cookies })
    },
    onRuleChange() {
      this.$emit('change', { responseHandling: this.responseHandling })
    },
    addSuccessRule() {
      const rules = this.responseHandling.businessSuccess?.allOf || []
      rules.push({ path: '', op: 'EQ', value: '' })
      this.$emit('change', {
        responseHandling: {
          ...this.responseHandling,
          businessSuccess: { allOf: rules },
        },
      })
    },
    removeSuccessRule(idx: number) {
      const rules = [...(this.responseHandling.businessSuccess?.allOf || [])]
      rules.splice(idx, 1)
      this.$emit('change', {
        responseHandling: {
          ...this.responseHandling,
          businessSuccess: { allOf: rules },
        },
      })
    },
    addFailureRule() {
      const rules = this.responseHandling.businessFailure?.anyOf || []
      rules.push({ path: '', op: 'EQ', value: '' })
      this.$emit('change', {
        responseHandling: {
          ...this.responseHandling,
          businessFailure: { anyOf: rules },
        },
      })
    },
    removeFailureRule(idx: number) {
      const rules = [...(this.responseHandling.businessFailure?.anyOf || [])]
      rules.splice(idx, 1)
      this.$emit('change', {
        responseHandling: {
          ...this.responseHandling,
          businessFailure: { anyOf: rules },
        },
      })
    },
    openImportDialog() {
      this.importFormat = this.bodyFormat
      this.dialogInput = ''
      this.showImportDialog = true
    },
    openHeadersImport() {
      this.importFormat = 'headers'
      this.dialogInput = ''
      this.showImportDialog = true
    },
    handleImport() {
      try {
        if (this.importFormat === 'json') {
          const { cleanJson, labels } = parseJsonWithComments(this.dialogInput)
          const parsed = JSON.parse(cleanJson)
          const generatedSchema = jsonToFields(parsed, labels)
          this.$emit('change', {
            responseSchema: generatedSchema,
            requestMapping: {
              ...this.step.requestMapping,
              _rawResponseSample: JSON.stringify(parsed, null, 2),
            },
          })
          this.$message.success('JSON 响应结构已解析')
        } else if (this.importFormat === 'headers') {
          const lines = this.dialogInput.split('\n').filter((l: string) => l.trim())
          const fields: InputFieldDefinition[] = lines
            .map((line: string) => {
              const colonIdx = line.indexOf(':')
              if (colonIdx === -1) return null
              const name = line.slice(0, colonIdx).trim()
              const value = line.slice(colonIdx + 1).trim()
              if (!name) return null
              return {
                name,
                type: 'string' as const,
                required: false,
                batchEnabled: false,
                defaultValue: value,
                label: '',
              }
            })
            .filter(Boolean) as InputFieldDefinition[]

          if (fields.length > 0) {
            this.$emit('change', { responseHeadersSchema: fields })
            this.$message.success(`已解析 ${fields.length} 个响应头`)
          } else {
            this.$message.error('未检测到有效的 Header 行')
          }
        } else {
          this.$emit('change', {
            requestMapping: {
              ...this.step.requestMapping,
              _rawResponseSample: this.dialogInput,
            },
          })
          this.$message.success('报文样例已保存')
        }
        this.showImportDialog = false
      } catch (e) {
        this.$message.error(`${this.importFormat.toUpperCase()} 解析失败，请检查格式`)
      }
    },
    schemaToSample(schema: InputFieldDefinition[]): Record<string, unknown> {
      const obj: Record<string, unknown> = {}
      for (const field of schema) {
        if (field.type === 'object' && field.children) {
          obj[field.name] = this.schemaToSample(field.children)
        } else if (field.type === 'array' && field.children) {
          obj[field.name] = [this.schemaToSample(field.children)]
        } else {
          obj[field.name] = field.defaultValue ?? ''
        }
      }
      return obj
    },
  },
})
</script>

<style lang="scss" scoped>
.http-response-mapping-editor {
  margin-top: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  user-select: none;

  .section-icon {
    font-size: 14px;
    color: #3b82f6;
  }

  .section-title {
    font-size: 13px;
    font-weight: 700;
    color: #3b82f6;
  }
}

.response-tabs {
  margin-top: 12px;

  ::v-deep .el-tabs__header {
    margin-bottom: 12px;
  }

  .tab-badge {
    margin-left: 4px;
  }
}

.tab-content {
  &.disabled {
    pointer-events: none;
    opacity: 0.5;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 12px;

    .view-toggle {
      display: flex;
      align-items: center;
    }

    .format-selector {
      margin-left: auto;
    }
  }

  .tree-view {
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;

    &.disabled {
      pointer-events: none;
      opacity: 0.5;
    }

    .empty-state {
      padding: 32px;
      text-align: center;
      font-size: 12px;
      color: var(--muted-foreground);
      font-style: italic;
    }

    .tree-container {
      .tree-header {
        display: grid;
        grid-template-columns: 1fr 80px 150px 1fr;
        gap: 8px;
        padding: 8px 12px;
        background: var(--muted);
        border-bottom: 1px solid var(--border);
        font-size: 10px;
        font-weight: 700;
        color: var(--muted-foreground);
        text-transform: uppercase;
      }

      .tree-body {
        max-height: 400px;
        overflow: auto;
      }
    }
  }

  .preview-view {
    .preview-label {
      display: block;
      font-size: 10px;
      color: var(--muted-foreground);
      margin-bottom: 8px;
    }

    .preview-content {
      padding: 12px;
      background: var(--muted);
      border-radius: 6px;
      font-family: monospace;
      font-size: 12px;
      white-space: pre-wrap;
      max-height: 400px;
      overflow: auto;
    }
  }

  .headers-table,
  .cookies-table {
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;

    .table-header {
      display: grid;
      gap: 8px;
      padding: 8px 12px;
      background: var(--muted);
      border-bottom: 1px solid var(--border);
      font-size: 10px;
      font-weight: 700;
      color: var(--muted-foreground);
      text-transform: uppercase;
    }

    .table-body {
      .table-row {
        display: grid;
        gap: 8px;
        padding: 8px 12px;
        border-bottom: 1px solid var(--border);
        align-items: center;

        &:last-child {
          border-bottom: none;
        }
      }
    }
  }

  .headers-table {
    .table-header,
    .table-row {
      grid-template-columns: 1fr 1fr 1fr 32px;
    }
  }

  .cookies-table {
    .table-header,
    .table-row {
      grid-template-columns: 1fr 1fr 120px 80px 32px;
    }
  }
}

.response-handling-section {
  margin-top: 24px;

  .section-content {
    padding-top: 12px;

    .section-desc {
      font-size: 12px;
      color: var(--muted-foreground);
      margin-bottom: 16px;
    }

    .rules-group {
      margin-bottom: 16px;

      .rules-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
        font-size: 13px;
        font-weight: 600;

        .success-icon {
          color: #10b981;
        }

        .failure-icon {
          color: #ef4444;
        }
      }

      .rules-list {
        .rule-item {
          display: flex;
          gap: 8px;
          margin-bottom: 8px;
          align-items: center;

          .rule-path {
            flex: 2;
          }

          .rule-op {
            width: 100px;
          }

          .rule-value {
            flex: 1;
          }
        }
      }
    }
  }
}

.import-dialog-content {
  ::v-deep .el-textarea__inner {
    font-family: monospace;
    font-size: 12px;
  }
}
</style>
