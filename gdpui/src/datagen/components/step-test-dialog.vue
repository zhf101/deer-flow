<template>
  <el-dialog
    :visible.sync="dialogVisible"
    width="700px"
    top="5vh"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- 自定义标题 -->
    <template #title>
      <div class="dialog-title">
        <div class="title-icon">
          <font-awesome-icon icon="play" />
        </div>
        <div>
          <div class="title-main">{{ step.stepName || step.stepId }}</div>
          <div class="title-sub">{{ step.method }} {{ step.path }}</div>
        </div>
      </div>
    </template>

    <!-- 环境选择 -->
    <div class="form-section">
      <label class="section-label">运行环境</label>
      <el-select v-model="envCode" placeholder="选择环境..." style="width: 100%">
        <el-option
          v-for="env in environments"
          :key="env.envCode"
          :label="`${env.envName} (${env.envCode})`"
          :value="env.envCode"
        />
      </el-select>
    </div>

    <!-- 场景输入参数（可折叠） -->
    <div class="collapsible-section">
      <div class="collapse-header" @click="showInputs = !showInputs">
        <span>场景输入参数</span>
        <font-awesome-icon :icon="showInputs ? 'chevron-down' : 'chevron-right'" class="collapse-icon" />
      </div>
      <div v-if="showInputs" class="collapse-body">
        <div
          v-for="field in inputFields"
          :key="field.name"
          class="input-row"
        >
          <span class="input-label" :title="field.name">
            {{ field.label || field.name }}
            <span v-if="field.required" class="required-mark">*</span>
          </span>
          <el-input
            v-model="inputStrValues[field.name]"
            size="small"
            :placeholder="field.defaultValue != null ? `默认: ${safeStringify(field.defaultValue)}` : ''"
          />
        </div>
        <div v-if="inputFields.length === 0" class="no-params">无输入参数</div>
      </div>
    </div>

    <!-- 前序步骤输出（可折叠，有依赖时才显示） -->
    <div v-if="step.dependsOn && step.dependsOn.length > 0" class="collapsible-section">
      <div class="collapse-header" @click="showDeps = !showDeps">
        <span>前序步骤输出（{{ step.dependsOn.length }} 个依赖）</span>
        <font-awesome-icon :icon="showDeps ? 'chevron-down' : 'chevron-right'" class="collapse-icon" />
      </div>
      <div v-if="showDeps" class="collapse-body">
        <div v-for="(outputs, depId) in depOutputs" :key="depId" class="dep-group">
          <div class="dep-label">{{ depId }}</div>
          <div v-for="(val, key) in outputs" :key="key" class="input-row">
            <span class="input-label mono">{{ key }}</span>
            <el-input
              :value="safeStringify(val)"
              size="small"
              placeholder="测试值"
              @input="updateDepOutput(depId, key, $event)"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- 测试结果 -->
    <template v-if="result">
      <!-- 状态横幅 -->
      <div :class="['test-status-banner', result.success ? 'success' : 'error']">
        <font-awesome-icon
          :icon="result.success ? 'circle-check' : 'circle-xmark'"
          class="status-icon"
        />
        <div>
          <div :class="['status-text', result.success ? 'text-success' : 'text-error']">
            {{ result.success ? '测试通过' : '测试失败' }}
          </div>
          <div class="status-meta">
            <span v-if="result.response && result.response.statusCode" class="mono">
              Status: {{ result.response.statusCode }}
            </span>
            <span v-if="result.response && result.response.elapsedMs != null">
              {{ result.response.elapsedMs }}ms
            </span>
          </div>
        </div>
      </div>

      <!-- 错误信息 -->
      <div v-if="result.error" class="error-block">
        <p class="error-msg">{{ result.error.message }}</p>
        <pre v-if="result.error.detail" class="error-detail">{{ result.error.detail }}</pre>
      </div>

      <!-- 提取的变量 -->
      <div v-if="result.extractedOutputs && Object.keys(result.extractedOutputs).length > 0" class="extracted-section">
        <div class="section-header">
          提取的变量 ({{ Object.keys(result.extractedOutputs).length }})
        </div>
        <div class="extracted-list">
          <div v-for="(val, key) in result.extractedOutputs" :key="key" class="extracted-item">
            <span class="var-name">{{ key }}</span>
            <span class="var-eq">=</span>
            <span class="var-value" :title="safeStringify(val)">{{ safeStringify(val) }}</span>
          </div>
        </div>
      </div>

      <!-- 响应体 -->
      <div v-if="result.response && result.response.body != null" class="response-section">
        <div class="section-header">响应体</div>
        <pre class="response-body">{{ formatBody(result.response.body) }}</pre>
      </div>
    </template>

    <!-- 底部按钮 -->
    <template #footer>
      <el-button @click="handleClose">关闭</el-button>
      <el-button
        type="primary"
        :loading="testing"
        :disabled="!envCode"
        @click="handleTest"
      >
        <font-awesome-icon v-if="!testing" icon="play" />
        {{ testing ? '测试中...' : '执行测试' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script lang="ts">
import Vue from 'vue'

import { listEnvironments, testHttpSource } from '@/datagen/common/lib/api'
import {
  buildDefaultInputs,
  collectDependencyOutputs,
  resolveRuntimeVariables,
  stepToHttpTestConfig,
} from '@/datagen/common/lib/step-test-utils'
import type {
  EnvironmentResponse,
  HttpSourceTestResult,
  HttpStepDefinition,
  SceneDefinition,
} from '@/datagen/common/lib/types'

/**
 * 步骤测试弹窗：在场景编排中测试单个 HTTP 步骤。
 * 支持选择环境、填写输入参数和前序步骤输出、执行测试并查看响应和提取结果。
 */
export default Vue.extend({
  name: 'StepTestDialog',
  props: {
    step: { type: Object as () => HttpStepDefinition, required: true },
    scene: { type: Object as () => SceneDefinition, required: true },
    visible: { type: Boolean, default: false },
  },
  data() {
    return {
      envCode: '',
      environments: [] as EnvironmentResponse[],
      inputs: {} as Record<string, unknown>,
      inputStrValues: {} as Record<string, string>,
      depOutputs: {} as Record<string, Record<string, unknown>>,
      testing: false,
      result: null as HttpSourceTestResult | null,
      showInputs: true,
      showDeps: false,
    }
  },
  computed: {
    dialogVisible: {
      get(): boolean { return this.visible },
      set(val: boolean) { this.$emit('update:visible', val) },
    },
    inputFields() {
      return (this.scene.inputSchema || []).filter((f) => f.name !== 'env')
    },
  },
  watch: {
    visible(val: boolean) {
      if (val) {
        this.onOpen()
      } else {
        this.result = null
        this.testing = false
      }
    },
  },
  methods: {
    safeStringify(val: unknown): string {
      if (val == null) return ''
      if (typeof val === 'string') return val
      if (typeof val === 'number' || typeof val === 'boolean') return String(val)
      return JSON.stringify(val)
    },

    formatBody(body: unknown): string {
      if (typeof body === 'object' && body !== null) {
        return JSON.stringify(body, null, 2)
      }
      return String(body).substring(0, 2000)
    },

    updateDepOutput(depId: string, key: string, value: string) {
      this.depOutputs = {
        ...this.depOutputs,
        [depId]: { ...this.depOutputs[depId], [key]: value },
      }
    },

    async onOpen() {
      try {
        const envs = await listEnvironments()
        this.environments = envs.filter((e) => e.status === 'ENABLED')
      } catch {
        this.environments = []
      }
      this.inputs = buildDefaultInputs(this.scene.inputSchema || [])
      // 将输入值转为字符串供 el-input 显示
      const strVals: Record<string, string> = {}
      for (const field of this.inputFields) {
        strVals[field.name] = this.safeStringify(this.inputs[field.name])
      }
      this.inputStrValues = strVals
      this.depOutputs = collectDependencyOutputs(this.step, this.scene)
      this.result = null
    },

    async handleTest() {
      if (!this.envCode) {
        this.$message.warning('请先选择环境')
        return
      }

      // 将字符串值转回 inputs
      const resolvedInputs: Record<string, unknown> = {}
      for (const field of this.inputFields) {
        const strVal = this.inputStrValues[field.name]
        resolvedInputs[field.name] = strVal === '' || strVal === undefined ? undefined : strVal
      }

      this.testing = true
      this.result = null

      try {
        const rawConfig = stepToHttpTestConfig(this.step)
        const config = resolveRuntimeVariables(rawConfig, resolvedInputs, this.depOutputs)
        const testResult = await testHttpSource(this.envCode, config)
        this.result = testResult

        if (testResult.success) {
          this.$message.success('执行成功')
          this.$emit('test-success', testResult)
        } else {
          this.$message.error('执行失败')
        }
      } catch (err) {
        this.$message.error(err instanceof Error ? err.message : '测试执行失败')
      } finally {
        this.testing = false
      }
    },

    handleClose() {
      this.$emit('update:visible', false)
    },
  },
})
</script>

<style lang="scss" scoped>
.dialog-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: rgba(59, 130, 246, 0.1);
  color: #3b82f6;
  font-size: 13px;
}

.title-main {
  font-size: 14px;
  font-weight: 600;
}

.title-sub {
  font-size: 11px;
  color: var(--muted-foreground);
}

/* ── 表单区 ── */

.form-section {
  margin-bottom: 12px;
}

.section-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--muted-foreground);
  margin-bottom: 4px;
}

.required-mark {
  color: #e74c3c;
  margin-left: 2px;
}

/* ── 折叠区 ── */

.collapsible-section {
  border: 1px solid var(--border);
  border-radius: 6px;
  margin-bottom: 12px;
  overflow: hidden;
}

.collapse-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background-color 0.15s;

  &:hover {
    background: var(--accent, #f5f5f5);
  }
}

.collapse-icon {
  font-size: 11px;
  color: var(--muted-foreground);
}

.collapse-body {
  padding: 10px 12px;
  border-top: 1px solid var(--border);
}

.input-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;

  &:last-child {
    margin-bottom: 0;
  }
}

.input-label {
  width: 130px;
  flex-shrink: 0;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  &.mono {
    font-family: monospace;
  }
}

.no-params {
  font-size: 12px;
  color: var(--muted-foreground);
  font-style: italic;
  padding: 4px 0;
}

.dep-group {
  margin-bottom: 10px;
}

.dep-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--muted-foreground);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 6px;
}

/* ── 测试结果 ── */

.test-status-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 12px;

  &.success {
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.2);
    .status-icon { color: #10b981; }
  }
  &.error {
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.2);
    .status-icon { color: #ef4444; }
  }
}

.status-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.status-text {
  font-size: 13px;
  font-weight: 600;

  &.text-success { color: #059669; }
  &.text-error { color: #dc2626; }
}

.status-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--muted-foreground);
  margin-top: 2px;
}

.mono {
  font-family: monospace;
}

.error-block {
  border: 1px solid rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.05);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 12px;
}

.error-msg {
  font-size: 13px;
  color: #dc2626;
  font-weight: 500;
  margin: 0 0 6px;
}

.error-detail {
  font-size: 11px;
  color: rgba(220, 38, 38, 0.8);
  white-space: pre-wrap;
  font-family: monospace;
  margin: 0;
}

/* ── 提取变量 / 响应体 ── */

.extracted-section,
.response-section {
  border: 1px solid var(--border);
  border-radius: 6px;
  margin-bottom: 12px;
  overflow: hidden;
}

.section-header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--muted, #f5f5f5);
  font-size: 12px;
  font-weight: 500;
}

.extracted-list {
  padding: 8px 12px;
}

.extracted-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 4px;
}

.var-name {
  font-family: monospace;
  font-weight: 600;
  color: #3b82f6;
}

.var-eq {
  color: var(--muted-foreground);
}

.var-value {
  font-family: monospace;
  color: var(--muted-foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}

.response-body {
  padding: 10px 12px;
  font-size: 11px;
  font-family: monospace;
  max-height: 240px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>
