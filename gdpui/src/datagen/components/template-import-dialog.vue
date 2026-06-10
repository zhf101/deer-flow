<template>
  <el-dialog
    :visible="visible"
    :title="dialogTitle"
    width="600px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <div class="template-import-dialog">
      <p class="dialog-description">
        选择{{ isHttp ? 'HTTP 接口' : 'SQL' }}模板，将其配置导入到当前步骤。
        导入后步骤的 stepId、依赖关系和执行顺序保持不变。
      </p>

      <!-- Search Bar -->
      <div class="search-wrapper">
        <font-awesome-icon icon="search" class="search-icon" />
        <el-input
          v-model="search"
          size="mini"
          placeholder="搜索模板名称、编码或系统..."
          class="search-input"
        />
      </div>

      <!-- Template List -->
      <div class="template-list">
        <div v-if="filteredSources.length === 0" class="empty-state">
          <span v-if="sources.length === 0">
            暂无可用的{{ isHttp ? 'HTTP 接口' : 'SQL' }}模板
          </span>
          <span v-else>没有匹配的模板</span>
        </div>

        <div v-else class="template-items">
          <div
            v-for="source in filteredSources"
            :key="source.sourceCode"
            class="template-item"
            :class="{ selected: source.sourceCode === selectedCode }"
            @click="selectSource(source.sourceCode)"
          >
            <font-awesome-icon
              :icon="isHttp ? 'globe' : 'database'"
              class="source-icon"
              :class="{ 'http-icon': isHttp, 'sql-icon': !isHttp }"
            />
            <div class="source-info">
              <div class="source-header">
                <span class="source-name">{{ source.sourceName }}</span>
                <el-tag size="mini" type="info" class="sys-tag">{{ source.sysCode }}</el-tag>
              </div>
              <div class="source-meta">
                <span class="source-code">{{ source.sourceCode }}</span>
                <template v-if="isHttp">
                  <el-tag size="mini" class="method-tag">{{ source.method }}</el-tag>
                  <span class="source-path">{{ source.path }}</span>
                </template>
                <template v-else>
                  <el-tag size="mini" class="operation-tag">{{ source.operation }}</el-tag>
                  <span class="datasource-code">{{ source.datasourceCode }}</span>
                </template>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div slot="footer" class="dialog-footer">
      <el-button size="small" @click="handleClose">取消</el-button>
      <el-button
        type="primary"
        size="small"
        :disabled="!selectedSource"
        @click="handleImport"
      >
        <font-awesome-icon icon="download" class="import-icon" />
        导入配置
      </el-button>
    </div>
  </el-dialog>
</template>

<script lang="ts">
import Vue from 'vue'
import type {
  HttpSourceResponse,
  HttpStepDefinition,
  SqlSourceResponse,
  SqlStepDefinition,
  StepDefinition,
} from '../common/lib/types'
import {
  computeHttpSourceHash,
  computeHttpStepConfigHash,
  computeSqlSourceHash,
  computeSqlStepConfigHash,
} from '../common/lib/template-utils'
import { createDefaultHttpTimeoutConfig } from '../common/lib/defaults'

interface Props {
  visible: boolean
  step: StepDefinition
  httpSources: HttpSourceResponse[]
  sqlSources: SqlSourceResponse[]
}

export default Vue.extend({
  name: 'TemplateImportDialog',
  props: {
    visible: {
      type: Boolean,
      default: false,
    },
    step: {
      type: Object as () => StepDefinition,
      required: true,
    },
    httpSources: {
      type: Array as () => HttpSourceResponse[],
      default: () => [],
    },
    sqlSources: {
      type: Array as () => SqlSourceResponse[],
      default: () => [],
    },
  },
  data() {
    return {
      search: '',
      selectedCode: null as string | null,
    }
  },
  computed: {
    isHttp(): boolean {
      return this.step.type === 'HTTP'
    },
    isSql(): boolean {
      return this.step.type === 'SQL'
    },
    dialogTitle(): string {
      return '从模板导入配置'
    },
    sources(): Array<HttpSourceResponse | SqlSourceResponse> {
      if (this.isHttp) return this.httpSources
      if (this.isSql) return this.sqlSources
      return []
    },
    filteredSources(): Array<HttpSourceResponse | SqlSourceResponse> {
      if (!this.search.trim()) return this.sources
      const q = this.search.toLowerCase()
      return this.sources.filter(
        (s) =>
          s.sourceName.toLowerCase().includes(q) ||
          s.sourceCode.toLowerCase().includes(q) ||
          s.sysCode.toLowerCase().includes(q)
      )
    },
    selectedSource(): HttpSourceResponse | SqlSourceResponse | null {
      return this.sources.find((s) => s.sourceCode === this.selectedCode) || null
    },
  },
  methods: {
    selectSource(code: string) {
      this.selectedCode = code
    },
    handleImport() {
      if (!this.selectedSource) return
      const now = new Date().toISOString()

      if (this.isHttp) {
        const src = this.selectedSource as HttpSourceResponse
        const sourceHash = computeHttpSourceHash(src)
        const updated: HttpStepDefinition = {
          ...(this.step as HttpStepDefinition),
          sourceName: src.sourceName,
          sysCode: src.sysCode,
          method: src.method,
          path: src.path,
          timeoutConfig: src.timeoutConfig ?? createDefaultHttpTimeoutConfig(),
          requestMapping: src.requestMapping ?? {},
          bodySchema: src.bodySchema ?? null,
          responseSchema: src.responseSchema ?? null,
          responseHeadersSchema: src.responseHeadersSchema ?? null,
          responseCookiesSchema: src.responseCookiesSchema ?? null,
          responseHandling: src.responseHandling ?? null,
          errorMapping: src.errorMapping ?? null,
          businessErrorMapping: src.businessErrorMapping ?? null,
          retryPolicy: src.retryPolicy ?? null,
          outputMapping: src.outputMapping ?? {},
          outputMeta: src.outputMeta ?? null,
          templateRef: {
            type: 'HTTP_SOURCE',
            sourceCode: src.sourceCode,
            sourceNameAtSnapshot: src.sourceName,
            sourceUpdatedAtSnapshot: src.updatedAt,
            sourceHashSnapshot: sourceHash,
            configHash: '',
            snapshotAt: now,
            drifted: false,
          },
        }
        updated.templateRef!.configHash = computeHttpStepConfigHash(updated)
        this.$emit('import', updated)
      } else if (this.isSql) {
        const src = this.selectedSource as SqlSourceResponse
        const sourceHash = computeSqlSourceHash(src)
        const updated: SqlStepDefinition = {
          ...(this.step as SqlStepDefinition),
          sourceName: src.sourceName,
          sysCode: src.sysCode,
          datasourceCode: src.datasourceCode,
          operation: src.operation,
          sqlText: src.sqlText,
          normalizedSql: src.normalizedSql,
          tables: src.tables ?? [],
          resultFields: src.resultFields ?? [],
          conditionFields: src.conditionFields ?? [],
          parameters: src.parameters ?? [],
          safety: src.safety ?? { requireWhere: true, maxAffectedRows: null },
          templateRef: {
            type: 'SQL_SOURCE',
            sourceCode: src.sourceCode,
            sourceNameAtSnapshot: src.sourceName,
            sourceUpdatedAtSnapshot: src.updatedAt,
            sourceHashSnapshot: sourceHash,
            configHash: '',
            snapshotAt: now,
            drifted: false,
          },
        }
        updated.templateRef!.configHash = computeSqlStepConfigHash(updated)
        this.$emit('import', updated)
      }

      this.resetAndClose()
    },
    handleClose() {
      this.resetAndClose()
    },
    resetAndClose() {
      this.selectedCode = null
      this.search = ''
      this.$emit('update:visible', false)
    },
  },
})
</script>

<style lang="scss" scoped>
.template-import-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 60vh;

  .dialog-description {
    font-size: 12px;
    color: var(--muted-foreground);
    margin: 0;
  }

  .search-wrapper {
    position: relative;

    .search-icon {
      position: absolute;
      left: 10px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 12px;
      color: var(--muted-foreground);
      pointer-events: none;
    }

    .search-input {
      ::v-deep .el-input__inner {
        padding-left: 32px;
        font-size: 12px;
      }
    }
  }

  .template-list {
    flex: 1;
    overflow: auto;
    border: 1px solid var(--border);
    border-radius: 6px;
    min-height: 300px;

    .empty-state {
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 64px 16px;
      font-size: 12px;
      color: var(--muted-foreground);
    }

    .template-items {
      .template-item {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 10px 12px;
        border-left: 2px solid transparent;
        cursor: pointer;
        transition: all 0.2s;

        &:hover {
          background: var(--muted);
        }

        &.selected {
          background: rgba(59, 130, 246, 0.1);
          border-left-color: var(--primary);
        }

        .source-icon {
          font-size: 14px;
          margin-top: 2px;
          flex-shrink: 0;

          &.http-icon {
            color: #3b82f6;
          }

          &.sql-icon {
            color: #10b981;
          }
        }

        .source-info {
          flex: 1;
          min-width: 0;

          .source-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 4px;

            .source-name {
              font-size: 12px;
              font-weight: 500;
              color: var(--foreground);
              overflow: hidden;
              text-overflow: ellipsis;
              white-space: nowrap;
            }

            .sys-tag {
              flex-shrink: 0;
              font-size: 8px;
              height: 16px;
              padding: 0 6px;
            }
          }

          .source-meta {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 10px;
            color: var(--muted-foreground);

            .source-code {
              font-family: monospace;
              overflow: hidden;
              text-overflow: ellipsis;
              white-space: nowrap;
            }

            .method-tag,
            .operation-tag {
              font-size: 8px;
              height: 16px;
              padding: 0 6px;
            }

            .source-path,
            .datasource-code {
              font-family: monospace;
              overflow: hidden;
              text-overflow: ellipsis;
              white-space: nowrap;
            }
          }
        }
      }
    }
  }
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;

  .import-icon {
    font-size: 12px;
    margin-right: 4px;
  }
}
</style>
