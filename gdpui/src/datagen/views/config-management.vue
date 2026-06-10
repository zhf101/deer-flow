<template>
  <div class="config-management">
    <div class="page-header">
      <h1>配置管理</h1>
      <p>管理环境、系统、服务端点、数据源和标识引用配置</p>
    </div>

    <el-tabs v-model="activeTab" class="config-tabs">
      <!-- ── 环境 ── -->
      <el-tab-pane label="环境" name="environments">
        <div class="tab-header">
          <el-button type="primary" size="small" @click="openEnvDialog(null)">
            <font-awesome-icon icon="plus" /> 新增环境
          </el-button>
        </div>
        <el-table v-loading="envLoading" :data="environments" empty-text="暂无环境配置" size="small">
          <el-table-column prop="envCode" label="编码" width="160" />
          <el-table-column prop="envName" label="名称" min-width="200" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" size="mini">
                {{ row.status === 'ENABLED' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="200" show-overflow-tooltip />
          <el-table-column label="操作" width="120" align="right">
            <template #default="{ row }">
              <el-button type="text" size="mini" @click="openEnvDialog(row)">编辑</el-button>
              <el-button type="text" size="mini" class="danger-text" @click="confirmDeleteEnv(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ── 系统 ── -->
      <el-tab-pane label="系统" name="systems">
        <div class="tab-header">
          <el-button type="primary" size="small" @click="openSysDialog(null)">
            <font-awesome-icon icon="plus" /> 新增系统
          </el-button>
        </div>
        <el-table v-loading="sysLoading" :data="systems" empty-text="暂无系统配置" size="small">
          <el-table-column prop="sysCode" label="编码" width="160" />
          <el-table-column prop="sysName" label="名称" min-width="200" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" size="mini">
                {{ row.status === 'ENABLED' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="200" show-overflow-tooltip />
          <el-table-column label="操作" width="120" align="right">
            <template #default="{ row }">
              <el-button type="text" size="mini" @click="openSysDialog(row)">编辑</el-button>
              <el-button type="text" size="mini" class="danger-text" @click="confirmDeleteSys(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ── 服务端点 ── -->
      <el-tab-pane label="服务端点" name="endpoints">
        <div class="tab-header">
          <el-button type="primary" size="small" @click="openEpDialog(null)">
            <font-awesome-icon icon="plus" /> 新增端点
          </el-button>
        </div>
        <el-table v-loading="epLoading" :data="endpoints" empty-text="暂无服务端点" size="small">
          <el-table-column prop="envCode" label="环境" width="120" />
          <el-table-column prop="sysCode" label="系统" width="120" />
          <el-table-column prop="baseUrl" label="Base URL" min-width="300" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" size="mini">
                {{ row.status === 'ENABLED' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="right">
            <template #default="{ row }">
              <el-button type="text" size="mini" @click="openEpDialog(row)">编辑</el-button>
              <el-button type="text" size="mini" class="danger-text" @click="confirmDeleteEp(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ── 数据源 ── -->
      <el-tab-pane label="数据源" name="datasources">
        <div class="tab-header">
          <el-button type="primary" size="small" @click="openDsDialog(null)">
            <font-awesome-icon icon="plus" /> 新增数据源
          </el-button>
        </div>
        <el-table v-loading="dsLoading" :data="datasources" empty-text="暂无数据源配置" size="small">
          <el-table-column prop="envCode" label="环境" width="100" />
          <el-table-column prop="sysCode" label="系统" width="100" />
          <el-table-column prop="datasourceCode" label="编码" width="140" />
          <el-table-column prop="datasourceName" label="名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="dbType" label="类型" width="100" />
          <el-table-column label="连接信息" min-width="240">
            <template #default="{ row }">
              <span class="mono-text">{{ row.host }}:{{ row.port }}/{{ row.databaseName }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" size="mini">
                {{ row.status === 'ENABLED' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="right">
            <template #default="{ row }">
              <el-button type="text" size="mini" @click="openDsDialog(row)">编辑</el-button>
              <el-button type="text" size="mini" class="danger-text" @click="confirmDeleteDs(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ── 标识引用 ── -->
      <el-tab-pane label="标识引用" name="identifiers">
        <div class="tab-header">
          <el-button type="primary" size="small" @click="openIdRefDialog(null)">
            <font-awesome-icon icon="plus" /> 新增标识引用
          </el-button>
        </div>
        <el-table v-loading="idRefLoading" :data="identifierRefs" empty-text="暂无标识引用" size="small">
          <el-table-column prop="refCode" label="编码" width="160" />
          <el-table-column prop="refName" label="名称" min-width="160" />
          <el-table-column prop="refType" label="类型" width="100">
            <template #default="{ row }">
              <el-tag size="mini" type="info">{{ row.refType }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="syntax" label="语法" min-width="200" show-overflow-tooltip />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" size="mini">
                {{ row.status === 'ENABLED' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" align="right">
            <template #default="{ row }">
              <el-button type="text" size="mini" @click="openIdRefDialog(row)">编辑</el-button>
              <el-button type="text" size="mini" class="danger-text" @click="confirmDeleteIdRef(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ── 环境对话框 ── -->
    <el-dialog :title="envEditing ? '编辑环境' : '新增环境'" :visible.sync="envDialogVisible" width="480px">
      <el-form label-width="80px" size="small">
        <el-form-item label="编码">
          <el-input v-model="envForm.envCode" :disabled="!!envEditing" placeholder="如: DEV" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="envForm.envName" placeholder="如: 开发环境" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="envForm.status" active-value="ENABLED" inactive-value="DISABLED" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="envForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <span slot="footer">
        <el-button size="small" @click="envDialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="handleSaveEnv">确定</el-button>
      </span>
    </el-dialog>

    <!-- ── 系统对话框 ── -->
    <el-dialog :title="sysEditing ? '编辑系统' : '新增系统'" :visible.sync="sysDialogVisible" width="480px">
      <el-form label-width="80px" size="small">
        <el-form-item label="编码">
          <el-input v-model="sysForm.sysCode" :disabled="!!sysEditing" placeholder="如: ORDER_SYS" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="sysForm.sysName" placeholder="如: 订单系统" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="sysForm.status" active-value="ENABLED" inactive-value="DISABLED" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="sysForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <span slot="footer">
        <el-button size="small" @click="sysDialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="handleSaveSys">确定</el-button>
      </span>
    </el-dialog>

    <!-- ── 服务端点对话框 ── -->
    <el-dialog :title="epEditing ? '编辑服务端点' : '新增服务端点'" :visible.sync="epDialogVisible" width="520px">
      <el-form label-width="100px" size="small">
        <el-form-item label="环境">
          <el-select v-model="epForm.envCode" placeholder="选择环境" style="width: 100%">
            <el-option v-for="e in environments" :key="e.envCode" :label="e.envName" :value="e.envCode" />
          </el-select>
        </el-form-item>
        <el-form-item label="系统">
          <el-select v-model="epForm.sysCode" placeholder="选择系统" style="width: 100%">
            <el-option v-for="s in systems" :key="s.sysCode" :label="s.sysName" :value="s.sysCode" />
          </el-select>
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="epForm.baseUrl" placeholder="如: http://localhost:8080" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="epForm.status" active-value="ENABLED" inactive-value="DISABLED" />
        </el-form-item>
      </el-form>
      <span slot="footer">
        <el-button size="small" @click="epDialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="handleSaveEp">确定</el-button>
      </span>
    </el-dialog>

    <!-- ── 数据源对话框 ── -->
    <el-dialog :title="dsEditing ? '编辑数据源' : '新增数据源'" :visible.sync="dsDialogVisible" width="560px">
      <el-form label-width="100px" size="small">
        <el-form-item label="环境">
          <el-select v-model="dsForm.envCode" placeholder="选择环境" style="width: 100%">
            <el-option v-for="e in environments" :key="e.envCode" :label="e.envName" :value="e.envCode" />
          </el-select>
        </el-form-item>
        <el-form-item label="系统">
          <el-select v-model="dsForm.sysCode" placeholder="选择系统" style="width: 100%">
            <el-option v-for="s in systems" :key="s.sysCode" :label="s.sysName" :value="s.sysCode" />
          </el-select>
        </el-form-item>
        <el-form-item label="编码">
          <el-input v-model="dsForm.datasourceCode" :disabled="!!dsEditing" placeholder="如: order_db" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="dsForm.datasourceName" placeholder="如: 订单数据库" />
        </el-form-item>
        <el-form-item label="数据库类型">
          <el-select v-model="dsForm.dbType" placeholder="选择类型" style="width: 100%">
            <el-option label="MySQL" value="MySQL" />
            <el-option label="PostgreSQL" value="PostgreSQL" />
            <el-option label="Oracle" value="Oracle" />
            <el-option label="SQLServer" value="SQLServer" />
          </el-select>
        </el-form-item>
        <div class="form-row">
          <el-form-item label="主机" class="flex-1">
            <el-input v-model="dsForm.host" placeholder="localhost" />
          </el-form-item>
          <el-form-item label="端口" class="port-field">
            <el-input v-model.number="dsForm.port" type="number" placeholder="3306" />
          </el-form-item>
        </div>
        <el-form-item label="数据库名">
          <el-input v-model="dsForm.databaseName" placeholder="order_db" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="dsForm.username" placeholder="root" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="dsForm.password" type="password" show-password placeholder="密码" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="dsForm.status" active-value="ENABLED" inactive-value="DISABLED" />
        </el-form-item>
      </el-form>
      <span slot="footer">
        <el-button size="small" @click="dsDialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="handleSaveDs">确定</el-button>
      </span>
    </el-dialog>

    <!-- ── 标识引用对话框 ── -->
    <el-dialog :title="idRefEditing ? '编辑标识引用' : '新增标识引用'" :visible.sync="idRefDialogVisible" width="600px">
      <el-form label-width="100px" size="small">
        <el-form-item label="编码">
          <el-input v-model="idRefForm.refCode" :disabled="!!idRefEditing" placeholder="如: CURRENT_TIME" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="idRefForm.refName" placeholder="如: 当前时间" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="idRefForm.refType" placeholder="选择类型" style="width: 100%">
            <el-option label="TIME" value="TIME" />
            <el-option label="MATCHER" value="MATCHER" />
            <el-option label="TPN" value="TPN" />
            <el-option label="LOGIN" value="LOGIN" />
            <el-option label="BASE64" value="BASE64" />
          </el-select>
        </el-form-item>
        <el-form-item label="语法">
          <el-input v-model="idRefForm.syntax" placeholder="如: ${CURRENT_TIME}" class="mono-input" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="idRefForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="idRefForm.status" active-value="ENABLED" inactive-value="DISABLED" />
        </el-form-item>

        <!-- 参数列表 -->
        <el-divider content-position="left">参数</el-divider>
        <div v-for="(param, idx) in idRefForm.parameters" :key="'p' + idx" class="param-row">
          <el-input v-model="param.name" placeholder="参数名" size="mini" class="param-name" />
          <el-input v-model="param.description" placeholder="描述" size="mini" class="param-desc" />
          <el-checkbox v-model="param.required" size="mini">必填</el-checkbox>
          <el-button type="text" size="mini" class="danger-text" @click="idRefForm.parameters.splice(idx, 1)">
            <font-awesome-icon icon="trash" />
          </el-button>
        </div>
        <el-button size="mini" plain @click="idRefForm.parameters.push({ name: '', description: '', required: false, defaultValue: undefined })">
          <font-awesome-icon icon="plus" /> 添加参数
        </el-button>

        <!-- 示例列表 -->
        <el-divider content-position="left">示例</el-divider>
        <div v-for="(ex, idx) in idRefForm.examples" :key="'e' + idx" class="param-row">
          <el-input v-model="ex.expression" placeholder="表达式" size="mini" class="param-name" />
          <el-input v-model="ex.description" placeholder="描述" size="mini" class="param-desc" />
          <el-button type="text" size="mini" class="danger-text" @click="idRefForm.examples.splice(idx, 1)">
            <font-awesome-icon icon="trash" />
          </el-button>
        </div>
        <el-button size="mini" plain @click="idRefForm.examples.push({ expression: '', description: '' })">
          <font-awesome-icon icon="plus" /> 添加示例
        </el-button>
      </el-form>
      <span slot="footer">
        <el-button size="small" @click="idRefDialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="handleSaveIdRef">确定</el-button>
      </span>
    </el-dialog>

    <!-- ── 删除确认对话框 ── -->
    <el-dialog title="确认删除" :visible.sync="deleteDialogVisible" width="420px">
      <p class="delete-desc">{{ deleteMessage }}</p>
      <span slot="footer">
        <el-button size="small" @click="deleteDialogVisible = false">取消</el-button>
        <el-button type="danger" size="small" @click="handleDelete">确认删除</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import {
  listEnvironments,
  saveEnvironment,
  deleteEnvironment,
  listSystems,
  saveSystem,
  deleteSystem,
  listServiceEndpoints,
  createServiceEndpoint,
  updateServiceEndpoint,
  deleteServiceEndpoint,
  listDatasources,
  createDatasource,
  updateDatasource,
  deleteDatasource,
} from '@/datagen/common/lib/api'
import type {
  ConfigStatus,
  DatasourceConfig,
  DatasourceResponse,
  EnvironmentConfig,
  EnvironmentResponse,
  IdentifierReferenceConfig,
  IdentifierReferenceResponse,
  ServiceEndpointConfig,
  ServiceEndpointResponse,
  SysConfig,
  SysResponse,
} from '@/datagen/common/lib/types'

/**
 * 基础配置管理页面。
 * 包含环境、系统、服务端点、数据源、标识引用五个标签页。
 * 从 React ConfigManagement 跨框架重写为 Vue 2 + Element UI。
 */
export default Vue.extend({
  name: 'ConfigManagement',
  data() {
    return {
      activeTab: 'environments',

      /* ── 环境 ── */
      environments: [] as EnvironmentResponse[],
      envLoading: false,
      envDialogVisible: false,
      envEditing: null as EnvironmentResponse | null,
      envForm: { envCode: '', envName: '', status: 'ENABLED' as ConfigStatus, remark: '' },

      /* ── 系统 ── */
      systems: [] as SysResponse[],
      sysLoading: false,
      sysDialogVisible: false,
      sysEditing: null as SysResponse | null,
      sysForm: { sysCode: '', sysName: '', status: 'ENABLED' as ConfigStatus, remark: '' },

      /* ── 服务端点 ── */
      endpoints: [] as ServiceEndpointResponse[],
      epLoading: false,
      epDialogVisible: false,
      epEditing: null as ServiceEndpointResponse | null,
      epForm: { envCode: '', sysCode: '', baseUrl: '', status: 'ENABLED' as ConfigStatus },

      /* ── 数据源 ── */
      datasources: [] as DatasourceResponse[],
      dsLoading: false,
      dsDialogVisible: false,
      dsEditing: null as DatasourceResponse | null,
      dsForm: {
        envCode: '', sysCode: '', datasourceCode: '', datasourceName: '',
        dbType: 'MySQL', host: 'localhost', port: 3306, databaseName: '',
        username: '', password: '', status: 'ENABLED' as ConfigStatus,
      },

      /* ── 标识引用 ── */
      identifierRefs: [] as IdentifierReferenceResponse[],
      idRefLoading: false,
      idRefDialogVisible: false,
      idRefEditing: null as IdentifierReferenceResponse | null,
      idRefForm: {
        refCode: '', refName: '', refType: 'TIME' as IdentifierReferenceConfig['refType'],
        syntax: '', description: '', usageScope: [] as string[],
        parameters: [] as IdentifierReferenceConfig['parameters'],
        examples: [] as IdentifierReferenceConfig['examples'],
        status: 'ENABLED' as ConfigStatus, remark: '',
      },

      /* ── 删除 ── */
      deleteDialogVisible: false,
      deleteMessage: '',
      deleteAction: null as (() => Promise<void>) | null,
    }
  },
  created() {
    this.loadEnvironments()
    this.loadSystems()
    this.loadEndpoints()
    this.loadDatasources()
    this.loadIdentifierRefs()
  },
  methods: {
    /* ── 环境 CRUD ── */
    loadEnvironments() {
      this.envLoading = true
      listEnvironments()
        .then((r) => { this.environments = r })
        .catch(() => {})
        .finally(() => { this.envLoading = false })
    },
    openEnvDialog(item: EnvironmentResponse | null) {
      this.envEditing = item
      this.envForm = item
        ? { envCode: item.envCode, envName: item.envName, status: item.status, remark: item.remark || '' }
        : { envCode: '', envName: '', status: 'ENABLED', remark: '' }
      this.envDialogVisible = true
    },
    async handleSaveEnv() {
      try {
        await saveEnvironment(this.envForm as EnvironmentConfig)
        this.$message.success(this.envEditing ? '环境已更新' : '环境已创建')
        this.envDialogVisible = false
        this.loadEnvironments()
      } catch (e) {
        this.$message.error(e instanceof Error ? e.message : '保存失败')
      }
    },
    confirmDeleteEnv(item: EnvironmentResponse) {
      this.deleteMessage = `确定删除环境 "${item.envCode}" 吗？此操作不可撤销。`
      this.deleteAction = async () => {
        await deleteEnvironment(item.envCode)
        this.$message.success('已删除')
        this.loadEnvironments()
      }
      this.deleteDialogVisible = true
    },

    /* ── 系统 CRUD ── */
    loadSystems() {
      this.sysLoading = true
      listSystems()
        .then((r) => { this.systems = r })
        .catch(() => {})
        .finally(() => { this.sysLoading = false })
    },
    openSysDialog(item: SysResponse | null) {
      this.sysEditing = item
      this.sysForm = item
        ? { sysCode: item.sysCode, sysName: item.sysName, status: item.status, remark: item.remark || '' }
        : { sysCode: '', sysName: '', status: 'ENABLED', remark: '' }
      this.sysDialogVisible = true
    },
    async handleSaveSys() {
      try {
        await saveSystem(this.sysForm as SysConfig)
        this.$message.success(this.sysEditing ? '系统已更新' : '系统已创建')
        this.sysDialogVisible = false
        this.loadSystems()
      } catch (e) {
        this.$message.error(e instanceof Error ? e.message : '保存失败')
      }
    },
    confirmDeleteSys(item: SysResponse) {
      this.deleteMessage = `确定删除系统 "${item.sysCode}" 吗？此操作不可撤销。`
      this.deleteAction = async () => {
        await deleteSystem(item.sysCode)
        this.$message.success('已删除')
        this.loadSystems()
      }
      this.deleteDialogVisible = true
    },

    /* ── 服务端点 CRUD ── */
    loadEndpoints() {
      this.epLoading = true
      listServiceEndpoints()
        .then((r) => { this.endpoints = r })
        .catch(() => {})
        .finally(() => { this.epLoading = false })
    },
    openEpDialog(item: ServiceEndpointResponse | null) {
      this.epEditing = item
      this.epForm = item
        ? { envCode: item.envCode, sysCode: item.sysCode, baseUrl: item.baseUrl, status: item.status }
        : { envCode: '', sysCode: '', baseUrl: '', status: 'ENABLED' }
      this.epDialogVisible = true
    },
    async handleSaveEp() {
      try {
        if (this.epEditing) {
          await updateServiceEndpoint(this.epEditing.id, this.epForm as ServiceEndpointConfig)
        } else {
          await createServiceEndpoint(this.epForm as ServiceEndpointConfig)
        }
        this.$message.success(this.epEditing ? '端点已更新' : '端点已创建')
        this.epDialogVisible = false
        this.loadEndpoints()
      } catch (e) {
        this.$message.error(e instanceof Error ? e.message : '保存失败')
      }
    },
    confirmDeleteEp(item: ServiceEndpointResponse) {
      this.deleteMessage = `确定删除服务端点 "${item.envCode}/${item.sysCode}" 吗？`
      this.deleteAction = async () => {
        await deleteServiceEndpoint(item.id)
        this.$message.success('已删除')
        this.loadEndpoints()
      }
      this.deleteDialogVisible = true
    },

    /* ── 数据源 CRUD ── */
    loadDatasources() {
      this.dsLoading = true
      listDatasources()
        .then((r) => { this.datasources = r })
        .catch(() => {})
        .finally(() => { this.dsLoading = false })
    },
    openDsDialog(item: DatasourceResponse | null) {
      this.dsEditing = item
      this.dsForm = item
        ? {
            envCode: item.envCode, sysCode: item.sysCode,
            datasourceCode: item.datasourceCode, datasourceName: item.datasourceName,
            dbType: item.dbType, host: item.host, port: item.port,
            databaseName: item.databaseName, username: item.username || '',
            password: item.password || '', status: item.status,
          }
        : {
            envCode: '', sysCode: '', datasourceCode: '', datasourceName: '',
            dbType: 'MySQL', host: 'localhost', port: 3306, databaseName: '',
            username: '', password: '', status: 'ENABLED',
          }
      this.dsDialogVisible = true
    },
    async handleSaveDs() {
      try {
        const config = { ...this.dsForm } as DatasourceConfig
        if (this.dsEditing) {
          await updateDatasource(this.dsEditing.id, config)
        } else {
          await createDatasource(config)
        }
        this.$message.success(this.dsEditing ? '数据源已更新' : '数据源已创建')
        this.dsDialogVisible = false
        this.loadDatasources()
      } catch (e) {
        this.$message.error(e instanceof Error ? e.message : '保存失败')
      }
    },
    confirmDeleteDs(item: DatasourceResponse) {
      this.deleteMessage = `确定删除数据源 "${item.datasourceCode}" 吗？`
      this.deleteAction = async () => {
        await deleteDatasource(item.id)
        this.$message.success('已删除')
        this.loadDatasources()
      }
      this.deleteDialogVisible = true
    },

    /* ── 标识引用（本地管理，API 待后端就绪）── */
    loadIdentifierRefs() {
      this.idRefLoading = true
      // 标识引用 API 暂未在 api.ts 中暴露，先展示空列表
      this.identifierRefs = []
      this.idRefLoading = false
    },
    openIdRefDialog(item: IdentifierReferenceResponse | null) {
      this.idRefEditing = item
      this.idRefForm = item
        ? {
            refCode: item.refCode, refName: item.refName, refType: item.refType,
            syntax: item.syntax, description: item.description,
            usageScope: [...item.usageScope],
            parameters: item.parameters.map((p) => ({ ...p })),
            examples: item.examples.map((e) => ({ ...e })),
            status: item.status, remark: item.remark || '',
          }
        : {
            refCode: '', refName: '', refType: 'TIME',
            syntax: '', description: '', usageScope: [],
            parameters: [], examples: [],
            status: 'ENABLED', remark: '',
          }
      this.idRefDialogVisible = true
    },
    async handleSaveIdRef() {
      // 标识引用保存 API 待后端开放后接入
      this.$message.info('标识引用 API 暂未开放，保存功能待后端就绪')
      this.idRefDialogVisible = false
    },
    confirmDeleteIdRef(_item: IdentifierReferenceResponse) {
      this.deleteMessage = `确定删除标识引用 "${_item.refCode}" 吗？`
      this.deleteAction = async () => {
        // 标识引用删除 API 待后端开放后接入
        this.$message.info('标识引用 API 暂未开放')
      }
      this.deleteDialogVisible = true
    },

    /* ── 通用删除 ── */
    async handleDelete() {
      if (!this.deleteAction) return
      try {
        await this.deleteAction()
        this.deleteDialogVisible = false
      } catch (e) {
        this.$message.error(e instanceof Error ? e.message : '删除失败')
      }
    },
  },
})
</script>

<style scoped>
.config-management {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 24px;
  box-sizing: border-box;
  background: var(--background);
}

.page-header {
  margin-bottom: 20px;
}

.page-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--foreground);
}

.page-header p {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--muted-foreground);
}

.config-tabs {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.config-tabs >>> .el-tabs__content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.tab-header {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.danger-text {
  color: #ef4444 !important;
}

.delete-desc {
  font-size: 13px;
  color: var(--muted-foreground);
  margin: 0;
}

.mono-text {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.mono-input >>> input {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-row .flex-1 {
  flex: 1;
}

.form-row .port-field {
  width: 120px;
}

.param-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.param-name {
  width: 140px;
}

.param-desc {
  flex: 1;
}
</style>
