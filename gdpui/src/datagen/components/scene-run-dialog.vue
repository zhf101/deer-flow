<template>
  <el-dialog
    :visible.sync="dialogVisible"
    :title="`执行场景: ${scene.sceneName}`"
    width="900px"
    top="5vh"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <div class="run-dialog-body">
      <!-- ── 左侧：输入表单 ── -->
      <div class="run-left">
        <!-- 环境选择 -->
        <div class="form-section">
          <label class="section-label">执行环境</label>
          <el-select v-model="envCode" placeholder="选择环境..." style="width: 100%">
            <el-option
              v-for="env in environments"
              :key="env.envCode"
              :label="`${env.envName} (${env.envCode})`"
              :value="env.envCode"
            />
          </el-select>
        </div>

        <!-- 动态输入字段 -->
        <div v-for="field in inputFields" :key="field.name" class="form-section">
          <label class="section-label">
            {{ field.label || field.name }}
            <span v-if="field.required" class="required-mark">*</span>
          </label>

          <!-- boolean 类型 -->
          <el-switch
            v-if="field.type === 'boolean'"
            v-model="inputs[field.name]"
          />

          <!-- number 类型 -->
          <el-input
            v-else-if="field.type === 'number'"
            :value="formatVal(inputs[field.name])"
            @input="onNumberInput(field.name, $event)"
            :placeholder="field.remark || `输入 ${field.label || field.name}`"
          />

          <!-- 其他类型（string/date/enum 等） -->
          <el-input
            v-else
            :value="formatVal(inputs[field.name])"
            @input="onStringInput(field.name, $event)"
            :placeholder="field.remark || `输入 ${field.label || field.name}`"
          />
        </div>

        <div v-if="inputFields.length === 0" class="no-inputs">
          此场景无需输入参数
        </div>

        <!-- 执行按钮 -->
        <el-button
          type="success"
          :loading="running"
          :disabled="!envCode"
          class="run-btn"
          @click="handleRun"
        >
          <font-awesome-icon v-if="!running" icon="play" />
          {{ running ? '执行中...' : '执行' }}
        </el-button>
      </div>

      <!-- ── 右侧：执行结果 ── -->
      <div class="run-right">
        <template v-if="result">
          <!-- 总体结果 -->
          <div :class="['result-summary', result.status === 'SUCCESS' ? 'success' : 'error']">
            <font-awesome-icon
              :icon="result.status === 'SUCCESS' ? 'circle-check' : 'circle-xmark'"
              class="result-icon"
            />
            <div class="result-info">
              <div class="result-status">{{ result.status === 'SUCCESS' ? '执行成功' : '执行失败' }}</div>
              <div class="result-meta">
                <span>版本 v{{ result.versionNo }}</span>
                <span><font-awesome-icon icon="clock" /> {{ result.durationMs }}ms</span>
                <span>{{ result.envCode }}</span>
              </div>
            </div>
            <el-tag :type="result.status === 'SUCCESS' ? 'success' : 'danger'" size="small">
              {{ result.status }}
            </el-tag>
          </div>

          <!-- 步骤结果列表 -->
          <div class="steps-section">
            <h4>步骤执行详情</h4>
            <div v-for="sr in result.stepResults" :key="sr.stepId" :class="['step-card', `step-${sr.status.toLowerCase()}`]">
              <div class="step-card-header" @click="toggleStep(sr.stepId)">
                <font-awesome-icon :icon="expandedSteps.has(sr.stepId) ? 'chevron-down' : 'chevron-right'" class="chevron" />
                <font-awesome-icon
                  :icon="stepStatusIcon(sr.status)"
                  :class="['step-status-icon', `icon-${sr.status.toLowerCase()}`]"
                />
                <span class="step-name">{{ sr.stepName || sr.stepId }}</span>
                <el-tag size="mini" type="info" class="step-type-badge">{{ sr.type }}</el-tag>
                <span class="step-duration">
                  <font-awesome-icon icon="clock" /> {{ sr.durationMs }}ms
                </span>
              </div>
              <div v-if="expandedSteps.has(sr.stepId)" class="step-card-body">
                <div v-if="sr.error" class="step-error">{{ sr.error }}</div>
                <div v-if="sr.statusCode" class="step-status-code">HTTP {{ sr.statusCode }}</div>
                <div v-if="Object.keys(sr.outputs).length > 0" class="step-outputs">
                  <div class="outputs-label">输出变量</div>
                  <pre class="outputs-json">{{ JSON.stringify(sr.outputs, null, 2) }}</pre>
                </div>
              </div>
            </div>
          </div>

          <!-- 最终输出 -->
          <div v-if="Object.keys(result.finalOutput).length > 0" class="final-output">
            <h4>最终输出</h4>
            <pre class="output-json">{{ JSON.stringify(result.finalOutput, null, 2) }}</pre>
          </div>

          <!-- 错误列表 -->
          <div v-if="result.errors.length > 0" class="error-list">
            <h4 class="error-title">错误信息</h4>
            <div v-for="(err, i) in result.errors" :key="i" class="error-item">{{ err }}</div>
          </div>
        </template>

        <!-- 空状态 -->
        <div v-else class="empty-result">
          <font-awesome-icon icon="play" class="empty-icon" />
          <p>填写参数后点击执行</p>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script lang="ts">
import Vue from 'vue'

import { listEnvironments, runScene } from '@/datagen/common/lib/api'
import { formatUnknownValue } from '@/datagen/common/lib/value-utils'
import type {
  EnvironmentResponse,
  ExecutionResult,
  InputFieldDefinition,
  SceneDefinition,
} from '@/datagen/common/lib/types'

/**
 * 场景执行弹窗：选择环境、填写输入参数、执行并查看各步骤结果。
 * 布局为左右分栏：左侧输入表单，右侧执行结果详情。
 */
export default Vue.extend({
  name: 'SceneRunDialog',
  props: {
    scene: { type: Object as () => SceneDefinition, required: true },
    sceneCode: { type: String, required: true },
    visible: { type: Boolean, default: false },
  },
  data() {
    return {
      envCode: '',
      inputs: {} as Record<string, unknown>,
      running: false,
      result: null as ExecutionResult | null,
      environments: [] as EnvironmentResponse[],
      expandedSteps: new Set<string>(),
    }
  },
  computed: {
    dialogVisible: {
      get(): boolean { return this.visible },
      set(val: boolean) { this.$emit('update:visible', val) },
    },
    // 过滤掉 env 字段（由环境选择器处理）
    inputFields(): InputFieldDefinition[] {
      return (this.scene.inputSchema || []).filter((f) => f.name !== 'env')
    },
  },
  watch: {
    visible(val: boolean) {
      if (val) {
        this.loadEnvironments()
        this.initDefaultInputs()
      } else {
        this.result = null
        this.running = false
        this.expandedSteps = new Set()
      }
    },
  },
  methods: {
    formatVal(v: unknown): string {
      return formatUnknownValue(v)
    },

    onNumberInput(name: string, v: string) {
      this.$set(this.inputs, name, v === '' ? undefined : Number(v))
    },

    onStringInput(name: string, v: string) {
      this.$set(this.inputs, name, v === '' ? undefined : v)
    },

    async loadEnvironments() {
      try {
        const envs = await listEnvironments()
        this.environments = envs.filter((e) => e.status === 'ENABLED')
        if (this.environments.length > 0 && !this.envCode) {
          this.envCode = this.environments[0]!.envCode
        }
      } catch {
        this.$message.error('加载环境列表失败')
      }
    },

    initDefaultInputs() {
      const defaults: Record<string, unknown> = {}
      for (const field of this.scene.inputSchema || []) {
        if (field.defaultValue !== null && field.defaultValue !== undefined) {
          defaults[field.name] = field.defaultValue
        }
      }
      this.inputs = defaults
    },

    async handleRun() {
      if (!this.envCode) {
        this.$message.warning('请先选择执行环境')
        return
      }
      this.running = true
      this.result = null
      try {
        const res = await runScene(this.sceneCode, { envCode: this.envCode, inputs: this.inputs })
        this.result = res
        if (res.status === 'SUCCESS') {
          this.$message.success('场景执行成功')
        } else {
          this.$message.error(`场景执行失败: ${res.errors[0] ?? '未知错误'}`)
        }
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '执行请求失败')
      } finally {
        this.running = false
      }
    },

    toggleStep(stepId: string) {
      const s = new Set(this.expandedSteps)
      if (s.has(stepId)) s.delete(stepId)
      else s.add(stepId)
      this.expandedSteps = s
    },

    stepStatusIcon(status: string): string {
      return status === 'SUCCESS' ? 'circle-check'
        : status === 'FAILED' ? 'circle-xmark'
        : 'circle-exclamation'
    },

    handleClose() {
      this.$emit('update:visible', false)
    },
  },
})
</script>

<style lang="scss" scoped>
.run-dialog-body {
  display: flex;
  gap: 16px;
  min-height: 480px;
  max-height: 70vh;
}

.run-left {
  width: 340px;
  flex-shrink: 0;
  overflow-y: auto;
  padding-right: 16px;
  border-right: 1px solid var(--border);
}

.run-right {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
}

.form-section {
  margin-bottom: 12px;
}

.section-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  color: var(--foreground);
}

.required-mark {
  color: #e74c3c;
  margin-left: 2px;
}

.no-inputs {
  font-size: 13px;
  color: var(--muted-foreground);
  font-style: italic;
  padding: 8px 0;
}

.run-btn {
  width: 100%;
  margin-top: 16px;
}

/* ── 右侧结果 ── */

.result-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 6px;
  margin-bottom: 16px;

  &.success {
    background: #f0fdf4;
    .result-icon { color: #16a34a; }
    .result-status { color: #16a34a; }
  }
  &.error {
    background: #fef2f2;
    .result-icon { color: #dc2626; }
    .result-status { color: #dc2626; }
  }
}

.result-info {
  flex: 1;
}

.result-status {
  font-size: 14px;
  font-weight: 600;
}

.result-meta {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--muted-foreground);
  margin-top: 2px;
}

/* ── 步骤卡片 ── */

.steps-section {
  margin-bottom: 16px;
  h4 {
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 8px;
  }
}

.step-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  margin-bottom: 6px;
  overflow: hidden;

  &.step-success { background: #f0fdf4; }
  &.step-failed { background: #fef2f2; }
  &.step-skipped { background: #f9fafb; }
}

.step-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 12px;

  &:hover {
    background: rgba(0, 0, 0, 0.03);
  }
}

.chevron {
  width: 10px;
  color: var(--muted-foreground);
}

.step-status-icon {
  width: 14px;
  &.icon-success { color: #16a34a; }
  &.icon-failed { color: #dc2626; }
  &.icon-skipped { color: #9ca3af; }
}

.step-name {
  flex: 1;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-type-badge {
  flex-shrink: 0;
}

.step-duration {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--muted-foreground);
}

.step-card-body {
  padding: 8px 12px;
  border-top: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.5);
}

.step-error {
  font-size: 12px;
  color: #dc2626;
  background: #fef2f2;
  padding: 8px;
  border-radius: 4px;
  margin-bottom: 6px;
}

.step-status-code {
  font-size: 12px;
  color: var(--muted-foreground);
  margin-bottom: 6px;
}

.outputs-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted-foreground);
  margin-bottom: 4px;
  text-transform: uppercase;
}

.outputs-json,
.output-json {
  font-size: 11px;
  background: var(--muted, #f5f5f5);
  padding: 8px;
  border-radius: 4px;
  overflow: auto;
  max-height: 160px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

/* ── 最终输出 / 错误 ── */

.final-output,
.error-list {
  margin-bottom: 16px;
  h4 {
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 8px;
  }
}

.error-title {
  color: #dc2626;
}

.error-item {
  font-size: 12px;
  color: #dc2626;
  background: #fef2f2;
  padding: 8px;
  border-radius: 4px;
  margin-bottom: 4px;
}

/* ── 空状态 ── */

.empty-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--muted-foreground);

  .empty-icon {
    font-size: 32px;
    opacity: 0.3;
    margin-bottom: 8px;
  }

  p {
    font-size: 13px;
  }
}
</style>
