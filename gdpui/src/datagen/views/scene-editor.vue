<template>
  <div class="scene-editor">
    <!-- ── loading ── -->
    <div v-if="loading" class="editor-loading">
      <i class="el-icon-loading" /> 加载中...
    </div>

    <template v-else>
      <!-- ── sidebar ── -->
      <aside class="editor-sidebar" :class="{ collapsed: !sidebarExpanded }">
        <div class="sidebar-header">
          <el-button type="text" @click="goBack">
            <font-awesome-icon icon="arrow-left" />
            <span v-if="sidebarExpanded" class="ml-1">返回</span>
          </el-button>
          <el-button
            v-if="sidebarExpanded"
            type="text"
            class="collapse-btn"
            @click="sidebarExpanded = false"
          >
            <font-awesome-icon icon="angles-left" />
          </el-button>
        </div>

        <div v-if="sidebarExpanded" class="sidebar-scene-info">
          <div class="info-name">{{ scene.sceneName || '新建场景' }}</div>
          <div class="info-code">{{ scene.sceneCode || '未设置编码' }}</div>
          <el-tag v-if="scene.status" :type="statusTagType(scene.status)" size="mini">
            {{ statusLabel(scene.status) }}
          </el-tag>
        </div>

        <el-menu
          :default-active="String(currentStep)"
          :collapse="!sidebarExpanded"
          class="sidebar-menu"
          @select="onStepSelect"
        >
          <el-menu-item v-for="(step, idx) in STEPS" :key="idx" :index="String(idx)">
            <font-awesome-icon :icon="step.icon" />
            <span slot="title">
              {{ step.title }}
              <span v-if="stepIssueCounts[idx].errors" class="error-dot" />
            </span>
          </el-menu-item>
        </el-menu>

        <div class="sidebar-actions">
          <template v-if="sidebarExpanded">
            <el-button size="small" :loading="saving" @click="save">
              <font-awesome-icon v-if="!saving" icon="floppy-disk" />
              保存
            </el-button>
            <el-button size="small" type="success" :loading="publishing" @click="runPublish">
              <font-awesome-icon v-if="!publishing" icon="cloud-arrow-up" />
              发布
            </el-button>
            <el-button
              v-if="canRun"
              size="small"
              type="primary"
              plain
              @click="showRunDialog = true"
            >
              <font-awesome-icon icon="play" /> 执行
            </el-button>
          </template>
          <template v-else>
            <el-button type="text" title="保存" @click="save">
              <font-awesome-icon icon="floppy-disk" />
            </el-button>
            <el-button type="text" title="发布" @click="runPublish">
              <font-awesome-icon icon="cloud-arrow-up" />
            </el-button>
          </template>
        </div>
      </aside>

      <!-- ── main content ── -->
      <div class="editor-main">
        <header class="editor-header">
          <div class="header-left">
            <el-button
              v-if="!sidebarExpanded"
              type="text"
              @click="sidebarExpanded = true"
            >
              <font-awesome-icon icon="angles-right" />
            </el-button>
            <h2>{{ scene.sceneName || '新建场景' }}</h2>
            <el-tag size="mini" type="info">步骤 {{ currentStep + 1 }} / {{ STEPS.length }}</el-tag>
          </div>
          <div class="header-right">
            <el-tag v-if="saving" size="small" type="warning">保存中...</el-tag>
            <el-tag v-if="!hasUnsavedChanges" size="small" type="success">已保存</el-tag>
            <el-tag v-else size="small" type="warning">未保存</el-tag>
          </div>
        </header>

        <div class="editor-body">
          <!-- Step 0: 基础配置 -->
          <div v-if="currentStep === 0" class="step-panel">
            <el-form label-position="top" :disabled="readOnly">
              <el-form-item label="场景编码" required>
                <el-input v-model="scene.sceneCode" placeholder="唯一编码，如 create_order" :disabled="!!persistedSceneCode" />
              </el-form-item>
              <el-form-item label="场景名称" required>
                <el-input v-model="scene.sceneName" placeholder="显示名称" />
              </el-form-item>
              <el-form-item label="场景描述">
                <el-input v-model="scene.sceneRemark" type="textarea" :rows="3" placeholder="描述场景用途" />
              </el-form-item>
              <el-form-item label="业务分类">
                <el-input v-model="scene.sceneType" placeholder="如：订单、用户" />
              </el-form-item>
              <el-form-item label="错误策略">
                <el-select v-model="scene.errorPolicy">
                  <el-option label="遇错停止" value="STOP_ON_ERROR" />
                  <el-option label="遇错继续" value="CONTINUE_ON_ERROR" />
                </el-select>
              </el-form-item>
            </el-form>
          </div>

          <!-- Step 1: 参数配置 -->
          <div v-if="currentStep === 1" class="step-panel">
            <div class="panel-toolbar">
              <h3>输入参数定义</h3>
              <el-button v-if="!readOnly" size="small" type="primary" plain @click="addInputField">
                <font-awesome-icon icon="plus" /> 添加字段
              </el-button>
            </div>
            <el-table :data="scene.inputSchema" row-key="name" border size="small">
              <el-table-column label="字段名" width="160">
                <template #default="{ row, $index }">
                  <el-input v-model="row.name" size="small" :disabled="row.name === 'env' || readOnly" @input="onFieldChange($index)" />
                </template>
              </el-table-column>
              <el-table-column label="标签" width="140">
                <template #default="{ row }">
                  <el-input v-model="row.label" size="small" :disabled="row.name === 'env' || readOnly" />
                </template>
              </el-table-column>
              <el-table-column label="类型" width="120">
                <template #default="{ row }">
                  <el-select v-model="row.type" size="small" :disabled="row.name === 'env' || readOnly">
                    <el-option v-for="t in FIELD_TYPES" :key="t" :label="t" :value="t" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="必填" width="70" align="center">
                <template #default="{ row }">
                  <el-switch v-model="row.required" :disabled="row.name === 'env' || readOnly" />
                </template>
              </el-table-column>
              <el-table-column label="批量" width="70" align="center">
                <template #default="{ row }">
                  <el-switch v-model="row.batchEnabled" :disabled="row.name === 'env' || readOnly" />
                </template>
              </el-table-column>
              <el-table-column label="备注" min-width="160">
                <template #default="{ row }">
                  <el-input v-model="row.remark" size="small" placeholder="备注" :disabled="row.name === 'env' || readOnly" />
                </template>
              </el-table-column>
              <el-table-column v-if="!readOnly" label="" width="60" align="center">
                <template #default="{ row, $index }">
                  <el-button
                    v-if="row.name !== 'env'"
                    type="text"
                    size="small"
                    icon="el-icon-delete"
                    class="text-danger"
                    @click="removeInputField($index)"
                  />
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- Step 2: 逻辑编排 -->
          <div v-if="currentStep === 2" class="step-panel step-orchestration">
            <div class="panel-toolbar">
              <h3>步骤编排</h3>
              <div v-if="!readOnly" class="toolbar-actions">
                <el-button size="small" @click="addStep('HTTP')">
                  <font-awesome-icon icon="plus" /> HTTP 步骤
                </el-button>
                <el-button size="small" @click="addStep('SQL')">
                  <font-awesome-icon icon="plus" /> SQL 步骤
                </el-button>
              </div>
            </div>

            <div class="orchestration-body">
              <!-- Step list -->
              <div class="step-list">
                <div
                  v-for="(step, idx) in scene.steps"
                  :key="step.stepId"
                  class="step-item"
                  :class="{ active: selectedStepId === step.stepId, disabled: !step.enabled }"
                  @click="selectedStepId = step.stepId"
                >
                  <div class="step-order">{{ idx + 1 }}</div>
                  <div class="step-info">
                    <div class="step-title">{{ step.stepName || step.stepId }}</div>
                    <div class="step-meta">
                      <el-tag size="mini" :type="step.type === 'HTTP' ? '' : 'warning'">{{ step.type }}</el-tag>
                      <span v-if="!step.enabled" class="text-muted">已禁用</span>
                    </div>
                  </div>
                  <el-button
                    v-if="!readOnly"
                    type="text"
                    size="small"
                    icon="el-icon-delete"
                    class="text-danger"
                    @click.stop="deleteStep(step.stepId)"
                  />
                </div>
                <div v-if="scene.steps.length === 0" class="step-empty">
                  暂无步骤，点击上方按钮添加
                </div>
              </div>

              <!-- Step detail -->
              <div v-if="selectedStep" class="step-detail">
                <el-form label-position="top" size="small" :disabled="readOnly">
                  <div class="detail-row">
                    <el-form-item label="步骤名称">
                      <el-input v-model="selectedStep.stepName" />
                    </el-form-item>
                    <el-form-item label="启用">
                      <el-switch v-model="selectedStep.enabled" />
                    </el-form-item>
                  </div>
                  <el-form-item label="描述">
                    <el-input v-model="selectedStep.description" type="textarea" :rows="2" />
                  </el-form-item>
                  <el-form-item label="依赖步骤 (stepId)">
                    <el-input v-model="selectedStep.dependsOnStr" placeholder="逗号分隔" />
                  </el-form-item>

                  <!-- HTTP step fields -->
                  <template v-if="selectedStep.type === 'HTTP'">
                    <el-divider content-position="left">
                      HTTP 配置
                      <el-button
                        v-if="!readOnly"
                        type="primary"
                        size="mini"
                        plain
                        class="test-step-btn"
                        @click="openTestDialog"
                      >
                        <font-awesome-icon icon="flask" /> 测试
                      </el-button>
                    </el-divider>
                    <div class="detail-row">
                      <el-form-item label="请求方式">
                        <el-select v-model="selectedStep.method">
                          <el-option label="GET" value="GET" />
                          <el-option label="POST" value="POST" />
                        </el-select>
                      </el-form-item>
                      <el-form-item label="系统">
                        <el-input v-model="selectedStep.sysCode" placeholder="sysCode" />
                      </el-form-item>
                    </div>
                    <el-form-item label="路径">
                      <el-input v-model="selectedStep.path" placeholder="/api/path" />
                    </el-form-item>
                    <el-form-item label="超时 (秒)">
                      <div v-if="selectedStep.timeoutConfig" class="timeout-grid">
                        <el-input-number v-model="selectedStep.timeoutConfig.connectTimeoutSeconds" :min="1" :max="300" controls-position="right" />
                        <el-input-number v-model="selectedStep.timeoutConfig.readTimeoutSeconds" :min="1" :max="300" controls-position="right" />
                        <el-input-number v-model="selectedStep.timeoutConfig.writeTimeoutSeconds" :min="1" :max="300" controls-position="right" />
                      </div>
                      <div class="timeout-labels">
                        <span>连接</span><span>读</span><span>写</span>
                      </div>
                    </el-form-item>
                    <el-form-item label="请求映射 (JSON)">
                      <el-input v-model="selectedStep.requestMappingJson" type="textarea" :rows="4" placeholder='{"headers":{},"query":{},"body":{}}' />
                    </el-form-item>
                    <el-form-item label="HTTP 参数映射 (JSON)">
                      <el-input v-model="selectedStep.httpParamMappingJson" type="textarea" :rows="3" placeholder="{}" />
                    </el-form-item>

                    <!-- Template import button -->
                    <el-button size="mini" plain @click="showTemplateDialog = true">
                      <font-awesome-icon icon="download" /> 从模板导入
                    </el-button>

                    <!-- HTTP Response Mapping Editor -->
                    <http-response-mapping-editor
                      :step="scene.steps.find(s => s.stepId === selectedStepId)"
                      :disabled="readOnly"
                      @change="onHttpResponseChange"
                    />
                  </template>

                  <!-- SQL step fields -->
                  <template v-if="selectedStep.type === 'SQL'">
                    <el-divider content-position="left">SQL 配置</el-divider>
                    <div class="detail-row">
                      <el-form-item label="系统">
                        <el-input v-model="selectedStep.sysCode" placeholder="sysCode" />
                      </el-form-item>
                      <el-form-item label="数据源">
                        <el-input v-model="selectedStep.datasourceCode" placeholder="datasourceCode" />
                      </el-form-item>
                    </div>
                    <div class="detail-row">
                      <el-form-item label="操作类型">
                        <el-select v-model="selectedStep.operation">
                          <el-option v-for="op in SQL_OPS" :key="op" :label="op" :value="op" />
                        </el-select>
                      </el-form-item>
                    </div>
                    <el-form-item label="SQL 语句">
                      <el-input v-model="selectedStep.sqlText" type="textarea" :rows="6" placeholder="SELECT / INSERT / UPDATE / DELETE" />
                    </el-form-item>
                    <el-form-item label="参数映射 (JSON)">
                      <el-input v-model="selectedStep.paramMappingJson" type="textarea" :rows="3" placeholder="{}" />
                    </el-form-item>

                    <!-- Template import button -->
                    <el-button size="mini" plain @click="showTemplateDialog = true">
                      <font-awesome-icon icon="download" /> 从模板导入
                    </el-button>

                    <!-- SQL Output Extraction Editor -->
                    <sql-output-extraction-editor
                      :step="scene.steps.find(s => s.stepId === selectedStepId)"
                      :disabled="readOnly"
                      @change="onSqlOutputChange"
                    />
                  </template>

                  <!-- Output mapping -->
                  <el-divider content-position="left">输出映射</el-divider>
                  <el-form-item label="输出映射 (JSON)">
                    <el-input v-model="selectedStep.outputMappingJson" type="textarea" :rows="3" placeholder='{"key": "expression"}' />
                  </el-form-item>
                </el-form>
              </div>

              <div v-else class="step-detail step-detail-empty">
                <p class="text-muted">选择左侧步骤查看配置</p>
              </div>
            </div>
          </div>

          <!-- Step 3: 结果输出 -->
          <div v-if="currentStep === 3" class="step-panel">
            <div class="panel-toolbar">
              <h3>结果输出配置</h3>
            </div>

            <h4>结果 Schema</h4>
            <el-table :data="resultSchemaFields" border size="small">
              <el-table-column label="字段名" width="160">
                <template #default="{ row }">
                  <el-input v-model="row.name" size="small" :disabled="readOnly" />
                </template>
              </el-table-column>
              <el-table-column label="标签" width="140">
                <template #default="{ row }">
                  <el-input v-model="row.label" size="small" :disabled="readOnly" />
                </template>
              </el-table-column>
              <el-table-column label="类型" width="120">
                <template #default="{ row }">
                  <el-select v-model="row.type" size="small" :disabled="readOnly">
                    <el-option v-for="t in FIELD_TYPES" :key="t" :label="t" :value="t" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="必填" width="70" align="center">
                <template #default="{ row }">
                  <el-switch v-model="row.required" :disabled="readOnly" />
                </template>
              </el-table-column>
              <el-table-column v-if="!readOnly" label="" width="60" align="center">
                <template #default="{ $index }">
                  <el-button type="text" size="small" icon="el-icon-delete" class="text-danger" @click="removeResultField($index)" />
                </template>
              </el-table-column>
            </el-table>
            <el-button v-if="!readOnly" size="small" class="mt-2" @click="addResultField">
              <font-awesome-icon icon="plus" /> 添加结果字段
            </el-button>

            <el-divider />
            <h4>结果映射</h4>
            <el-form :disabled="readOnly">
              <div v-for="(_, key) in scene.resultMapping" :key="key" class="mapping-row">
                <el-input :value="String(key)" size="small" disabled class="mapping-key" />
                <span class="mapping-arrow">→</span>
                <el-input v-model="scene.resultMapping[key]" size="small" :disabled="readOnly" class="mapping-value" />
                <el-button v-if="!readOnly" type="text" icon="el-icon-delete" class="text-danger" @click="removeResultMapping(String(key))" />
              </div>
              <el-button v-if="!readOnly" size="small" @click="addResultMapping">
                <font-awesome-icon icon="plus" /> 添加映射
              </el-button>
            </el-form>
          </div>

          <!-- Step 4: 批量设置 -->
          <div v-if="currentStep === 4" class="step-panel">
            <el-form label-position="top" :disabled="readOnly">
              <el-form-item label="启用批量执行">
                <el-switch v-model="scene.batchConfig.enabled" />
              </el-form-item>
              <el-form-item label="失败策略">
                <el-select v-model="scene.batchConfig.failurePolicy">
                  <el-option label="遇错停止" value="STOP_ON_ERROR" />
                  <el-option label="遇错继续" value="CONTINUE_ON_ERROR" />
                </el-select>
              </el-form-item>
              <el-form-item label="最大并发数">
                <el-input-number v-model="scene.batchConfig.maxConcurrency" :min="1" :max="100" />
              </el-form-item>
            </el-form>
          </div>
        </div>

        <!-- Step navigation -->
        <footer class="editor-footer">
          <el-button :disabled="currentStep === 0" @click="prevStep">
            <font-awesome-icon icon="arrow-left" /> 上一步
          </el-button>
          <el-button :disabled="currentStep === STEPS.length - 1" type="primary" @click="nextStep">
            下一步 <font-awesome-icon icon="arrow-right" />
          </el-button>
        </footer>
      </div>
    </template>

    <!-- ── Run dialog ── -->
    <scene-run-dialog
      :scene="scene"
      :scene-code="persistedSceneCode || ''"
      :visible.sync="showRunDialog"
    />

    <!-- ── Step test dialog ── -->
    <step-test-dialog
      v-if="testStep"
      :step="testStep"
      :scene="scene"
      :visible.sync="showTestDialog"
      @test-success="onStepTestSuccess"
    />

    <!-- ── Template import dialog ── -->
    <template-import-dialog
      v-if="selectedStep"
      :visible.sync="showTemplateDialog"
      :step="selectedStep"
      :http-sources="httpSources"
      :sql-sources="sqlSources"
      @import="onTemplateImport"
    />
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import SceneRunDialog from '@/datagen/components/scene-run-dialog.vue'
import StepTestDialog from '@/datagen/components/step-test-dialog.vue'
import HttpResponseMappingEditor from '@/datagen/components/http-response-mapping-editor.vue'
import SqlOutputExtractionEditor from '@/datagen/components/sql-output-extraction-editor.vue'
import TemplateImportDialog from '@/datagen/components/template-import-dialog.vue'

import {
  createScene,
  getScene,
  listEnvironments,
  listHttpSources,
  listSqlSources,
  publishScene,
  updateScene,
} from '@/datagen/common/lib/api'
import {
  createDefaultScene,
  createDefaultStep,
  INPUT_FIELD_TYPES,
  SQL_OPERATIONS,
} from '@/datagen/common/lib/defaults'
import type {
  EnvironmentResponse,
  HttpSourceResponse,
  HttpSourceTestResult,
  HttpStepDefinition,
  InputFieldDefinition,
  SceneDefinition,
  SceneStatus,
  SqlSourceResponse,
  StepDefinition,
  StepType,
  ValidationIssue,
} from '@/datagen/common/lib/types'

interface StepMeta {
  title: string
  description: string
  icon: string
}

const STEPS: StepMeta[] = [
  { title: '基础配置', description: '定义场景基本信息', icon: 'circle-info' },
  { title: '参数配置', description: '配置场景输入参数', icon: 'file-code' },
  { title: '逻辑编排', description: '编排执行步骤与逻辑', icon: 'layer-group' },
  { title: '结果输出', description: '配置最终返回结果', icon: 'table-cells' },
  { title: '批量设置', description: '配置批量执行策略', icon: 'gears' },
]

const FIELD_TYPES = INPUT_FIELD_TYPES
const SQL_OPS = SQL_OPERATIONS

/** Proxy around a step definition so we can expose computed JSON string
 *  helpers for textarea bindings without mutating the original object. */
interface StepProxy {
  [key: string]: unknown
  stepId: string
  stepName: string | null | undefined
  type: StepType
  enabled: boolean
  description: string | null | undefined
  dependsOn: string[]
  dependsOnStr: string
  outputMapping: Record<string, string>
  outputMappingJson: string
  // HTTP
  method?: string
  path?: string | null
  sysCode?: string | null
  timeoutConfig?: { connectTimeoutSeconds: number; readTimeoutSeconds: number; writeTimeoutSeconds: number; poolTimeoutSeconds: number }
  requestMapping?: Record<string, unknown>
  requestMappingJson?: string
  httpParamMapping?: Record<string, unknown>
  httpParamMappingJson?: string
  datasourceCode?: string | null
  operation?: string | null
  sqlText?: string | null
  paramMapping?: Record<string, unknown>
  paramMappingJson?: string
}

export default Vue.extend({
  name: 'SceneEditor',
  components: {
    SceneRunDialog,
    StepTestDialog,
    HttpResponseMappingEditor,
    SqlOutputExtractionEditor,
    TemplateImportDialog,
  },

  data() {
    return {
      STEPS,
      FIELD_TYPES,
      SQL_OPS,
      currentStep: 0,
      scene: createDefaultScene(),
      persistedSceneCode: null as string | null,
      lastSavedSnapshot: null as string | null,
      saving: false,
      publishing: false,
      loading: false,
      readOnly: false,
      sidebarExpanded: true,
      selectedStepId: null as string | null,
      // sources
      httpSources: [] as HttpSourceResponse[],
      sqlSources: [] as SqlSourceResponse[],
      // validation
      issues: [] as ValidationIssue[],
      // run dialog
      showRunDialog: false,
      environments: [] as EnvironmentResponse[],
      // step test dialog
      showTestDialog: false,
      testStep: null as HttpStepDefinition | null,
      testResult: null as HttpSourceTestResult | null,
      // template import dialog
      showTemplateDialog: false,
      // new mapping row
      newMappingKey: '',
      newMappingValue: '',
    }
  },

  computed: {
    selectedStep(): StepProxy | null {
      if (!this.selectedStepId) return null
      const step = this.scene.steps.find(s => s.stepId === this.selectedStepId)
      if (!step) return null
      return this.wrapStep(step)
    },

    resultSchemaFields(): InputFieldDefinition[] {
      return this.scene.resultSchema ?? []
    },

    hasUnsavedChanges(): boolean {
      if (!this.persistedSceneCode) return true
      return this.buildSnapshot() !== this.lastSavedSnapshot
    },

    canRun(): boolean {
      return !!this.persistedSceneCode && this.scene.status === 'PUBLISHED'
    },

    stepIssueCounts(): Array<{ errors: number; warnings: number }> {
      const counts = STEPS.map(() => ({ errors: 0, warnings: 0 }))
      for (const issue of this.issues) {
        let idx = -1
        if (['sceneCode', 'sceneName', 'sceneRemark'].includes(issue.field)) idx = 0
        else if (issue.field.startsWith('inputSchema')) idx = 1
        else if (issue.field.startsWith('step:') || issue.field.startsWith('steps[')) idx = 2
        else if (issue.field.startsWith('resultMapping') || issue.field.startsWith('resultSchema')) idx = 3
        else if (issue.field.startsWith('batchConfig')) idx = 4
        if (idx >= 0 && idx < counts.length) {
          if (issue.level === 'ERROR') counts[idx]!.errors++
          else if (issue.level === 'WARNING') counts[idx]!.warnings++
        }
      }
      return counts
    },
  },

  watch: {
    '$route.params.code': {
      immediate: true,
      handler(code: string | undefined) {
        this.initFromRoute(code)
      },
    },
  },

  created() {
    this.readOnly = this.$route.path.includes('/view/')
    this.initFromRoute(this.$route.params.code)
    // load sources
    listHttpSources().then(s => { this.httpSources = s }).catch(() => { this.httpSources = [] })
    listSqlSources().then(s => { this.sqlSources = s }).catch(() => { this.sqlSources = [] })
    listEnvironments().then(envs => {
      this.environments = envs.filter(e => e.status === 'ENABLED')
    }).catch(() => { this.environments = [] })
  },

  methods: {
    initFromRoute(code?: string) {
      if (code) {
        this.loading = true
        this.persistedSceneCode = code
        getScene(code)
          .then(data => {
            this.scene = this.normalizeScene(data)
            this.lastSavedSnapshot = this.buildSnapshot()
          })
          .catch(err => {
            this.$message.error(err instanceof Error ? err.message : '加载失败')
            this.goBack()
          })
          .finally(() => { this.loading = false })
      } else {
        this.scene = createDefaultScene()
        this.persistedSceneCode = null
        this.lastSavedSnapshot = null
      }
    },

    goBack() {
      this.$router.push('/datagen/scenes').catch(() => {})
    },

    onStepSelect(index: string) {
      const idx = parseInt(index, 10)
      if (!this.readOnly && this.hasUnsavedChanges) {
        this.save(false)
      }
      this.currentStep = idx
    },

    prevStep() {
      if (this.currentStep > 0) this.currentStep--
    },
    nextStep() {
      if (this.currentStep < STEPS.length - 1) this.currentStep++
    },

    // ── Save ──
    async save(showToast = true): Promise<string | null> {
      if (this.readOnly) return this.persistedSceneCode
      if (!this.scene.sceneCode || !this.scene.sceneName) {
        if (showToast) this.$message.error('请先填写场景编码和名称')
        return null
      }
      const payload = this.buildPayload()
      const snapshot = JSON.stringify(payload)
      if (this.persistedSceneCode && snapshot === this.lastSavedSnapshot) {
        if (showToast) this.$message.info('没有需要保存的变更')
        return this.persistedSceneCode
      }
      this.saving = true
      try {
        const version = this.persistedSceneCode
          ? await updateScene(this.persistedSceneCode, payload)
          : await createScene(payload)
        this.scene = this.normalizeScene(version.definition)
        this.lastSavedSnapshot = JSON.stringify(this.buildPayload())
        this.persistedSceneCode = version.sceneCode
        if (showToast) this.$message.success(`配置已保存 (v${version.versionNo})`)
        return version.sceneCode
      } catch (error) {
        if (showToast) this.$message.error(error instanceof Error ? error.message : '保存失败')
        return null
      } finally {
        this.saving = false
      }
    },

    // ── Publish ──
    async runPublish() {
      if (this.readOnly) return
      if (this.persistedSceneCode && this.scene.status === 'PUBLISHED' && !this.hasUnsavedChanges) {
        this.$message.info('当前版本已经发布，无需重复发布')
        return
      }
      this.publishing = true
      try {
        const code = this.hasUnsavedChanges ? await this.save(false) : this.persistedSceneCode
        if (!code) {
          this.$message.error('保存失败，无法发布')
          return
        }
        const version = await publishScene(code)
        this.scene = this.normalizeScene(version.definition)
        this.lastSavedSnapshot = JSON.stringify(this.buildPayload())
        this.$message.success(`已发布成功 v${version.versionNo}`)
        this.goBack()
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '发布失败')
      } finally {
        this.publishing = false
      }
    },

    // ── Execute ──
    /** 打开步骤测试弹窗（仅 HTTP 步骤） */
    openTestDialog() {
      const step = this.scene.steps.find(s => s.stepId === this.selectedStepId)
      if (!step || step.type !== 'HTTP') return
      this.testStep = step as unknown as HttpStepDefinition
      this.showTestDialog = true
    },

    /** 步骤测试成功回调，可选择更新 outputMapping */
    onStepTestSuccess(result: HttpSourceTestResult) {
      this.testResult = result
    },

    /** 模板导入回调 */
    onTemplateImport(updatedStep: StepDefinition) {
      const idx = this.scene.steps.findIndex(s => s.stepId === updatedStep.stepId)
      if (idx >= 0) {
        this.$set(this.scene.steps, idx, updatedStep)
        this.$message.success('模板配置已导入')
      }
    },

    /** HTTP 响应配置变更回调 */
    onHttpResponseChange(updates: Partial<HttpStepDefinition>) {
      const idx = this.scene.steps.findIndex(s => s.stepId === this.selectedStepId)
      if (idx >= 0) {
        const step = this.scene.steps[idx] as HttpStepDefinition
        this.$set(this.scene.steps, idx, { ...step, ...updates })
      }
    },

    /** SQL 输出提取变更回调 */
    onSqlOutputChange(updatedStep: StepDefinition) {
      const idx = this.scene.steps.findIndex(s => s.stepId === updatedStep.stepId)
      if (idx >= 0) {
        this.$set(this.scene.steps, idx, updatedStep)
      }
    },

    // ── Input schema ──
    addInputField() {
      this.scene.inputSchema.push({
        name: `field_${this.scene.inputSchema.length}`,
        label: '',
        remark: '',
        type: 'string',
        required: false,
        batchEnabled: false,
        defaultValue: null,
      })
    },
    removeInputField(index: number) {
      this.scene.inputSchema.splice(index, 1)
    },
    onFieldChange(_index: number) {
      // trigger reactivity
    },

    // ── Steps ──
    addStep(type: 'HTTP' | 'SQL') {
      const nextStep = createDefaultStep(type, this.scene.steps.length)
      this.scene.steps.push(this.assignOrder(nextStep, this.scene.steps.length))
      this.selectedStepId = nextStep.stepId
    },
    deleteStep(id: string) {
      this.scene.steps = this.scene.steps
        .filter(s => s.stepId !== id)
        .map((s, i) => ({ ...s, executionOrder: i + 1 }))
      if (this.selectedStepId === id) this.selectedStepId = null
    },

    // ── Result schema ──
    addResultField() {
      if (!this.scene.resultSchema) this.scene.resultSchema = []
      this.scene.resultSchema.push({
        name: `result_${this.scene.resultSchema.length}`,
        label: '',
        type: 'string',
        required: false,
        batchEnabled: false,
      })
    },
    removeResultField(index: number) {
      if (this.scene.resultSchema) {
        this.scene.resultSchema.splice(index, 1)
      }
    },

    // ── Result mapping ──
    addResultMapping() {
      const key = `output_${Object.keys(this.scene.resultMapping).length}`
      this.$set(this.scene.resultMapping, key, '')
    },
    removeResultMapping(key: string) {
      this.$delete(this.scene.resultMapping, key)
    },

    // ── Step proxy ──
    wrapStep(step: StepDefinition): StepProxy {
      const proxy: StepProxy = {
        ...step,
        stepName: step.stepName,
        description: step.description,
        dependsOnStr: (step.dependsOn || []).join(', '),
        outputMappingJson: JSON.stringify(step.outputMapping || {}, null, 2),
      }

      if (step.type === 'HTTP') {
        proxy.requestMappingJson = JSON.stringify((step as any).requestMapping || {}, null, 2)
        proxy.httpParamMappingJson = JSON.stringify((step as any).httpParamMapping || {}, null, 2)
      }
      if (step.type === 'SQL') {
        proxy.paramMappingJson = JSON.stringify((step as any).paramMapping || {}, null, 2)
      }

      // Create a reactive proxy that syncs back
      return new Proxy(proxy, {
        set: (target, prop, value) => {
          (target as any)[prop] = value
          this.syncStepBack(target)
          return true
        },
      })
    },

    syncStepBack(proxy: StepProxy) {
      const idx = this.scene.steps.findIndex(s => s.stepId === proxy.stepId)
      if (idx < 0) return

      const step: any = { ...this.scene.steps[idx] }
      step.stepName = proxy.stepName
      step.enabled = proxy.enabled
      step.description = proxy.description
      step.dependsOn = (proxy.dependsOnStr || '').split(',').map((s: string) => s.trim()).filter(Boolean)
      try { step.outputMapping = JSON.parse(proxy.outputMappingJson || '{}') } catch { /* ignore */ }

      if (step.type === 'HTTP') {
        step.method = proxy.method
        step.path = proxy.path
        step.sysCode = proxy.sysCode
        if (proxy.timeoutConfig) step.timeoutConfig = { ...proxy.timeoutConfig }
        try { step.requestMapping = JSON.parse(proxy.requestMappingJson || '{}') } catch { /* ignore */ }
        try { step.httpParamMapping = JSON.parse(proxy.httpParamMappingJson || '{}') } catch { /* ignore */ }
      }
      if (step.type === 'SQL') {
        step.sysCode = proxy.sysCode
        step.datasourceCode = proxy.datasourceCode
        step.operation = proxy.operation
        step.sqlText = proxy.sqlText
        try { step.paramMapping = JSON.parse(proxy.paramMappingJson || '{}') } catch { /* ignore */ }
      }

      this.$set(this.scene.steps, idx, step)
    },

    // ── Helpers ──
    buildSnapshot(): string {
      return JSON.stringify(this.buildPayload())
    },

    buildPayload(): SceneDefinition {
      return {
        ...this.scene,
        inputSchema: this.scene.inputSchema.map(f => ({ ...f })),
        steps: this.scene.steps.map((s, i) => ({ ...s, executionOrder: i + 1 })),
        resultSchema: (this.scene.resultSchema || []).map(f => ({ ...f })),
        resultMapping: { ...this.scene.resultMapping },
        batchConfig: { ...this.scene.batchConfig },
      }
    },

    normalizeScene(data: SceneDefinition): SceneDefinition {
      return {
        ...data,
        inputSchema: (data.inputSchema || []).map(f => ({ ...f, children: f.children ?? undefined })),
        batchConfig: data.batchConfig ?? createDefaultScene().batchConfig,
        resultSchema: data.resultSchema ?? [],
        resultMapping: this.normalizeResultMapping(data.resultMapping),
        errorPolicy: data.errorPolicy ?? 'STOP_ON_ERROR',
        steps: (data.steps || [])
          .map((s, i) => ({ ...s, executionOrder: s.executionOrder ?? i + 1 }))
          .sort((a, b) => (a.executionOrder ?? 0) - (b.executionOrder ?? 0))
          .map((s, i) => ({ ...s, executionOrder: i + 1 })),
      }
    },

    normalizeResultMapping(raw: Record<string, unknown> | Record<string, string> | undefined): Record<string, string> {
      if (!raw) return {}
      const result: Record<string, string> = {}
      for (const [k, v] of Object.entries(raw)) {
        result[k] = typeof v === 'string' ? v : JSON.stringify(v)
      }
      return result
    },

    assignOrder<T extends { executionOrder?: number | null }>(step: T, index: number): T {
      return { ...step, executionOrder: index + 1 }
    },

    statusLabel(status: SceneStatus): string {
      if (status === 'PUBLISHED') return '已发布'
      if (status === 'DISABLED') return '已停用'
      return '草稿'
    },
    statusTagType(status: SceneStatus): string {
      if (status === 'PUBLISHED') return 'success'
      if (status === 'DISABLED') return 'danger'
      return 'info'
    },
  },
})
</script>

<style scoped>
.scene-editor {
  display: flex;
  height: 100%;
  overflow: hidden;
  background: var(--background);
}

.editor-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  color: var(--muted-foreground);
  font-size: 14px;
}
.editor-loading i { margin-right: 8px; font-size: 20px; }

/* ── sidebar ── */
.editor-sidebar {
  display: flex;
  flex-direction: column;
  width: 260px;
  border-right: 1px solid var(--border);
  background: var(--card);
  transition: width 0.2s;
  flex-shrink: 0;
}
.editor-sidebar.collapsed { width: 56px; }

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-bottom: 1px solid var(--border);
}
.collapse-btn { margin-left: auto; }

.sidebar-scene-info {
  padding: 16px 12px;
  border-bottom: 1px solid var(--border);
}
.info-name {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 4px;
  color: var(--foreground);
}
.info-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--muted-foreground);
  margin-bottom: 8px;
}

.sidebar-menu {
  flex: 1;
  border: none;
  background: transparent;
}
.sidebar-menu .el-menu-item {
  font-size: 13px;
  height: 44px;
  line-height: 44px;
}
.sidebar-menu .el-menu-item i { margin-right: 8px; }

.error-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  background: var(--destructive, #f56c6c);
  border-radius: 50%;
  margin-left: 6px;
  vertical-align: middle;
}

.sidebar-actions {
  padding: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sidebar-actions .el-button { width: 100%; }

/* ── main ── */
.editor-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--card);
}
.header-left { display: flex; align-items: center; gap: 12px; }
.header-left h2 { margin: 0; font-size: 16px; font-weight: 600; }
.header-right { display: flex; align-items: center; gap: 8px; }

.editor-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.step-panel {
  max-width: 900px;
  margin: 0 auto;
}

.panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.panel-toolbar h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}
.toolbar-actions { display: flex; gap: 8px; }

/* ── orchestration ── */
.step-orchestration { max-width: none; }
.orchestration-body {
  display: flex;
  gap: 16px;
  min-height: 400px;
}

.step-list {
  width: 280px;
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow-y: auto;
  max-height: calc(100vh - 280px);
}

.step-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--border);
  transition: background 0.15s;
}
.step-item:last-child { border-bottom: none; }
.step-item:hover { background: var(--muted, #f5f5f5); }
.step-item.active { background: var(--primary-light, #ecf5ff); }
.step-item.disabled { opacity: 0.5; }

.step-order {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-info { flex: 1; min-width: 0; }
.step-title { font-size: 13px; font-weight: 500; }
.step-meta { display: flex; gap: 6px; align-items: center; margin-top: 2px; }

.step-empty {
  padding: 40px 16px;
  text-align: center;
  color: var(--muted-foreground);
  font-size: 13px;
}

.step-detail {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 20px;
  overflow-y: auto;
  max-height: calc(100vh - 280px);
}
.step-detail-empty {
  display: flex;
  align-items: center;
  justify-content: center;
}

.detail-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.timeout-grid {
  display: flex;
  gap: 8px;
}
.timeout-grid .el-input-number { flex: 1; }
.timeout-labels {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--muted-foreground);
}
.timeout-labels span { flex: 1; text-align: center; }

/* ── result mapping ── */
.mapping-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.mapping-key { flex: 0 0 200px; }
.mapping-arrow { color: var(--muted-foreground); }
.mapping-value { flex: 1; }

/* ── footer ── */
.editor-footer {
  display: flex;
  justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  background: var(--card);
}

/* ── run dialog ── */
.run-result { margin-top: 16px; }
.result-json {
  margin-top: 8px;
  padding: 12px;
  background: var(--muted, #f5f5f5);
  border-radius: 4px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow-x: auto;
  max-height: 300px;
  overflow-y: auto;
}

/* ── utility ── */
.ml-1 { margin-left: 4px; }
.mt-2 { margin-top: 8px; }
.text-muted { color: var(--muted-foreground); }
.text-danger { color: var(--destructive, #f56c6c); }
</style>
