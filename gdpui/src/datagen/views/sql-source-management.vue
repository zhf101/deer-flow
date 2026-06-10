<template>
  <div class="sql-source-mgmt">
    <!-- ── List View ── -->
    <template v-if="!editing">
      <div class="page-header">
        <h2>SQL 配置</h2>
        <el-button type="primary" size="small" @click="handleNew">
          <font-awesome-icon icon="plus" /> 新增 SQL
        </el-button>
      </div>

      <div class="filters-bar">
        <el-select v-model="opFilter" placeholder="操作类型" clearable size="small" @change="onFilterChange">
          <el-option label="全部类型" value="" />
          <el-option v-for="op in SQL_OPS" :key="op" :label="op" :value="op" />
        </el-select>
        <el-select v-model="sysFilter" placeholder="所属系统" clearable size="small" @change="onFilterChange">
          <el-option label="全部系统" value="" />
          <el-option v-for="sys in systems" :key="sys.sysCode" :label="sys.sysName + ' (' + sys.sysCode + ')'" :value="sys.sysCode" />
        </el-select>
        <el-input v-model="sqlFilter" placeholder="筛选 SQL 内容" clearable size="small" @input="onFilterChange">
          <font-awesome-icon slot="prefix" icon="magnifying-glass" class="search-icon" />
        </el-input>
        <el-input v-model="descFilter" placeholder="筛选描述" clearable size="small" @input="onFilterChange">
          <font-awesome-icon slot="prefix" icon="magnifying-glass" class="search-icon" />
        </el-input>
        <el-button size="small" @click="resetFilters">重置</el-button>
      </div>

      <div class="table-wrap">
        <el-table
          v-loading="loading"
          :data="pageRows"
          row-key="id"
          empty-text="没有匹配的 SQL 配置"
          size="small"
        >
          <el-table-column label="编码 / 描述" min-width="180">
            <template #default="{ row }">
              <div class="cell-name">{{ row.sourceCode }}</div>
              <div class="cell-sub">{{ row.sourceName }}</div>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="90">
            <template #default="{ row }">
              <el-tag size="mini" :type="opTagType(row.operation)">{{ row.operation }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="系统 / 数据源" width="170">
            <template #default="{ row }">
              <div>{{ systemName(row.sysCode) }}</div>
              <div class="cell-mono cell-sub">{{ row.datasourceCode || '-' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="SQL" min-width="220">
            <template #default="{ row }">
              <span class="cell-mono cell-sub" :title="row.sqlText">{{ truncate(row.sqlText, 60) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'ENABLED' ? 'success' : 'info'" size="mini">
                {{ row.status === 'ENABLED' ? '启用' : '停用' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" align="right">
            <template #default="{ row }">
              <el-button type="text" size="small" @click="handleView(row)">
                <font-awesome-icon icon="eye" />
              </el-button>
              <el-button type="text" size="small" @click="handleEdit(row)">
                <font-awesome-icon icon="pen" />
              </el-button>
              <el-dropdown trigger="click" @command="onRowCommand($event, row)">
                <el-button type="text" size="small">
                  <font-awesome-icon icon="ellipsis-vertical" />
                </el-button>
                <el-dropdown-menu slot="dropdown">
                  <el-dropdown-item command="copy">
                    <font-awesome-icon icon="copy" class="menu-icon" /> 复制
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" class="cmd-danger">
                    <font-awesome-icon icon="trash" class="menu-icon" /> 删除
                  </el-dropdown-item>
                </el-dropdown-menu>
              </el-dropdown>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="pager">
        <span class="cell-muted">共 {{ filteredSources.length }} 条</span>
        <div>
          <el-button size="mini" :disabled="page === 0" @click="page--">上一页</el-button>
          <el-button size="mini" :disabled="(page + 1) * pageSize >= filteredSources.length" @click="page++">下一页</el-button>
        </div>
      </div>
    </template>

    <!-- ── Editor View ── -->
    <template v-else>
      <div class="editor-view">
        <header class="editor-header">
          <div class="header-left">
            <el-button type="text" @click="closeEditor">
              <font-awesome-icon icon="arrow-left" /> 返回列表
            </el-button>
            <h3>{{ isNew ? '新增 SQL' : (editorMode === 'view' ? '查看 SQL' : '编辑 SQL') }}</h3>
          </div>
          <div v-if="editorMode !== 'view'" class="header-right">
            <el-button size="small" @click="closeEditor">取消</el-button>
            <el-button size="small" type="primary" :loading="saving" @click="handleSave">
              <font-awesome-icon v-if="!saving" icon="floppy-disk" /> 保存
            </el-button>
          </div>
        </header>

        <div class="editor-body">
          <el-form label-position="top" size="small" :disabled="editorMode === 'view'">
            <div class="form-grid">
              <el-form-item label="SQL 编码" required>
                <el-input v-model="editing.sourceCode" :disabled="!isNew" placeholder="唯一编码" />
              </el-form-item>
              <el-form-item label="SQL 名称" required>
                <el-input v-model="editing.sourceName" placeholder="显示名称" />
              </el-form-item>
            </div>
            <div class="form-grid">
              <el-form-item label="所属系统" required>
                <el-input v-model="editing.sysCode" placeholder="sysCode" />
              </el-form-item>
              <el-form-item label="数据源" required>
                <el-input v-model="editing.datasourceCode" placeholder="datasourceCode" />
              </el-form-item>
            </div>
            <div class="form-grid">
              <el-form-item label="操作类型">
                <el-select v-model="editing.operation">
                  <el-option v-for="op in SQL_OPS" :key="op" :label="op" :value="op" />
                </el-select>
              </el-form-item>
              <el-form-item label="状态">
                <el-select v-model="editing.status">
                  <el-option label="启用" value="ENABLED" />
                  <el-option label="停用" value="DISABLED" />
                </el-select>
              </el-form-item>
            </div>

            <el-divider content-position="left">SQL 语句</el-divider>
            <el-form-item label="SQL">
              <el-input v-model="editing.sqlText" type="textarea" :rows="8" placeholder="SELECT * FROM ..." />
            </el-form-item>
            <el-form-item v-if="!isNew && editing.normalizedSql" label="标准化 SQL">
              <pre class="normalized-sql">{{ editing.normalizedSql }}</pre>
            </el-form-item>

            <el-form-item>
              <el-button size="small" :loading="parsing" @click="parseSql">
                <font-awesome-icon v-if="!parsing" icon="wand-magic-sparkles" /> 解析 SQL
              </el-button>
            </el-form-item>

            <!-- Parse results -->
            <template v-if="parseResult">
              <el-divider content-position="left">解析结果</el-divider>

              <h4>表</h4>
              <el-table :data="parseResult.tables" border size="mini" empty-text="无">
                <el-table-column prop="tableName" label="表名" />
                <el-table-column prop="alias" label="别名" width="100" />
                <el-table-column prop="description" label="描述" />
              </el-table>

              <h4 class="mt-2">结果字段</h4>
              <el-table :data="parseResult.resultFields" border size="mini" empty-text="无">
                <el-table-column prop="fieldName" label="字段名" />
                <el-table-column prop="sourceTable" label="来源表" width="120" />
                <el-table-column prop="alias" label="别名" width="120" />
                <el-table-column prop="description" label="描述" />
              </el-table>

              <h4 class="mt-2">条件字段</h4>
              <el-table :data="parseResult.conditionFields" border size="mini" empty-text="无">
                <el-table-column prop="fieldName" label="字段名" />
                <el-table-column prop="sourceTable" label="来源表" width="120" />
                <el-table-column prop="paramName" label="参数名" width="120" />
                <el-table-column prop="description" label="描述" />
              </el-table>

              <h4 class="mt-2">参数</h4>
              <el-table :data="parseResult.parameters" border size="mini" empty-text="无">
                <el-table-column prop="name" label="参数名" width="160" />
                <el-table-column prop="type" label="类型" width="100" />
                <el-table-column label="必填" width="70" align="center">
                  <template #default="{ row }">{{ row.required ? '是' : '否' }}</template>
                </el-table-column>
                <el-table-column prop="description" label="描述" />
              </el-table>
            </template>

            <!-- Safety -->
            <el-divider content-position="left">安全策略</el-divider>
            <div class="form-grid">
              <el-form-item label="要求 WHERE 条件">
                <el-switch v-model="editing.safety.requireWhere" />
              </el-form-item>
              <el-form-item label="最大影响行数">
                <el-input-number v-model="editing.safety.maxAffectedRows" :min="0" controls-position="right" placeholder="不限" />
              </el-form-item>
            </div>
          </el-form>
        </div>

        <!-- Test bar -->
        <div class="test-bar">
          <el-button size="small" type="success" plain @click="openTestDialog">
            <font-awesome-icon icon="play" /> 测试执行
          </el-button>
        </div>
      </div>
    </template>

    <!-- ── Test Dialog ── -->
    <el-dialog title="SQL 测试执行" :visible.sync="testDialogVisible" width="700px">
      <el-form label-position="top" size="small">
        <el-form-item label="测试环境">
          <el-select v-model="testEnvCode" placeholder="选择环境">
            <el-option v-for="env in environments" :key="env.envCode" :label="env.envName" :value="env.envCode" />
          </el-select>
        </el-form-item>
        <el-form-item label="参数 (JSON)">
          <el-input v-model="testParamsJson" type="textarea" :rows="4" placeholder='{"key": "value"}' />
        </el-form-item>
      </el-form>
      <div v-if="testResult" class="test-result">
        <el-divider content-position="left">执行结果</el-divider>
        <el-tag :type="testResult.success ? 'success' : 'danger'" size="small">
          {{ testResult.success ? '成功' : '失败' }}
        </el-tag>
        <span v-if="testResult.elapsedMs != null" class="text-muted ml-1">{{ testResult.elapsedMs }}ms</span>
        <span v-if="testResult.affectedRows" class="text-muted ml-1">影响 {{ testResult.affectedRows }} 行</span>
        <pre v-if="testResult.rows && testResult.rows.length" class="result-json">{{ JSON.stringify(testResult.rows.slice(0, 20), null, 2) }}</pre>
        <pre v-if="testResult.error" class="result-json error">{{ testResult.error.message }}</pre>
      </div>
      <span slot="footer">
        <el-button @click="testDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="testing" :disabled="!testEnvCode" @click="runTest">执行测试</el-button>
      </span>
    </el-dialog>

    <!-- ── Delete Dialog ── -->
    <el-dialog title="确认删除" :visible.sync="deleteDialogVisible" width="440px">
      <p>确定删除 SQL 配置 "{{ deleteTarget }}" 吗？此操作不可撤销。</p>
      <span slot="footer">
        <el-button @click="deleteDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmDelete">确认删除</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import {
  createSqlSource,
  deleteSqlSource,
  executeSql,
  listDatasources,
  listEnvironments,
  listSqlSources,
  listSystems,
  parseSqlSource,
  updateSqlSource,
} from '@/datagen/common/lib/api'
import { createDefaultSqlSource, SQL_OPERATIONS } from '@/datagen/common/lib/defaults'
import type {
  DatasourceResponse,
  EnvironmentResponse,
  SqlExecutionResult,
  SqlOperation,
  SqlSourceConfig,
  SqlSourceParseResponse,
  SqlSourceResponse,
  SysResponse,
} from '@/datagen/common/lib/types'

const SQL_OPS = SQL_OPERATIONS

export default Vue.extend({
  name: 'SqlSourceManagement',

  data() {
    return {
      SQL_OPS,
      sources: [] as SqlSourceResponse[],
      systems: [] as SysResponse[],
      datasources: [] as DatasourceResponse[],
      environments: [] as EnvironmentResponse[],
      loading: true,
      // filters
      opFilter: '' as SqlOperation | '',
      sysFilter: '',
      sqlFilter: '',
      descFilter: '',
      page: 0,
      pageSize: 20,
      // editor
      editing: null as SqlSourceConfig | null,
      editorMode: null as 'edit' | 'view' | null,
      saving: false,
      // parse
      parsing: false,
      parseResult: null as SqlSourceParseResponse | null,
      // test
      testDialogVisible: false,
      testEnvCode: '',
      testParamsJson: '{}',
      testing: false,
      testResult: null as SqlExecutionResult | null,
      // delete
      deleteDialogVisible: false,
      deleteTarget: null as string | null,
    }
  },

  computed: {
    isNew(): boolean {
      if (!this.editing) return true
      return !this.sources.some(s => s.sourceCode === this.editing!.sourceCode)
    },

    filteredSources(): SqlSourceResponse[] {
      const sqlKw = this.sqlFilter.trim().toLowerCase()
      const descKw = this.descFilter.trim().toLowerCase()
      return this.sources.filter(s => {
        if (this.opFilter && s.operation !== this.opFilter) return false
        if (this.sysFilter && s.sysCode !== this.sysFilter) return false
        if (sqlKw && !s.sqlText.toLowerCase().includes(sqlKw)) return false
        if (descKw && !s.sourceName.toLowerCase().includes(descKw)) return false
        return true
      })
    },

    pageRows(): SqlSourceResponse[] {
      const start = this.page * this.pageSize
      return this.filteredSources.slice(start, start + this.pageSize)
    },
  },

  created() {
    void this.reload()
  },

  methods: {
    async reload() {
      this.loading = true
      try {
        const [s, sys, d, envs] = await Promise.all([
          listSqlSources(),
          listSystems(),
          listDatasources(),
          listEnvironments(),
        ])
        this.sources = s
        this.systems = sys
        this.datasources = d
        this.environments = envs.filter(e => e.status === 'ENABLED')
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '加载失败')
      } finally {
        this.loading = false
      }
    },

    onFilterChange() { this.page = 0 },
    resetFilters() {
      this.opFilter = ''
      this.sysFilter = ''
      this.sqlFilter = ''
      this.descFilter = ''
      this.page = 0
    },

    systemName(code: string): string {
      return this.systems.find(s => s.sysCode === code)?.sysName || code || '-'
    },

    truncate(str: string, len: number): string {
      return str.length > len ? str.slice(0, len) + '...' : str
    },

    opTagType(op: SqlOperation): string {
      if (op === 'SELECT') return ''
      if (op === 'INSERT') return 'success'
      if (op === 'UPDATE') return 'warning'
      if (op === 'DELETE') return 'danger'
      return 'info'
    },

    // ── Editor ──
    handleNew() {
      this.openEditor(createDefaultSqlSource(), 'edit')
    },
    handleView(row: SqlSourceResponse) {
      this.openEditor({ ...row }, 'view')
    },
    handleEdit(row: SqlSourceResponse) {
      this.openEditor({ ...row }, 'edit')
    },
    handleCopy(row: SqlSourceResponse) {
      const existingCodes = this.sources.map(s => s.sourceCode)
      this.openEditor({
        ...row,
        sourceCode: this.nextCopyCode(row.sourceCode, existingCodes),
        sourceName: `${row.sourceName} 副本`,
        status: 'ENABLED',
      }, 'edit')
    },

    openEditor(config: SqlSourceConfig, mode: 'edit' | 'view') {
      this.editing = config
      this.editorMode = mode
      this.parseResult = null
    },

    closeEditor() {
      this.editing = null
      this.editorMode = null
      this.parseResult = null
    },

    async handleSave() {
      if (!this.editing) return
      this.saving = true
      try {
        if (this.isNew) {
          await createSqlSource(this.editing)
          this.$message.success('SQL 配置已创建')
        } else {
          await updateSqlSource(this.editing.sourceCode, this.editing)
          this.$message.success('SQL 配置已保存')
        }
        this.closeEditor()
        await this.reload()
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '保存失败')
      } finally {
        this.saving = false
      }
    },

    // ── Parse ──
    async parseSql() {
      if (!this.editing?.sqlText) {
        this.$message.warning('请先输入 SQL 语句')
        return
      }
      this.parsing = true
      try {
        const result = await parseSqlSource(this.editing.sqlText, this.editing.parameters)
        this.parseResult = result
        // apply parse results back to editing
        if (this.editing) {
          this.editing.operation = result.operation
          this.editing.normalizedSql = result.normalizedSql
          this.editing.tables = result.tables
          this.editing.resultFields = result.resultFields
          this.editing.conditionFields = result.conditionFields
          this.editing.parameters = result.parameters
        }
        this.$message.success('SQL 解析成功')
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '解析失败')
      } finally {
        this.parsing = false
      }
    },

    // ── Delete ──
    onRowCommand(cmd: string, row: SqlSourceResponse) {
      if (cmd === 'copy') this.handleCopy(row)
      else if (cmd === 'delete') {
        this.deleteTarget = row.sourceCode
        this.deleteDialogVisible = true
      }
    },
    async confirmDelete() {
      if (!this.deleteTarget) return
      try {
        await deleteSqlSource(this.deleteTarget)
        this.$message.success('已删除')
        this.deleteDialogVisible = false
        this.deleteTarget = null
        await this.reload()
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '删除失败')
      }
    },

    // ── Test ──
    openTestDialog() {
      this.testDialogVisible = true
      this.testEnvCode = ''
      this.testParamsJson = '{}'
      this.testResult = null
    },
    async runTest() {
      if (!this.editing || !this.testEnvCode) return
      this.testing = true
      this.testResult = null
      try {
        const params = JSON.parse(this.testParamsJson || '{}')
        this.testResult = await executeSql(this.testEnvCode, this.editing, params)
        if (this.testResult.success) {
          this.$message.success('执行成功')
        } else {
          this.$message.warning('执行失败')
        }
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '执行失败')
      } finally {
        this.testing = false
      }
    },

    // ── Helpers ──
    nextCopyCode(code: string, existing: string[]): string {
      let i = 1
      let candidate = `${code}_copy`
      while (existing.includes(candidate)) {
        i++
        candidate = `${code}_copy${i}`
      }
      return candidate
    },
  },
})
</script>

<style scoped>
.sql-source-mgmt {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
}
.page-header h2 { margin: 0; font-size: 16px; font-weight: 600; }

.filters-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: var(--muted, #f5f5f5);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}
.filters-bar .el-select { width: 150px; }
.filters-bar .el-input { width: 180px; }

.search-icon {
  color: var(--muted-foreground);
  line-height: 32px;
}

.table-wrap {
  flex: 1;
  overflow: auto;
  padding: 0 20px;
}

.cell-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  font-weight: 500;
}
.cell-sub {
  font-size: 11px;
  color: var(--muted-foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}
.cell-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: var(--muted-foreground);
}
.cell-muted { color: var(--muted-foreground); font-size: 12px; }

.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}

/* ── Editor ── */
.editor-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
}
.header-left { display: flex; align-items: center; gap: 12px; }
.header-left h3 { margin: 0; font-size: 15px; font-weight: 600; }
.header-right { display: flex; gap: 8px; }

.editor-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}

.normalized-sql {
  padding: 12px;
  background: var(--muted, #f5f5f5);
  border-radius: 4px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow-x: auto;
  margin: 0;
}

.test-bar {
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}

/* ── Test result ── */
.test-result { margin-top: 16px; }
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
.result-json.error { color: var(--destructive, #f56c6c); }

.menu-icon { margin-right: 6px; }
.cmd-danger { color: var(--destructive, #f56c6c); }
.mt-2 { margin-top: 8px; }
.ml-1 { margin-left: 4px; }
.text-muted { color: var(--muted-foreground); }
</style>
