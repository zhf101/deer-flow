<template>
  <div class="task-dashboard">
    <!-- 页头 -->
    <div class="dash-header">
      <div>
        <h1>造数任务</h1>
        <p>编排多个造数场景，组成复杂的造数任务</p>
      </div>
      <el-button type="primary" @click="openNewTask">
        <font-awesome-icon icon="file-circle-plus" />
        新增任务
      </el-button>
    </div>

    <!-- 筛选栏 -->
    <div class="dash-filters">
      <el-input
        v-model="keyword"
        placeholder="搜索任务名称或编码"
        clearable
        class="search-input"
        @input="onKeywordInput"
        @keyup.enter.native="loadTasks"
      >
        <font-awesome-icon slot="prefix" icon="magnifying-glass" class="search-icon" />
      </el-input>

      <el-select v-model="status" placeholder="所有状态" class="status-select" @change="onStatusChange">
        <el-option label="所有状态" value="" />
        <el-option label="草稿" value="DRAFT" />
        <el-option label="已发布" value="PUBLISHED" />
        <el-option label="已停用" value="DISABLED" />
      </el-select>

      <el-button :loading="loading" @click="loadTasks">
        <font-awesome-icon v-if="!loading" icon="rotate-right" />
        刷新
      </el-button>
    </div>

    <!-- 列表 -->
    <div class="dash-table">
      <el-table
        v-loading="loading"
        :data="tasks"
        row-key="id"
        empty-text="未找到匹配的任务"
        height="100%"
        @row-click="openTaskView($event.taskCode)"
      >
        <el-table-column label="任务名称" min-width="200">
          <template #default="{ row }">
            <div class="cell-name">{{ row.taskName }}</div>
            <div class="cell-code">{{ row.taskCode }}</div>
            <div v-if="row.taskRemark" class="cell-remark">{{ row.taskRemark }}</div>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small" disable-transitions>
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="当前版本" width="100">
          <template #default="{ row }">
            {{ row.currentVersionNo ? 'v' + row.currentVersionNo : '-' }}
          </template>
        </el-table-column>

        <el-table-column label="最后更新" min-width="170">
          <template #default="{ row }">
            <span class="cell-muted">{{ formatDate(row.updatedAt) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="160" align="right">
          <template #default="{ row }">
            <div class="row-actions" @click.stop>
              <el-tooltip content="查看详情" placement="top">
                <el-button type="text" @click.stop="openTaskView(row.taskCode)">
                  <font-awesome-icon icon="eye" />
                </el-button>
              </el-tooltip>

              <el-tooltip content="编辑" placement="top">
                <el-button type="text" @click.stop="openTaskEdit(row.taskCode)">
                  <font-awesome-icon icon="pen" />
                </el-button>
              </el-tooltip>

              <el-tooltip
                v-if="row.status === 'PUBLISHED'"
                content="执行"
                placement="top"
              >
                <el-button type="text" @click.stop="openTaskRun(row.taskCode)">
                  <font-awesome-icon icon="play" class="play-icon" />
                </el-button>
              </el-tooltip>

              <el-dropdown trigger="click" @command="onCommand($event, row)">
                <el-button type="text" @click.stop>
                  <font-awesome-icon icon="ellipsis-vertical" />
                </el-button>
                <el-dropdown-menu slot="dropdown">
                  <el-dropdown-item command="delete" class="cmd-danger">
                    <font-awesome-icon icon="trash" class="menu-cmd-icon" />
                    删除任务
                  </el-dropdown-item>
                </el-dropdown-menu>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 分页 -->
    <div class="dash-pager">
      <span class="cell-muted">第 {{ page + 1 }} 页</span>
      <div>
        <el-button size="small" :disabled="page === 0 || loading" @click="prevPage">
          上一页
        </el-button>
        <el-button size="small" :disabled="tasks.length < limit || loading" @click="nextPage">
          下一页
        </el-button>
      </div>
    </div>

    <!-- 删除对话框 -->
    <el-dialog title="确认删除" :visible.sync="deleteDialogVisible" width="440px">
      <p class="dialog-desc">
        您确定要删除任务 "{{ deletingTask && deletingTask.taskName }}" 吗？此操作不可撤销。
      </p>
      <span slot="footer">
        <el-button @click="deleteDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="handleDelete">确认删除</el-button>
      </span>
    </el-dialog>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import { deleteTask, listTasks } from '@/datagen/common/lib/api'
import type { SceneStatus, TaskSummary } from '@/datagen/common/lib/types'

/**
 * 造数任务列表页面。
 * 从 React TaskDashboard 跨框架重写为 Vue 2 + Element UI。
 */
export default Vue.extend({
  name: 'TaskDashboard',
  data() {
    return {
      tasks: [] as TaskSummary[],
      loading: false,
      keyword: '',
      status: '' as SceneStatus | '',
      page: 0,
      limit: 20,
      deleteDialogVisible: false,
      deletingTask: null as TaskSummary | null,
      searchTimer: undefined as ReturnType<typeof setTimeout> | undefined,
    }
  },
  created() {
    void this.loadTasks()
  },
  beforeDestroy() {
    if (this.searchTimer) clearTimeout(this.searchTimer)
  },
  methods: {
    async loadTasks() {
      this.loading = true
      try {
        this.tasks = await listTasks({
          keyword: this.keyword,
          status: this.status,
          limit: this.limit,
          offset: this.page * this.limit,
        })
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '加载失败')
      } finally {
        this.loading = false
      }
    },
    onKeywordInput() {
      this.page = 0
      if (this.searchTimer) clearTimeout(this.searchTimer)
      this.searchTimer = setTimeout(() => void this.loadTasks(), 300)
    },
    onStatusChange() {
      this.page = 0
      void this.loadTasks()
    },
    prevPage() {
      if (this.page === 0) return
      this.page -= 1
      void this.loadTasks()
    },
    nextPage() {
      if (this.tasks.length < this.limit) return
      this.page += 1
      void this.loadTasks()
    },
    onCommand(cmd: string, task: TaskSummary) {
      if (cmd === 'delete') {
        this.deletingTask = task
        this.deleteDialogVisible = true
      }
    },
    async handleDelete() {
      if (!this.deletingTask) return
      try {
        await deleteTask(this.deletingTask.taskCode)
        this.$message.success('任务已删除')
        this.deleteDialogVisible = false
        void this.loadTasks()
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '删除失败')
      }
    },

    /* 导航到详情标签 */
    openNewTask() {
      this.$router.push('/datagen/task/new').catch(() => {})
    },
    openTaskEdit(code: string) {
      this.$router.push(`/datagen/task/edit/${encodeURIComponent(code)}`).catch(() => {})
    },
    openTaskView(code: string) {
      this.$router.push(`/datagen/task/view/${encodeURIComponent(code)}`).catch(() => {})
    },
    openTaskRun(code: string) {
      this.$router.push(`/datagen/task/run/${encodeURIComponent(code)}`).catch(() => {})
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
    formatDate(value: string): string {
      if (!value) return '-'
      const d = new Date(value)
      return Number.isNaN(d.getTime()) ? value : d.toLocaleString()
    },
  },
})
</script>

<style scoped>
.task-dashboard {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 24px;
  box-sizing: border-box;
  background-color: var(--background);
}

.dash-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.dash-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--foreground);
}

.dash-header p {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--muted-foreground);
}

.dash-filters {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}

.search-input {
  max-width: 360px;
}

.search-icon {
  color: var(--muted-foreground);
  line-height: 40px;
}

.status-select {
  width: 180px;
}

.dash-table {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  background-color: var(--card);
}

.cell-name {
  font-weight: 500;
  color: var(--foreground);
}

.cell-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: var(--muted-foreground);
}

.cell-remark {
  font-size: 12px;
  color: var(--muted-foreground);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}

.cell-muted {
  color: var(--muted-foreground);
}

.row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}

.play-icon {
  color: #16a34a;
}

.menu-cmd-icon {
  margin-right: 8px;
}

.cmd-danger {
  color: var(--destructive);
}

.dash-pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 16px;
}

.dialog-desc {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--muted-foreground);
}

.dash-table >>> .el-table__row {
  cursor: pointer;
}
</style>
