<template>
  <div class="task-editor">
    <!-- 头部 -->
    <div class="editor-header">
      <div class="header-left">
        <el-button type="text" icon="el-icon-arrow-left" @click="goBack" />
        <div>
          <h2 class="header-title">{{ headerTitle }}</h2>
          <p class="header-sub">
            {{ task.taskName || '未命名任务' }}
            <span v-if="persistedCode" class="header-code">({{ persistedCode }})</span>
          </p>
        </div>
      </div>
      <div class="header-actions">
        <el-button
          v-if="persistedCode && task.status === 'PUBLISHED' && !readOnly"
          size="small"
          plain
          @click="openRunDialog"
        >
          <font-awesome-icon icon="play" class="play-icon" /> 执行
        </el-button>
        <template v-if="!readOnly">
          <el-button size="small" plain :loading="validating" @click="handleValidate">
            <font-awesome-icon v-if="!validating" icon="check-double" /> 校验
          </el-button>
          <el-button size="small" plain :loading="saving" @click="save">
            <font-awesome-icon v-if="!saving" icon="floppy-disk" /> 保存
          </el-button>
          <el-button size="small" type="primary" :loading="publishing" @click="handlePublish">
            <font-awesome-icon v-if="!publishing" icon="paper-plane" /> 发布
          </el-button>
        </template>
      </div>
    </div>

    <!-- 校验问题 -->
    <div v-if="issues.length > 0" class="issues-bar">
      <div
        v-for="(issue, i) in issues"
        :key="i"
        :class="['issue-item', issue.level === 'ERROR' ? 'issue--error' : 'issue--warn']"
      >
        [{{ issue.level }}] {{ issue.field }}: {{ issue.message }}
      </div>
    </div>

    <!-- 主内容：双栏 -->
    <div class="editor-body">
      <!-- 左侧 -->
      <div class="editor-left">
        <div class="left-scroll">
          <!-- 基本信息 -->
          <div class="section">
            <h3 class="section-title">基本信息</h3>
            <div class="form-field">
              <label class="field-label">任务编码</label>
              <el-input
                v-model="task.taskCode"
                :disabled="readOnly || !!persistedCode"
                placeholder="如: create_test_data"
                size="small"
                class="mono-input"
              />
            </div>
            <div class="form-field">
              <label class="field-label">任务名称</label>
              <el-input
                v-model="task.taskName"
                :disabled="readOnly"
                placeholder="如: 电商测试数据生成"
                size="small"
              />
            </div>
            <div class="form-field">
              <label class="field-label">备注</label>
              <el-input
                v-model="task.taskRemark"
                :disabled="readOnly"
                type="textarea"
                :rows="3"
                placeholder="任务说明..."
                size="small"
              />
            </div>
          </div>

          <!-- 步骤列表 -->
          <div class="section">
            <div class="section-header">
              <h3 class="section-title">场景步骤</h3>
              <el-button v-if="!readOnly" size="mini" plain @click="addStep">
                <font-awesome-icon icon="plus" /> 添加步骤
              </el-button>
            </div>

            <div v-if="task.steps.length === 0" class="empty-steps">
              暂无步骤，点击"添加步骤"编排场景
            </div>

            <div v-else class="step-list">
              <div
                v-for="(step, idx) in task.steps"
                :key="step.stepId"
                :class="['step-item', { 'step-item--active': selectedStepId === step.stepId }]"
                @click="selectedStepId = step.stepId"
              >
                <span class="step-idx">{{ idx + 1 }}</span>
                <div class="step-info">
                  <div class="step-name">{{ step.stepName || step.stepId }}</div>
                  <div class="step-scene">{{ sceneNameByCode(step.sceneCode) }}</div>
                </div>
                <el-switch
                  v-model="step.enabled"
                  :disabled="readOnly"
                  @click.native.stop
                />
              </div>
            </div>
          </div>

          <!-- 版本历史 -->
          <div v-if="versions.length > 0" class="section">
            <el-collapse>
              <el-collapse-item :title="`版本历史 (${versions.length})`">
                <div v-for="v in versions" :key="v.id" class="version-item">
                  <el-tag :type="v.versionStatus === 'PUBLISHED' ? '' : 'info'" size="mini">
                    v{{ v.versionNo }}
                  </el-tag>
                  <span class="version-status">{{ v.versionStatus }}</span>
                  <span class="version-time">{{ formatDate(v.createdAt) }}</span>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </div>

      <!-- 右侧 -->
      <div class="editor-right">
        <div v-if="selectedStep" class="step-detail">
          <div class="detail-scroll">
            <!-- 步骤基本信息 -->
            <div class="section">
              <h3 class="section-title">步骤配置</h3>
              <div class="detail-grid">
                <div class="form-field">
                  <label class="field-label">步骤 ID</label>
                  <el-input
                    :value="selectedStep.stepId"
                    :disabled="readOnly"
                    size="small"
                    class="mono-input"
                    @input="onStepFieldChange('stepId', $event)"
                  />
                </div>
                <div class="form-field">
                  <label class="field-label">步骤名称</label>
                  <el-input
                    :value="selectedStep.stepName || ''"
                    :disabled="readOnly"
                    size="small"
                    @input="onStepFieldChange('stepName', $event)"
                  />
                </div>
              </div>
            </div>

            <!-- 场景选择 -->
            <div class="section">
              <h3 class="section-title">关联场景</h3>
              <el-select
                :value="selectedStep.sceneCode || ''"
                :disabled="readOnly"
                placeholder="选择要执行的场景..."
                size="small"
                filterable
                style="width: 100%"
                @input="onStepFieldChange('sceneCode', $event)"
              >
                <el-option
                  v-for="sc in publishedScenes"
                  :key="sc.sceneCode"
                  :label="sc.sceneName + ' (' + sc.sceneCode + ')'"
                  :value="sc.sceneCode"
                />
              </el-select>
              <p v-if="selectedStep.sceneCode" class="scene-hint">
                运行时将执行场景 "{{ selectedStep.sceneCode }}" 的已发布版本。
              </p>
            </div>

            <!-- 依赖步骤 -->
            <div class="section">
              <h3 class="section-title">依赖步骤</h3>
              <div v-if="availableSteps.length > 0" class="dep-tags">
                <button
                  v-for="s in availableSteps"
                  :key="s.stepId"
                  :class="['dep-tag', { 'dep-tag--active': selectedStep.dependsOn.includes(s.stepId) }]"
                  :disabled="readOnly"
                  @click="toggleDependsOn(s.stepId)"
                >
                  {{ s.stepName || s.stepId }}
                </button>
              </div>
              <p v-else class="empty-hint">无其他步骤可依赖</p>
            </div>

            <!-- 参数映射 -->
            <div class="section">
              <el-collapse v-model="mappingOpen">
                <el-collapse-item title="参数映射">
                  <div class="form-field">
                    <label class="field-label">输入映射 (JSON)</label>
                    <p class="field-hint">任务变量 → 场景输入参数的映射</p>
                    <el-input
                      type="textarea"
                      :rows="6"
                      :disabled="readOnly"
                      :value="jsonStringify(selectedStep.inputMapping)"
                      class="mono-textarea"
                      @input="onInputMappingChange"
                    />
                  </div>
                  <div class="form-field">
                    <label class="field-label">输出映射 (JSON)</label>
                    <p class="field-hint">场景输出 → 任务变量的映射</p>
                    <el-input
                      type="textarea"
                      :rows="4"
                      :disabled="readOnly"
                      :value="jsonStringify(selectedStep.outputMapping)"
                      class="mono-textarea"
                      @input="onOutputMappingChange"
                    />
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>

            <!-- 删除 -->
            <div v-if="!readOnly" class="section section--border-top">
              <el-button type="danger" size="small" @click="removeStep(selectedStep.stepId)">
                <font-awesome-icon icon="trash" /> 删除此步骤
              </el-button>
            </div>
          </div>
        </div>
        <div v-else class="no-selection">
          选择左侧步骤进行配置，或添加新步骤
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import {
  createTask,
  getTask,
  listScenes,
  listTaskVersions,
  publishTask,
  updateTask,
  validateTask,
} from '@/datagen/common/lib/api'
import { createDefaultTask } from '@/datagen/common/lib/defaults'
import type {
  SceneSummary,
  TaskDefinition,
  TaskStepDefinition,
  TaskValidationIssue,
  TaskVersion,
} from '@/datagen/common/lib/types'

/**
 * 造数任务编辑器。
 * 从 React TaskEditor 跨框架重写为 Vue 2 + Element UI。
 * 支持新增、编辑、只读三种模式（由路由决定）。
 */
export default Vue.extend({
  name: 'TaskEditor',
  data() {
    return {
      task: createDefaultTask() as TaskDefinition,
      persistedCode: null as string | null,
      saving: false,
      publishing: false,
      validating: false,
      loading: false,
      issues: [] as TaskValidationIssue[],
      scenes: [] as SceneSummary[],
      versions: [] as TaskVersion[],
      selectedStepId: null as string | null,
      mappingOpen: ['mapping'],
    }
  },
  computed: {
    readOnly(): boolean {
      return this.$route.path.includes('/view/')
    },
    taskCode(): string {
      return (this.$route.params.code as string) || ''
    },
    headerTitle(): string {
      if (!this.persistedCode) return '新增任务'
      return this.readOnly ? '查看任务' : '编辑任务'
    },
    selectedStep(): TaskStepDefinition | null {
      if (!this.selectedStepId) return null
      return this.task.steps.find((s) => s.stepId === this.selectedStepId) ?? null
    },
    publishedScenes(): SceneSummary[] {
      return this.scenes.filter((s) => s.status === 'PUBLISHED')
    },
    availableSteps(): TaskStepDefinition[] {
      return this.task.steps.filter((s) => s.stepId !== this.selectedStepId)
    },
  },
  created() {
    if (this.taskCode) {
      this.loading = true
      getTask(this.taskCode)
        .then((data) => {
          this.task = this.normalizeTask(data)
          this.persistedCode = this.taskCode
        })
        .catch((err) => {
          this.$message.error(err instanceof Error ? err.message : '加载失败')
          this.goBack()
        })
        .finally(() => { this.loading = false })
    }
    listScenes({ limit: 500 })
      .then((result) => { this.scenes = result })
      .catch(() => { this.$message.error('加载场景列表失败') })
    if (this.taskCode) {
      listTaskVersions(this.taskCode)
        .then((v) => { this.versions = v })
        .catch(() => {})
    }
  },
  methods: {
    goBack() {
      this.$router.push('/datagen/tasks').catch(() => {})
    },
    sceneNameByCode(code: string): string {
      const scene = this.scenes.find((s) => s.sceneCode === code)
      return scene ? scene.sceneName : code || '未选择场景'
    },
    async save(showToast = true): Promise<string | null> {
      if (this.readOnly) return this.persistedCode
      if (!this.task.taskCode || !this.task.taskName) {
        if (showToast) this.$message.error('请先填写任务编码和名称')
        return null
      }
      this.saving = true
      try {
        const version = this.persistedCode
          ? await updateTask(this.persistedCode, this.task)
          : await createTask(this.task)
        this.task = this.normalizeTask(version.definition)
        this.persistedCode = version.taskCode
        if (showToast) this.$message.success(`已保存 (v${version.versionNo})`)
        return version.taskCode
      } catch (error) {
        if (showToast) this.$message.error(error instanceof Error ? error.message : '保存失败')
        return null
      } finally {
        this.saving = false
      }
    },
    async handleValidate() {
      const code = this.persistedCode ?? (await this.save(false))
      if (!code) return
      this.validating = true
      try {
        const result = await validateTask(code)
        this.issues = result.issues
        if (result.valid) {
          this.$message.success('校验通过')
        } else {
          this.$message.warning(`校验发现 ${result.issues.length} 个问题`)
        }
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '校验失败')
      } finally {
        this.validating = false
      }
    },
    async handlePublish() {
      const code = this.persistedCode ?? (await this.save(false))
      if (!code) return
      this.publishing = true
      try {
        const version = await publishTask(code)
        this.task = this.normalizeTask(version.definition)
        this.$message.success(`已发布 v${version.versionNo}`)
        this.goBack()
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '发布失败')
      } finally {
        this.publishing = false
      }
    },
    openRunDialog() {
      if (this.persistedCode) {
        this.$router.push(`/datagen/task/run/${encodeURIComponent(this.persistedCode)}`).catch(() => {})
      }
    },
    addStep() {
      if (this.readOnly) return
      const idx = this.task.steps.length
      const newStep: TaskStepDefinition = {
        stepId: `scene_step_${idx + 1}`,
        sceneCode: '',
        stepName: `步骤 ${idx + 1}`,
        enabled: true,
        dependsOn: [],
        inputMapping: {},
        outputMapping: {},
      }
      this.task = { ...this.task, steps: [...this.task.steps, newStep] }
      this.selectedStepId = newStep.stepId
    },
    removeStep(stepId: string) {
      if (this.readOnly) return
      this.task = {
        ...this.task,
        steps: this.task.steps.filter((s) => s.stepId !== stepId),
      }
      if (this.selectedStepId === stepId) this.selectedStepId = null
    },
    updateStep(updated: TaskStepDefinition) {
      this.task = {
        ...this.task,
        steps: this.task.steps.map((s) => (s.stepId === updated.stepId ? updated : s)),
      }
    },
    onStepFieldChange(field: string, value: string) {
      if (!this.selectedStep || this.readOnly) return
      this.updateStep({ ...this.selectedStep, [field]: value })
    },
    toggleDependsOn(stepId: string) {
      if (!this.selectedStep || this.readOnly) return
      const deps = this.selectedStep.dependsOn
      const next = deps.includes(stepId)
        ? deps.filter((id) => id !== stepId)
        : [...deps, stepId]
      this.updateStep({ ...this.selectedStep, dependsOn: next })
    },
    onInputMappingChange(value: string) {
      if (!this.selectedStep || this.readOnly) return
      try {
        this.updateStep({ ...this.selectedStep, inputMapping: JSON.parse(value) })
      } catch { /* 忽略无效 JSON */ }
    },
    onOutputMappingChange(value: string) {
      if (!this.selectedStep || this.readOnly) return
      try {
        this.updateStep({ ...this.selectedStep, outputMapping: JSON.parse(value) })
      } catch { /* 忽略无效 JSON */ }
    },
    jsonStringify(value: unknown): string {
      try { return JSON.stringify(value, null, 2) }
      catch { return '{}' }
    },
    normalizeTask(task: TaskDefinition): TaskDefinition {
      return {
        ...task,
        inputSchema: task.inputSchema || [],
        steps: (task.steps || []).map((s) => ({
          ...s,
          dependsOn: s.dependsOn || [],
          enabled: s.enabled ?? true,
          inputMapping: s.inputMapping || {},
          outputMapping: s.outputMapping || {},
        })),
        resultMapping: task.resultMapping || {},
      }
    },
    formatDate(value: string): string {
      if (!value) return '-'
      const d = new Date(value)
      return Number.isNaN(d.getTime()) ? value : d.toLocaleString()
    },
  },
})
</script>

<style scoped>
.task-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background);
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border);
  padding: 8px 24px;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--foreground);
}

.header-sub {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--muted-foreground);
}

.header-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.header-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.play-icon {
  color: #16a34a;
}

.issues-bar {
  border-bottom: 1px solid var(--border);
  background: #fffbeb;
  padding: 8px 24px;
  flex-shrink: 0;
}

.issue-item {
  font-size: 12px;
  padding: 2px 0;
}

.issue--error {
  color: #dc2626;
}

.issue--warn {
  color: #d97706;
}

.editor-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.editor-left {
  width: 360px;
  border-right: 1px solid var(--border);
  flex-shrink: 0;
}

.left-scroll {
  height: 100%;
  overflow-y: auto;
  padding: 16px;
}

.editor-right {
  flex: 1;
  min-width: 0;
}

.section {
  margin-bottom: 16px;
}

.section--border-top {
  border-top: 1px solid var(--border);
  padding-top: 16px;
}

.section-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.section-header .section-title {
  margin: 0;
}

.form-field {
  margin-bottom: 12px;
}

.field-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--muted-foreground);
  margin-bottom: 4px;
}

.field-hint {
  font-size: 10px;
  color: var(--muted-foreground);
  margin: 0 0 4px;
}

.mono-input >>> input {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.mono-textarea >>> textarea {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.empty-steps {
  border: 1px dashed var(--border);
  border-radius: 6px;
  padding: 16px;
  text-align: center;
  font-size: 12px;
  color: var(--muted-foreground);
}

.step-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.step-item {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
  cursor: pointer;
  transition: background 0.15s;
  font-size: 12px;
}

.step-item:hover {
  background: var(--accent);
}

.step-item--active {
  border-color: var(--primary);
  background: rgba(59, 130, 246, 0.05);
}

.step-idx {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--muted-foreground);
  width: 20px;
  text-align: center;
  flex-shrink: 0;
}

.step-info {
  flex: 1;
  min-width: 0;
}

.step-name {
  font-weight: 500;
  color: var(--foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-scene {
  font-size: 10px;
  color: var(--muted-foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  color: var(--muted-foreground);
  padding: 2px 0;
}

.version-status {
  font-size: 10px;
}

.version-time {
  font-size: 10px;
}

.step-detail {
  height: 100%;
}

.detail-scroll {
  height: 100%;
  overflow-y: auto;
  padding: 24px;
  max-width: 720px;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.scene-hint {
  font-size: 12px;
  color: var(--muted-foreground);
  margin: 8px 0 0;
}

.dep-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.dep-tag {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--card);
  color: var(--foreground);
}

.dep-tag:hover {
  background: var(--accent);
}

.dep-tag--active {
  border-color: var(--primary);
  background: rgba(59, 130, 246, 0.1);
  color: var(--primary);
}

.dep-tag:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.empty-hint {
  font-size: 12px;
  color: var(--muted-foreground);
  font-style: italic;
  margin: 0;
}

.no-selection {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--muted-foreground);
  font-size: 14px;
}
</style>
