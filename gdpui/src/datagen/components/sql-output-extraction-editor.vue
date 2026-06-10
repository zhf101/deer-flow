<template>
  <div class="sql-output-extraction-editor">
    <!-- Collapsible Header -->
    <div class="section-header" @click="isOpen = !isOpen">
      <font-awesome-icon :icon="isOpen ? 'chevron-down' : 'chevron-right'" class="toggle-icon" />
      <font-awesome-icon icon="bolt" class="section-icon" />
      <span class="section-title">执行结果提取</span>
      <span v-if="count > 0" class="count-badge">{{ count }}</span>
    </div>

    <!-- Collapsible Content -->
    <div v-if="isOpen" class="section-content">
      <p class="section-description">
        对于 SELECT 语句，将查询结果字段映射为变量，供后续步骤引用。
      </p>

      <!-- Quick Add Button -->
      <div v-if="onAddFromResultFields && unmappedCount > 0" class="quick-add-wrapper">
        <el-button
          size="mini"
          type="default"
          @click="onAddFromResultFields"
          class="quick-add-btn"
        >
          <font-awesome-icon icon="bolt" class="bolt-icon" />
          从解析结果添加 ({{ unmappedCount }})
        </el-button>
      </div>

      <!-- Mapping Table -->
      <div class="mapping-table" :class="{ disabled }">
        <div class="table-header">
          <div class="col-result-field">结果字段</div>
          <div class="col-var-name">定义为变量名</div>
          <div class="col-label">中文名</div>
          <div class="col-remark">备注</div>
          <div class="col-action">操作</div>
        </div>

        <div class="table-body">
          <div
            v-for="(field, varName) in step.outputMapping"
            :key="varName"
            class="mapping-row"
            :class="{ 'missing-meta': isMissingMeta(varName) }"
          >
            <!-- Result Field -->
            <div class="col-result-field">
              <el-input
                v-model="step.outputMapping[varName]"
                size="mini"
                class="field-input"
                @input="onFieldChange(varName, $event)"
              />
            </div>

            <!-- Variable Name (readonly) -->
            <div class="col-var-name">
              <div class="var-name-wrapper">
                <span class="arrow">→</span>
                <el-input
                  :value="varName"
                  size="mini"
                  readonly
                  class="var-input"
                />
              </div>
            </div>

            <!-- Label -->
            <div class="col-label">
              <el-input
                :value="getMeta(varName).label"
                size="mini"
                placeholder="中文名"
                class="label-input"
                :class="{ 'missing-field': isMissingLabel(varName) }"
                @input="onLabelChange(varName, $event)"
              />
            </div>

            <!-- Remark -->
            <div class="col-remark">
              <el-input
                :value="getMeta(varName).remark"
                size="mini"
                placeholder="备注"
                class="remark-input"
                :class="{ 'missing-field': isMissingRemark(varName) }"
                @input="onRemarkChange(varName, $event)"
              />
            </div>

            <!-- Delete Action -->
            <div class="col-action">
              <el-button
                type="text"
                size="mini"
                class="delete-btn"
                @click="confirmDelete(varName)"
              >
                <font-awesome-icon icon="trash" />
              </el-button>
            </div>
          </div>

          <!-- Add Button -->
          <el-button
            type="default"
            size="mini"
            plain
            class="add-btn"
            @click="addMapping"
          >
            <font-awesome-icon icon="plus" class="plus-icon" />
            手动添加结果提取项
          </el-button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation Dialog -->
    <confirm-dialog
      :visible.sync="showDeleteDialog"
      title="删除提取项"
      :message="`确定删除提取项 &quot;${pendingDeleteKey}&quot; 吗？`"
      @confirm="handleDelete"
    />
  </div>
</template>

<script lang="ts">
import Vue from 'vue'
import type { SqlStepDefinition, SqlSourceFieldMeta } from '../common/lib/types'
import ConfirmDialog from './confirm-dialog.vue'

export default Vue.extend({
  name: 'SqlOutputExtractionEditor',
  components: { ConfirmDialog },
  props: {
    step: {
      type: Object as () => SqlStepDefinition,
      required: true,
    },
    disabled: {
      type: Boolean,
      default: false,
    },
    resultFields: {
      type: Array as () => SqlSourceFieldMeta[],
      default: () => [],
    },
    onAddFromResultFields: {
      type: Function,
      default: null,
    },
  },
  data() {
    return {
      isOpen: true,
      showDeleteDialog: false,
      pendingDeleteKey: null as string | null,
    }
  },
  computed: {
    count(): number {
      return Object.keys(this.step.outputMapping || {}).length
    },
    unmappedCount(): number {
      return this.resultFields.filter(
        (f: SqlSourceFieldMeta) => !this.step.outputMapping[f.alias || f.fieldName]
      ).length
    },
  },
  methods: {
    getMeta(varName: string): { label: string; remark: string } {
      const meta = this.step.outputMeta?.[varName] || {}
      return {
        label: meta.label || '',
        remark: meta.remark || '',
      }
    },
    isMissingMeta(varName: string): boolean {
      return this.isMissingLabel(varName) || this.isMissingRemark(varName)
    },
    isMissingLabel(varName: string): boolean {
      const meta = this.step.outputMeta?.[varName]
      return !(meta?.label || '').trim()
    },
    isMissingRemark(varName: string): boolean {
      const meta = this.step.outputMeta?.[varName]
      return !(meta?.remark || '').trim()
    },
    onFieldChange(varName: string, value: string) {
      const next = { ...this.step.outputMapping, [varName]: value }
      this.$emit('change', { ...this.step, outputMapping: next })
    },
    onLabelChange(varName: string, value: string) {
      const nextMeta = { ...(this.step.outputMeta || {}) }
      nextMeta[varName] = { ...nextMeta[varName], label: value }
      this.$emit('change', { ...this.step, outputMeta: nextMeta })
    },
    onRemarkChange(varName: string, value: string) {
      const nextMeta = { ...(this.step.outputMeta || {}) }
      nextMeta[varName] = { ...nextMeta[varName], remark: value }
      this.$emit('change', { ...this.step, outputMeta: nextMeta })
    },
    addMapping() {
      const idx = Object.keys(this.step.outputMapping || {}).length + 1
      const varName = `field_${idx}`
      const next = { ...(this.step.outputMapping || {}), [varName]: 'column_name' }
      const nextMeta = {
        ...(this.step.outputMeta || {}),
        [varName]: { label: '', remark: '' },
      }
      this.$emit('change', { ...this.step, outputMapping: next, outputMeta: nextMeta })
    },
    confirmDelete(varName: string) {
      this.pendingDeleteKey = varName
      this.showDeleteDialog = true
    },
    handleDelete() {
      if (!this.pendingDeleteKey) return
      const next = { ...this.step.outputMapping }
      const nextMeta = { ...(this.step.outputMeta || {}) }
      delete next[this.pendingDeleteKey]
      delete nextMeta[this.pendingDeleteKey]
      this.$emit('change', { ...this.step, outputMapping: next, outputMeta: nextMeta })
      this.pendingDeleteKey = null
      this.showDeleteDialog = false
    },
  },
})
</script>

<style lang="scss" scoped>
.sql-output-extraction-editor {
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
  transition: color 0.2s;

  &:hover {
    color: var(--primary);
  }

  .toggle-icon {
    font-size: 14px;
    color: var(--muted-foreground);
  }

  .section-icon {
    font-size: 14px;
    color: #f59e0b;
  }

  .section-title {
    font-size: 13px;
    font-weight: 700;
    color: #f59e0b;
  }

  .count-badge {
    margin-left: 4px;
    padding: 2px 6px;
    border-radius: 10px;
    background: var(--muted);
    font-size: 9px;
    font-weight: 700;
    color: var(--muted-foreground);
  }
}

.section-content {
  padding-top: 12px;

  .section-description {
    font-size: 12px;
    color: var(--muted-foreground);
    margin-bottom: 12px;
  }
}

.quick-add-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;

  .quick-add-btn {
    height: 24px;
    font-size: 9px;
    display: flex;
    align-items: center;
    gap: 4px;

    .bolt-icon {
      font-size: 10px;
      color: #eab308;
    }
  }
}

.mapping-table {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card);
  overflow: hidden;

  &.disabled {
    pointer-events: none;
    opacity: 0.5;
  }

  .table-header {
    display: grid;
    grid-template-columns: 120px 1fr 120px 1fr 48px;
    gap: 8px;
    padding: 8px 16px;
    background: var(--muted);
    border-bottom: 1px solid var(--border);
    font-size: 9px;
    font-weight: 700;
    color: var(--muted-foreground);
    text-transform: uppercase;

    > div {
      display: flex;
      align-items: center;
    }

    .col-action {
      justify-content: center;
    }
  }

  .table-body {
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 8px;

    .mapping-row {
      display: grid;
      grid-template-columns: 120px 1fr 120px 1fr 48px;
      gap: 8px;
      padding: 6px 16px;
      background: var(--muted);
      border-radius: 4px;
      border: 1px solid transparent;
      align-items: center;

      &.missing-meta {
        border-left: 2px solid #f59e0b;
      }

      .col-result-field {
        .field-input {
          font-size: 10px;
          font-family: monospace;
        }
      }

      .col-var-name {
        .var-name-wrapper {
          display: flex;
          align-items: center;
          gap: 8px;

          .arrow {
            font-size: 10px;
            color: var(--muted-foreground);
          }

          .var-input {
            flex: 1;
            font-size: 10px;
            font-family: monospace;
          }
        }
      }

      .col-label,
      .col-remark {
        .label-input,
        .remark-input {
          font-size: 10px;

          &.missing-field {
            border-left: 2px solid #f59e0b;
          }
        }
      }

      .col-action {
        display: flex;
        justify-content: center;

        .delete-btn {
          width: 24px;
          height: 24px;
          padding: 0;
          color: var(--muted-foreground);

          &:hover {
            color: var(--destructive);
          }
        }
      }
    }

    .add-btn {
      width: 100%;
      height: 32px;
      font-size: 10px;
      border-style: dashed;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;

      .plus-icon {
        font-size: 10px;
      }
    }
  }
}
</style>
