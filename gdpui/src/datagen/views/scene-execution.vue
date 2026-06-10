<template>
  <div class="scene-execution">
    <!-- 加载中 -->
    <div v-if="loading" class="loading-state">
      <i class="el-icon-loading" /> 加载中...
    </div>

    <!-- 场景不存在 -->
    <div v-else-if="!scene" class="empty-state">
      场景不存在或加载失败
    </div>

    <template v-else>
      <!-- 头部 -->
      <header class="exec-header">
        <div class="header-info">
          <div class="header-row">
            <h1 class="scene-name">{{ scene.sceneName }}</h1>
            <el-tag size="mini" :type="scene.status === 'PUBLISHED' ? 'success' : 'info'">
              {{ scene.status }}
            </el-tag>
            <span v-if="result" :class="['exec-status', `exec-status--${result.status.toLowerCase()}`]">
              <span class="status-dot" />
              {{ statusLabel(result.status) }}
            </span>
          </div>
          <div class="header-meta">
            <span class="mono-text">{{ scene.sceneCode }}</span>
            <span class="meta-sep">|</span>
            <span>{{ scene.sceneType || '未分类' }}</span>
            <span class="meta-sep">|</span>
            <span>{{ scene.steps.length }} 个节点</span>
            <span v-if="result && result.runId" class="meta-sep">|</span>
            <span v-if="result && result.runId" class="mono-text">run: {{ result.runId }}</span>
          </div>
        </div>
        <div class="header-actions">
          <template v-if="!readOnly">
            <el-select v-model="envCode" size="small" placeholder="执行环境" class="env-select">
              <el-option
                v-for="env in environments"
                :key="env.envCode"
                :label="`${env.envName} (${env.envCode})`"
                :value="env.envCode"
              />
            </el-select>
            <el-button
              type="primary"
              size="small"
              :loading="running"
              :disabled="!envCode"
              @click="handleRun"
            >
              <font-awesome-icon v-if="!running" icon="play" />
              {{ running ? '执行中' : '执行' }}
            </el-button>
          </template>
          <el-tag v-if="readOnly" size="small" type="info">历史记录</el-tag>
        </div>
      </header>

      <!-- 入参/响应报文 -->
      <div class="io-section">
        <!-- 入参报文 -->
        <el-collapse v-model="inputCollapse">
          <el-collapse-item name="input">
            <template slot="title">
              <span class="collapse-title">入参报文</span>
              <el-tag size="mini" type="info" class="env-badge">{{ envCode || '未选环境' }}</el-tag>
            </template>
            <div class="io-content">
              <!-- 入参编辑 -->
              <div v-if="!result && inputFields.length > 0" class="input-grid">
                <div v-for="field in inputFields" :key="field.name" class="input-field">
                  <label class="field-label">
                    {{ field.label || field.name }}
                    <span v-if="field.required" class="required-mark">*</span>
                  </label>
                  <template v-if="field.type === 'boolean'">
                    <el-switch
                      :value="inputs[field.name] === true"
                      @change="setInput(field.name, $event)"
                    />
                  </template>
                  <el-input
                    v-else
                    :type="field.type === 'number' ? 'number' : 'text'"
                    :value="formatValue(inputs[field.name])"
                    size="mini"
                    :placeholder="field.remark || field.name"
                    @input="onFieldInput(field, $event)"
                  />
                </div>
              </div>
              <!-- JSON 预览 -->
              <pre v-if="Object.keys(displayInputs).length > 0" class="json-block">{{ jsonText(displayInputs) }}</pre>
              <p v-else class="empty-hint">无入参</p>
            </div>
          </el-collapse-item>
        </el-collapse>

        <!-- 响应报文 -->
        <el-collapse v-if="result" v-model="responseCollapse">
          <el-collapse-item name="response">
            <template slot="title">
              <span class="collapse-title">响应报文</span>
              <span :class="['exec-status-sm', `exec-status--${result.status.toLowerCase()}`]">
                {{ statusLabel(result.status) }}
              </span>
              <span class="duration-text">{{ formatDuration(result.durationMs) }}</span>
            </template>
            <pre class="json-block">{{ jsonText({ status: result.status, errors: result.errors, finalOutput: result.finalOutput, stepCount: result.stepResults.length }) }}</pre>
          </el-collapse-item>
        </el-collapse>
      </div>

      <!-- 步骤列表 + 详情 -->
      <div class="steps-body">
        <!-- 左侧步骤 -->
        <aside class="steps-sidebar">
          <div class="sidebar-title">步骤</div>
          <div class="step-timeline">
            <div
              v-for="(step, index) in orderedSteps"
              :key="step.stepId"
              :class="['timeline-item', { 'timeline-item--active': selectedStepId === step.stepId }]"
              @click="selectedStepId = step.stepId"
            >
              <div class="timeline-left">
                <div :class="['timeline-circle', `timeline-circle--${stepStatusClass(step)}`]">
                  {{ index + 1 }}
                </div>
                <div v-if="index < orderedSteps.length - 1" :class="['timeline-line', `timeline-line--${stepStatusClass(step)}`]" />
              </div>
              <div class="timeline-card">
                <div class="card-header">
                  <span class="card-name">{{ step.stepName || step.stepId }}</span>
                  <el-tag
                    :type="step.pending ? 'info' : stepStatusTagType(step.status)"
                    size="mini"
                  >
                    {{ step.pending ? '待执行' : stepStatusLabel(step.status) }}
                  </el-tag>
                </div>
                <div class="card-meta">
                  <span>{{ step.type }}</span>
                  <template v-if="!step.pending">
                    <span class="meta-dot">&middot;</span>
                    <span>{{ formatDuration(step.durationMs) }}</span>
                  </template>
                </div>
              </div>
            </div>
          </div>
        </aside>

        <!-- 右侧详情 -->
        <main class="steps-detail">
          <!-- 错误信息 -->
          <div v-if="result && result.errors.length > 0" class="error-panel">
            <div class="error-title">
              <font-awesome-icon icon="circle-xmark" /> 执行错误
            </div>
            <p v-for="(err, i) in result.errors" :key="i" class="error-item">{{ err }}</p>
          </div>

          <!-- 步骤详情 -->
          <div v-if="selectedStep" class="step-detail-panel">
            <!-- 步骤头部 -->
            <div :class="['detail-header', `detail-header--${selectedStep.status.toLowerCase()}`]">
              <div class="detail-header-row">
                <h2 class="detail-name">{{ selectedStep.stepName || selectedStep.stepId }}</h2>
                <el-tag size="mini" type="info">{{ selectedStep.type }}</el-tag>
                <el-tag :type="stepStatusTagType(selectedStep.status)" size="mini">
                  {{ stepStatusLabel(selectedStep.status) }}
                </el-tag>
                <el-tag v-if="selectedStep.statusCode" size="mini" type="info">
                  HTTP {{ selectedStep.statusCode }}
                </el-tag>
                <span class="detail-duration">
                  <font-awesome-icon icon="clock" /> {{ formatDuration(selectedStep.durationMs) }}
                </span>
              </div>
              <div v-if="selectedStep.error" class="detail-error">{{ selectedStep.error }}</div>
            </div>

            <!-- Tabs -->
            <el-tabs v-model="detailTab" class="detail-tabs">
              <el-tab-pane label="概览" name="overview">
                <div class="overview-grid">
                  <div class="info-item">
                    <div class="info-label">开始时间</div>
                    <div class="info-value">{{ formatDateTime(selectedStep.startedAt) }}</div>
                  </div>
                  <div class="info-item">
                    <div class="info-label">执行耗时</div>
                    <div class="info-value">{{ formatDuration(selectedStep.durationMs) }}</div>
                  </div>
                </div>
                <div v-if="Object.keys(selectedStep.outputs).length > 0" class="outputs-section">
                  <div class="section-label">输出变量</div>
                  <el-table :data="outputRows" size="mini" empty-text="无输出">
                    <el-table-column prop="key" label="变量名" width="40%">
                      <template #default="{ row }">
                        <span class="mono-text">{{ row.key }}</span>
                      </template>
                    </el-table-column>
                    <el-table-column prop="value" label="值">
                      <template #default="{ row }">
                        <span class="mono-text muted">{{ formatValue(row.value) }}</span>
                      </template>
                    </el-table-column>
                  </el-table>
                </div>
                <p v-else class="empty-hint">该步骤无输出变量</p>
              </el-tab-pane>

              <!-- HTTP 请求 Tab -->
              <template v-if="selectedStep.type === 'HTTP'">
                <el-tab-pane label="请求" name="request">
                  <div class="overview-grid overview-grid--3col">
                    <div class="info-item">
                      <div class="info-label">方法</div>
                      <div class="info-value mono-text">{{ httpRequest.method || '-' }}</div>
                    </div>
                    <div class="info-item">
                      <div class="info-label">Body 类型</div>
                      <div class="info-value">{{ httpRequest.bodyType || '-' }}</div>
                    </div>
                    <div class="info-item">
                      <div class="info-label">URL</div>
                      <div class="info-value mono-text">{{ httpRequest.url || '-' }}</div>
                    </div>
                  </div>
                  <details><summary>请求头</summary><pre class="json-block">{{ jsonText(httpRequest.headers || {}) }}</pre></details>
                  <details><summary>查询参数</summary><pre class="json-block">{{ jsonText(httpRequest.query || {}) }}</pre></details>
                  <details open><summary>请求体</summary><pre class="json-block">{{ jsonText(httpRequest.body || null) }}</pre></details>
                </el-tab-pane>
                <el-tab-pane label="响应" name="response">
                  <div class="response-status">
                    <span class="info-label">状态码</span>
                    <span :class="['status-code', statusCodeClass(httpResponse.statusCode)]">{{ httpResponse.statusCode || '-' }}</span>
                    <span class="detail-duration">
                      <font-awesome-icon icon="clock" />
                      {{ httpResponse.elapsedMs !== undefined ? formatDuration(Number(httpResponse.elapsedMs)) : '-' }}
                    </span>
                  </div>
                  <details open><summary>响应体</summary><pre class="json-block">{{ jsonText(httpResponse.body || null) }}</pre></details>
                  <details><summary>响应头</summary><pre class="json-block">{{ jsonText(httpResponse.headers || {}) }}</pre></details>
                  <details><summary>Cookie</summary><pre class="json-block">{{ jsonText(httpResponse.cookies || []) }}</pre></details>
                  <details><summary>业务判定</summary><pre class="json-block">{{ jsonText(rawResponse.businessResult || null) }}</pre></details>
                  <details><summary>重试信息</summary><pre class="json-block">{{ jsonText(rawResponse.retryInfo || null) }}</pre></details>
                </el-tab-pane>
              </template>

              <!-- SQL Tab -->
              <template v-if="selectedStep.type === 'SQL'">
                <el-tab-pane label="SQL" name="sql">
                  <div class="overview-grid overview-grid--4col">
                    <div class="info-item">
                      <div class="info-label">数据库</div>
                      <div class="info-value">{{ rawResponse.dbType || '-' }}</div>
                    </div>
                    <div class="info-item">
                      <div class="info-label">操作</div>
                      <div class="info-value">{{ rawResponse.operation || '-' }}</div>
                    </div>
                    <div class="info-item">
                      <div class="info-label">影响行数</div>
                      <div class="info-value">{{ rawResponse.affectedRows ?? '-' }}</div>
                    </div>
                    <div class="info-item">
                      <div class="info-label">耗时</div>
                      <div class="info-value">{{ rawResponse.elapsedMs !== undefined ? formatDuration(Number(rawResponse.elapsedMs)) : '-' }}</div>
                    </div>
                  </div>
                  <details><summary>结果字段</summary><pre class="json-block">{{ jsonText(rawResponse.columns || []) }}</pre></details>
                  <details open><summary>首行结果</summary><pre class="json-block">{{ jsonText(rawResponse.row || null) }}</pre></details>
                  <details><summary>结果集</summary><pre class="json-block">{{ jsonText(rawResponse.rows || []) }}</pre></details>
                  <details><summary>新增记录ID</summary><pre class="json-block">{{ jsonText(rawResponse.generatedKeys || []) }}</pre></details>
                  <details><summary>警告</summary><pre class="json-block">{{ jsonText(rawResponse.warnings || []) }}</pre></details>
                </el-tab-pane>
              </template>
            </el-tabs>
          </div>

          <!-- 空状态 -->
          <div v-else class="no-step-selected">
            <font-awesome-icon icon="bolt" class="bolt-icon" />
            <p>点击执行开始运行</p>
            <span class="empty-hint">执行后可在此查看每个步骤的详细结果</span>
          </div>
        </main>
      </div>
    </template>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import { getScene, getSceneRun, listEnvironments, runScene } from '@/datagen/common/lib/api'
import type {
  EnvironmentResponse,
  ExecutionResult,
  InputFieldDefinition,
  SceneDefinition,
  StepResult,
} from '@/datagen/common/lib/types'

type TimelineStep = StepResult & { pending?: boolean }
type JsonRecord = Record<string, unknown>

/**
 * 场景执行页面。
 * 从 React SceneExecutionPage 跨框架重写为 Vue 2 + Element UI。
 * 支持执行模式和历史记录查看模式（由路由 query.runId 决定）。
 */
export default Vue.extend({
  name: 'SceneExecution',
  data() {
    return {
      scene: null as SceneDefinition | null,
      environments: [] as EnvironmentResponse[],
      envCode: '',
      inputs: {} as Record<string, unknown>,
      loading: true,
      running: false,
      result: null as ExecutionResult | null,
      selectedStepId: null as string | null,
      submittedInputs: {} as Record<string, unknown>,
      inputCollapse: ['input'],
      responseCollapse: ['response'],
      detailTab: 'overview',
    }
  },
  computed: {
    readOnly(): boolean {
      return !!this.$route.query.runId
    },
    sceneCode(): string {
      return this.$route.params.code || ''
    },
    runId(): string {
      return (this.$route.query.runId as string) || ''
    },
    inputFields(): InputFieldDefinition[] {
      return (this.scene?.inputSchema ?? []).filter((f) => f.name !== 'env')
    },
    displayInputs(): Record<string, unknown> {
      return this.result ? this.submittedInputs : this.inputs
    },
    selectedStep(): TimelineStep | null {
      if (!this.selectedStepId || !this.result) return null
      return this.result.stepResults.find((s) => s.stepId === this.selectedStepId) ?? null
    },
    orderedSteps(): TimelineStep[] {
      if (!this.scene) return []
      const resultMap = new Map(
        (this.result?.stepResults ?? []).map((s) => [s.stepId, s]),
      )
      return this.scene.steps.map((step, i) => {
        const executed = resultMap.get(step.stepId)
        if (executed) return executed
        return {
          stepId: step.stepId,
          stepName: step.stepName,
          type: step.type,
          stepOrder: step.executionOrder ?? i + 1,
          timelineOrder: null,
          status: 'SKIPPED' as const,
          startedAt: new Date(0).toISOString(),
          finishedAt: new Date(0).toISOString(),
          durationMs: 0,
          outputs: {},
          error: null,
          statusCode: null,
          pending: true,
        }
      })
    },
    rawResponse(): JsonRecord {
      if (!this.selectedStep?.rawResponse) return {}
      return (typeof this.selectedStep.rawResponse === 'object' && this.selectedStep.rawResponse !== null && !Array.isArray(this.selectedStep.rawResponse))
        ? this.selectedStep.rawResponse as JsonRecord
        : {}
    },
    httpRequest(): JsonRecord {
      const req = this.rawResponse.request
      return (typeof req === 'object' && req !== null && !Array.isArray(req)) ? req as JsonRecord : {}
    },
    httpResponse(): JsonRecord {
      const resp = this.rawResponse.response
      return (typeof resp === 'object' && resp !== null && !Array.isArray(resp)) ? resp as JsonRecord : {}
    },
    outputRows(): Array<{ key: string; value: unknown }> {
      if (!this.selectedStep) return []
      return Object.entries(this.selectedStep.outputs).map(([key, value]) => ({ key, value }))
    },
  },
  created() {
    this.loadData()
  },
  methods: {
    async loadData() {
      this.loading = true
      try {
        if (this.runId) {
          // 历史记录查看模式
          const runResult = await getSceneRun(this.runId)
          this.result = runResult
          this.selectedStepId = runResult.stepResults[0]?.stepId ?? null
          this.submittedInputs = runResult.inputs
          this.envCode = runResult.envCode
          const sceneData = await getScene(this.sceneCode)
          this.scene = sceneData
        } else {
          // 执行模式
          const [sceneData, envs] = await Promise.all([getScene(this.sceneCode), listEnvironments()])
          this.scene = sceneData
          const enabledEnvs = envs.filter((e) => e.status === 'ENABLED')
          this.environments = enabledEnvs
          if (!this.envCode && enabledEnvs.length > 0) {
            this.envCode = enabledEnvs[0].envCode
          }
          this.inputs = this.buildDefaultInputs(sceneData.inputSchema)
        }
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '加载失败')
      } finally {
        this.loading = false
      }
    },
    buildDefaultInputs(fields: InputFieldDefinition[]): Record<string, unknown> {
      const inputs: Record<string, unknown> = {}
      for (const field of fields) {
        if (field.name === 'env') continue
        if (field.defaultValue !== undefined && field.defaultValue !== null) {
          inputs[field.name] = field.defaultValue
        }
      }
      return inputs
    },
    setInput(name: string, value: unknown) {
      this.$set(this.inputs, name, value)
    },
    onFieldInput(field: InputFieldDefinition, v: string) {
      const value = v === '' ? undefined : (field.type === 'number' ? Number(v) : v)
      this.$set(this.inputs, field.name, value)
    },
    async handleRun() {
      if (!this.envCode) {
        this.$message.error('请先选择执行环境')
        return
      }
      this.running = true
      this.result = null
      this.selectedStepId = null
      this.submittedInputs = { ...this.inputs }
      try {
        const next = await runScene(this.sceneCode, { envCode: this.envCode, inputs: this.inputs })
        const detail = next.runId ? await getSceneRun(next.runId) : next
        this.result = detail
        this.selectedStepId = detail.stepResults[0]?.stepId ?? null
        if (detail.status === 'SUCCESS') {
          this.$message.success('场景执行成功')
        } else {
          this.$message.error(detail.errors[0] ?? '场景执行未完全成功')
        }
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '场景执行请求失败')
      } finally {
        this.running = false
      }
    },

    /* ── 状态辅助 ── */
    statusLabel(status: string): string {
      if (status === 'SUCCESS') return '执行成功'
      if (status === 'FAILED') return '执行失败'
      return '部分成功'
    },
    stepStatusClass(step: TimelineStep): string {
      if (step.pending) return 'pending'
      if (step.status === 'SUCCESS') return 'success'
      if (step.status === 'FAILED') return 'failed'
      return 'skipped'
    },
    stepStatusTagType(status: string): string {
      if (status === 'SUCCESS') return 'success'
      if (status === 'FAILED') return 'danger'
      return 'info'
    },
    stepStatusLabel(status: string): string {
      if (status === 'SUCCESS') return '成功'
      if (status === 'FAILED') return '失败'
      return '跳过'
    },
    statusCodeClass(code: unknown): string {
      const num = typeof code === 'number' ? code : parseInt(String(code), 10)
      if (num >= 200 && num < 300) return 'status-code--success'
      if (num >= 300 && num < 400) return 'status-code--redirect'
      return 'status-code--error'
    },

    /* ── 格式化 ── */
    formatValue(value: unknown): string {
      if (value === undefined || value === null) return '-'
      if (typeof value === 'object') return JSON.stringify(value)
      return String(value)
    },
    formatDuration(ms: number): string {
      if (!Number.isFinite(ms)) return '-'
      if (ms < 1000) return `${Math.round(ms * 1000) / 1000} ms`
      return `${Math.round((ms / 1000) * 1000) / 1000} s`
    },
    formatDateTime(value: string): string {
      if (!value || value.startsWith('1970-01-01')) return '-'
      const d = new Date(value)
      return Number.isNaN(d.getTime()) ? '-' : d.toLocaleString()
    },
    jsonText(value: unknown): string {
      try { return JSON.stringify(value, null, 2) ?? '(空)' }
      catch { return '无法序列化' }
    },
  },
})
</script>

<style scoped>
.scene-execution {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background);
}

.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  font-size: 13px;
  color: var(--muted-foreground);
}

.exec-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border);
  background: var(--card);
  flex-shrink: 0;
}

.header-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.scene-name {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--muted-foreground);
  margin-top: 2px;
}

.meta-sep {
  color: var(--border);
}

.mono-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.env-select {
  width: 180px;
}

.exec-status,
.exec-status-sm {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 600;
}

.exec-status--success, .exec-status-sm.exec-status--success { color: #10b981; }
.exec-status--failed, .exec-status-sm.exec-status--failed { color: #ef4444; }
.exec-status--partial, .exec-status-sm.exec-status--partial { color: #f59e0b; }

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}

.duration-text {
  font-size: 10px;
  color: var(--muted-foreground);
  margin-left: 8px;
}

/* 入参/响应区域 */
.io-section {
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
  padding: 8px 16px;
}

.collapse-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--foreground);
}

.env-badge {
  margin-left: 8px;
}

.io-content {
  padding: 8px 0;
}

.input-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 8px;
}

.input-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--muted-foreground);
}

.required-mark {
  color: #ef4444;
}

.json-block {
  overflow: auto;
  border-radius: 6px;
  background: var(--accent);
  padding: 10px;
  font-size: 11px;
  line-height: 1.6;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  border: 1px solid var(--border);
  max-height: 200px;
  margin: 0;
}

.empty-hint {
  font-size: 12px;
  color: var(--muted-foreground);
  font-style: italic;
  margin: 0;
  padding: 4px 0;
}

/* 步骤区域 */
.steps-body {
  display: grid;
  grid-template-columns: 220px 1fr;
  flex: 1;
  min-height: 0;
}

.steps-sidebar {
  border-right: 1px solid var(--border);
  overflow-y: auto;
  padding: 10px;
}

.sidebar-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted-foreground);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 4px 8px;
  margin-bottom: 6px;
}

.timeline-item {
  display: flex;
  gap: 10px;
  margin-bottom: 6px;
}

.timeline-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 20px;
  flex-shrink: 0;
}

.timeline-circle {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 2px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 700;
  flex-shrink: 0;
  color: var(--muted-foreground);
  margin-top: 8px;
}

.timeline-circle--success {
  border-color: #34d399;
  background: #10b981;
  color: #fff;
}

.timeline-circle--failed {
  border-color: #f87171;
  background: #ef4444;
  color: #fff;
}

.timeline-circle--pending {
  border-color: var(--border);
  color: var(--muted-foreground);
  opacity: 0.4;
}

.timeline-circle--skipped {
  border-color: var(--border);
  background: var(--accent);
  color: var(--muted-foreground);
}

.timeline-line {
  width: 2px;
  flex: 1;
  margin-top: 4px;
}

.timeline-line--success { background: #6ee7b7; }
.timeline-line--failed { background: #fca5a5; }
.timeline-line--pending { background: var(--border); }
.timeline-line--skipped { background: var(--border); }

.timeline-card {
  flex: 1;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 6px 10px;
  cursor: pointer;
  transition: all 0.15s;
}

.timeline-card:hover {
  background: var(--accent);
}

.timeline-item--active .timeline-card {
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(59, 130, 246, 0.2);
}

.card-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.card-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: var(--muted-foreground);
  margin-top: 4px;
}

.meta-dot { color: var(--border); }

/* 步骤详情 */
.steps-detail {
  overflow-y: auto;
  padding: 16px;
}

.error-panel {
  border: 1px solid #fecaca;
  background: #fef2f2;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
}

.error-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #b91c1c;
  margin-bottom: 4px;
}

.error-item {
  font-size: 12px;
  color: #dc2626;
  padding-left: 20px;
  margin: 2px 0;
}

.detail-header {
  border: 1px solid var(--border);
  border-left: 4px solid var(--border);
  border-radius: 8px;
  padding: 12px 16px;
  background: var(--card);
  margin-bottom: 12px;
}

.detail-header--success { border-left-color: #10b981; }
.detail-header--failed { border-left-color: #ef4444; }
.detail-header--skipped { border-left-color: var(--border); }

.detail-header-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.detail-name {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}

.detail-duration {
  margin-left: auto;
  font-size: 11px;
  color: var(--muted-foreground);
  display: flex;
  align-items: center;
  gap: 4px;
}

.detail-error {
  margin-top: 8px;
  font-size: 12px;
  color: #dc2626;
  background: #fef2f2;
  border-radius: 4px;
  padding: 6px 8px;
}

.detail-tabs >>> .el-tabs__header {
  margin-bottom: 12px;
}

.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}

.overview-grid--3col { grid-template-columns: repeat(3, 1fr); }
.overview-grid--4col { grid-template-columns: repeat(4, 1fr); }

.info-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.info-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted-foreground);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.info-value {
  font-size: 12px;
  font-weight: 500;
  color: var(--foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted-foreground);
  margin-bottom: 8px;
}

.outputs-section {
  margin-top: 12px;
}

.muted { color: var(--muted-foreground); }

details {
  margin-top: 12px;
}

details summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted-foreground);
  padding: 4px 0;
}

details summary:hover {
  color: var(--foreground);
}

.response-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.status-code {
  font-size: 24px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.status-code--success { color: #10b981; }
.status-code--redirect { color: #f59e0b; }
.status-code--error { color: #ef4444; }

.no-step-selected {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px dashed var(--border);
  border-radius: 8px;
  padding: 64px;
  color: var(--muted-foreground);
}

.bolt-icon {
  font-size: 40px;
  margin-bottom: 12px;
  opacity: 0.15;
}

.no-step-selected p {
  font-size: 14px;
  font-weight: 500;
  margin: 0 0 4px;
}
</style>
