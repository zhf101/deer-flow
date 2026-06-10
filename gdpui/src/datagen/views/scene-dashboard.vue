<template>
  <div class="scene-dashboard">
    <!-- ── 页头 ── -->
    <div class="dash-header">
      <div>
        <h1>造数编排</h1>
        <p>管理和编排您的业务造数场景</p>
      </div>
      <div class="header-actions">
        <el-button
          plain
          :loading="generatingDemo"
          class="demo-btn"
          @click="handleGenerateDemo"
        >
          <font-awesome-icon v-if="!generatingDemo" icon="wand-magic-sparkles" />
          生成演示配置 (Demo)
        </el-button>
        <el-button type="primary" @click="openNewScene">
          <font-awesome-icon icon="file-circle-plus" />
          新增场景
        </el-button>
      </div>
    </div>

    <!-- ── 筛选栏 ── -->
    <div class="dash-filters">
      <el-input
        v-model="keyword"
        placeholder="搜索场景名称或编码"
        clearable
        class="search-input"
        @input="onKeywordInput"
        @keyup.enter.native="loadScenes"
      >
        <font-awesome-icon slot="prefix" icon="magnifying-glass" class="search-icon" />
      </el-input>

      <el-select
        v-model="status"
        placeholder="所有状态"
        class="status-select"
        @change="onStatusChange"
      >
        <el-option label="所有状态" value="" />
        <el-option label="草稿" value="DRAFT" />
        <el-option label="已发布" value="PUBLISHED" />
        <el-option label="已停用" value="DISABLED" />
      </el-select>

      <el-button :loading="loading" @click="loadScenes">
        <font-awesome-icon v-if="!loading" icon="rotate-right" />
        刷新
      </el-button>
    </div>

    <!-- ── 列表 ── -->
    <div class="dash-table">
      <el-table
        v-loading="loading"
        :data="scenes"
        row-key="id"
        empty-text="未找到匹配的场景"
        height="100%"
        @row-click="openSceneView($event.sceneCode)"
      >
        <el-table-column label="场景名称" min-width="200">
          <template #default="{ row }">
            <div class="cell-name">{{ row.sceneName }}</div>
            <div class="cell-code">{{ row.sceneCode }}</div>
          </template>
        </el-table-column>

        <el-table-column label="业务分类" min-width="120">
          <template #default="{ row }">{{ row.sceneType || '-' }}</template>
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

        <el-table-column label="发布版本" width="100">
          <template #default="{ row }">
            {{ row.publishedVersionNo ? 'v' + row.publishedVersionNo : '-' }}
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
              <el-tooltip
                :content="row.status === 'PUBLISHED' ? '测试执行' : '仅已发布场景可执行'"
                placement="top"
              >
                <el-button
                  type="text"
                  :disabled="row.status !== 'PUBLISHED'"
                  @click.stop="openSceneRun(row.sceneCode)"
                >
                  <font-awesome-icon icon="play" />
                </el-button>
              </el-tooltip>

              <el-tooltip content="查看详情" placement="top">
                <el-button type="text" @click.stop="openSceneView(row.sceneCode)">
                  <font-awesome-icon icon="eye" />
                </el-button>
              </el-tooltip>

              <el-tooltip content="编辑" placement="top">
                <el-button type="text" @click.stop="openSceneEdit(row.sceneCode)">
                  <font-awesome-icon icon="pen" />
                </el-button>
              </el-tooltip>

              <el-dropdown trigger="click" @command="onCommand($event, row)">
                <el-button type="text" @click.stop>
                  <font-awesome-icon icon="ellipsis-vertical" />
                </el-button>
                <el-dropdown-menu slot="dropdown">
                  <el-dropdown-item command="copy">
                    <font-awesome-icon icon="copy" class="menu-cmd-icon" />
                    复制场景
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" class="cmd-danger">
                    <font-awesome-icon icon="trash" class="menu-cmd-icon" />
                    删除场景
                  </el-dropdown-item>
                </el-dropdown-menu>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ── 分页 ── -->
    <div class="dash-pager">
      <span class="cell-muted">第 {{ page + 1 }} 页</span>
      <div>
        <el-button size="small" :disabled="page === 0 || loading" @click="prevPage">
          上一页
        </el-button>
        <el-button
          size="small"
          :disabled="scenes.length < limit || loading"
          @click="nextPage"
        >
          下一页
        </el-button>
      </div>
    </div>

    <!-- ── 复制对话框 ── -->
    <el-dialog title="复制场景" :visible.sync="copyDialogVisible" width="440px">
      <p class="dialog-desc">请输入新场景的唯一编码。</p>
      <label class="dialog-label">新场景编码</label>
      <el-input v-model="newSceneCode" placeholder="e.g. create_order_v2" class="mt-2" />
      <span slot="footer">
        <el-button @click="copyDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!newSceneCode" @click="handleCopy">
          确定复制
        </el-button>
      </span>
    </el-dialog>

    <!-- ── 删除对话框 ── -->
    <el-dialog title="确认删除" :visible.sync="deleteDialogVisible" width="440px">
      <p class="dialog-desc">
        您确定要删除场景 “{{ deletingScene && deletingScene.sceneName }}” 吗？
        此操作不可撤销，且会删除所有相关版本。
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

import { createScene, copyScene, deleteScene, listScenes } from '@/datagen/common/lib/api'
import { buildDemoSceneDefinition } from '@/datagen/common/lib/demo-scene-fixture'
import type { SceneStatus, SceneSummary } from '@/datagen/common/lib/types'

/**
 * 造数场景列表（vertical slice）。
 *
 * Ported from the React `SceneDashboard`. The React callbacks (onEdit/onView/
 * onRun/onCreate) become route navigations to the dynamic detail tabs, so each
 * action opens its own keep-alive'd tab in the shell. Search is debounced to
 * mirror the source's per-keystroke reload without hammering the API.
 */
export default Vue.extend({
  name: 'SceneDashboard',
  data() {
    return {
      scenes: [] as SceneSummary[],
      loading: false,
      keyword: '',
      status: '' as SceneStatus | '',
      page: 0,
      limit: 20,
      generatingDemo: false,
      // copy dialog
      copyDialogVisible: false,
      copyingScene: null as SceneSummary | null,
      newSceneCode: '',
      // delete dialog
      deleteDialogVisible: false,
      deletingScene: null as SceneSummary | null,
      // debounce handle
      searchTimer: undefined as ReturnType<typeof setTimeout> | undefined,
    }
  },
  created() {
    void this.loadScenes()
  },
  beforeDestroy() {
    if (this.searchTimer) clearTimeout(this.searchTimer)
  },
  methods: {
    async loadScenes() {
      this.loading = true
      try {
        this.scenes = await listScenes({
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
      this.searchTimer = setTimeout(() => void this.loadScenes(), 300)
    },
    onStatusChange() {
      this.page = 0
      void this.loadScenes()
    },
    prevPage() {
      if (this.page === 0) return
      this.page -= 1
      void this.loadScenes()
    },
    nextPage() {
      if (this.scenes.length < this.limit) return
      this.page += 1
      void this.loadScenes()
    },

    async handleGenerateDemo() {
      this.generatingDemo = true
      try {
        await createScene(buildDemoSceneDefinition())
        this.$message.success('演示场景生成成功！')
        void this.loadScenes()
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '演示场景生成失败')
      } finally {
        this.generatingDemo = false
      }
    },

    onCommand(cmd: string, scene: SceneSummary) {
      if (cmd === 'copy') {
        this.copyingScene = scene
        this.newSceneCode = `${scene.sceneCode}_copy`
        this.copyDialogVisible = true
      } else if (cmd === 'delete') {
        this.deletingScene = scene
        this.deleteDialogVisible = true
      }
    },

    async handleCopy() {
      if (!this.copyingScene || !this.newSceneCode) return
      try {
        await copyScene(this.copyingScene.sceneCode, this.newSceneCode)
        this.$message.success('场景已复制')
        this.copyDialogVisible = false
        this.newSceneCode = ''
        void this.loadScenes()
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '复制失败')
      }
    },

    async handleDelete() {
      if (!this.deletingScene) return
      try {
        await deleteScene(this.deletingScene.sceneCode)
        this.$message.success('场景已删除')
        this.deleteDialogVisible = false
        void this.loadScenes()
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '删除失败')
      }
    },

    /* ── navigation → detail tabs ── */
    openNewScene() {
      this.$router.push('/datagen/scene/new').catch(() => {})
    },
    openSceneEdit(code: string) {
      this.$router.push(`/datagen/scene/edit/${encodeURIComponent(code)}`).catch(() => {})
    },
    openSceneView(code: string) {
      this.$router.push(`/datagen/scene/view/${encodeURIComponent(code)}`).catch(() => {})
    },
    openSceneRun(code: string) {
      this.$router.push(`/datagen/scene/run/${encodeURIComponent(code)}`).catch(() => {})
    },

    /* ── presentation helpers ── */
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
.scene-dashboard {
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
  letter-spacing: -0.01em;
  color: var(--foreground);
}

.dash-header p {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--muted-foreground);
}

.header-actions {
  display: flex;
  gap: 12px;
}

.demo-btn {
  color: var(--primary);
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

.cell-muted {
  color: var(--muted-foreground);
}

.row-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
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

.dialog-label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 500;
  color: var(--foreground);
}

.mt-2 {
  margin-top: 8px;
}

/* Make table rows feel clickable, matching the React hover affordance. */
.dash-table >>> .el-table__row {
  cursor: pointer;
}
</style>
