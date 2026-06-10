<template>
  <div class="run-history">
    <!-- 筛选栏 -->
    <header class="history-header">
      <div class="header-inner">
        <h1 class="header-title">执行历史</h1>
        <el-select v-model="sceneCode" placeholder="全部场景" size="small" class="filter-select" @change="onFilterChange">
          <el-option label="全部场景" value="" />
          <el-option v-for="s in scenes" :key="s.sceneCode" :label="s.sceneName + ' (' + s.sceneCode + ')'" :value="s.sceneCode" />
        </el-select>
        <el-select v-model="status" placeholder="全部状态" size="small" class="filter-select-sm" @change="onFilterChange">
          <el-option label="全部状态" value="" />
          <el-option label="成功" value="SUCCESS" />
          <el-option label="失败" value="FAILED" />
          <el-option label="部分成功" value="PARTIAL" />
        </el-select>
        <el-button size="small" :loading="loading" icon="el-icon-refresh" circle @click="reloadRuns" />
      </div>
    </header>

    <!-- 列表 -->
    <div class="history-list">
      <div v-if="runs.length === 0 && !loading" class="empty-state">
        <font-awesome-icon icon="clock" class="empty-icon" />
        <p>暂无执行记录</p>
      </div>

      <div
        v-for="run in runs"
        :key="run.runId"
        :class="['run-card', `run-card--${run.status.toLowerCase()}`]"
        @click="viewRun(run)"
      >
        <!-- 第一行 -->
        <div class="run-card__header">
          <font-awesome-icon
            :icon="statusIcon(run.status)"
            :class="['status-icon', `status-icon--${run.status.toLowerCase()}`]"
          />
          <span class="run-card__scene">{{ run.sceneCode }}</span>
          <el-tag size="mini" type="info" class="run-card__badge">v{{ run.versionNo }}</el-tag>
          <el-tag size="mini" class="run-card__badge">{{ run.envCode }}</el-tag>
          <span class="run-card__duration">
            <font-awesome-icon icon="clock" />
            {{ formatDuration(run.durationMs) }}
          </span>
          <span class="run-card__time">{{ formatDateTime(run.startedAt) }}</span>
        </div>
        <!-- 第二行 -->
        <div class="run-card__meta">
          <span>
            步骤 <strong>{{ run.successCount }}/{{ run.stepCount }}</strong>
            <span v-if="run.failedCount > 0" class="failed-count">失败 {{ run.failedCount }}</span>
          </span>
          <span v-if="hasInputs(run)" class="run-card__inputs">
            入参: {{ truncateJson(run.inputs) }}
          </span>
        </div>
        <!-- 错误信息 -->
        <div v-if="run.errors.length > 0" class="run-card__error">
          {{ run.errors[0] }}
        </div>
      </div>

      <!-- 加载更多 -->
      <div v-if="hasMore" class="load-more">
        <el-button size="small" :loading="loading" @click="loadMore">
          <font-awesome-icon v-if="!loading" icon="chevron-down" />
          加载更多
        </el-button>
      </div>

      <div v-if="loading && runs.length === 0" class="loading-state">
        <i class="el-icon-loading" />
        <span>加载中...</span>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import { listSceneRuns, listScenes } from '@/datagen/common/lib/api'
import type { SceneRunSummary, SceneSummary } from '@/datagen/common/lib/types'

/**
 * 场景执行历史列表页面。
 * 从 React SceneRunHistory 跨框架重写为 Vue 2 + Element UI。
 */
export default Vue.extend({
  name: 'SceneRunHistory',
  data() {
    return {
      runs: [] as SceneRunSummary[],
      scenes: [] as SceneSummary[],
      loading: false,
      sceneCode: '',
      status: '',
      page: 0,
      hasMore: false,
      limit: 20,
    }
  },
  created() {
    this.loadScenes()
    void this.reloadRuns()
  },
  methods: {
    loadScenes() {
      listScenes({ limit: 200, offset: 0 })
        .then((result) => { this.scenes = result })
        .catch(() => {})
    },
    async reloadRuns() {
      this.page = 0
      this.loading = true
      try {
        const result = await listSceneRuns({
          sceneCode: this.sceneCode || undefined,
          status: this.status || undefined,
          limit: this.limit,
          offset: 0,
        })
        this.runs = result
        this.hasMore = result.length === this.limit
        this.page = 1
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '加载执行记录失败')
      } finally {
        this.loading = false
      }
    },
    async loadMore() {
      this.loading = true
      try {
        const result = await listSceneRuns({
          sceneCode: this.sceneCode || undefined,
          status: this.status || undefined,
          limit: this.limit,
          offset: this.page * this.limit,
        })
        this.runs = [...this.runs, ...result]
        this.hasMore = result.length === this.limit
        this.page += 1
      } catch (error) {
        this.$message.error(error instanceof Error ? error.message : '加载更多失败')
      } finally {
        this.loading = false
      }
    },
    onFilterChange() {
      void this.reloadRuns()
    },
    viewRun(run: SceneRunSummary) {
      this.$router.push({
        path: `/datagen/scene/run/${encodeURIComponent(run.sceneCode)}`,
        query: { runId: run.runId },
      }).catch(() => {})
    },
    statusIcon(status: string): string {
      if (status === 'SUCCESS') return 'circle-check'
      if (status === 'FAILED') return 'circle-xmark'
      return 'triangle-exclamation'
    },
    hasInputs(run: SceneRunSummary): boolean {
      return Object.keys(run.inputs).length > 0
    },
    truncateJson(obj: Record<string, unknown>): string {
      const text = JSON.stringify(obj)
      return text.length > 60 ? text.slice(0, 57) + '...' : text
    },
    formatDuration(ms: number): string {
      if (!Number.isFinite(ms)) return '-'
      if (ms < 1000) return `${Math.round(ms)}ms`
      return `${(ms / 1000).toFixed(1)}s`
    },
    formatDateTime(value: string): string {
      if (!value) return '-'
      const d = new Date(value)
      return Number.isNaN(d.getTime()) ? '-' : d.toLocaleString()
    },
  },
})
</script>

<style scoped>
.run-history {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background);
}

.history-header {
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
  background: var(--card);
  padding: 10px 16px;
}

.header-inner {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-title {
  font-size: 14px;
  font-weight: 600;
  margin: 0;
  margin-right: 16px;
  color: var(--foreground);
}

.filter-select {
  width: 200px;
}

.filter-select-sm {
  width: 130px;
}

.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
  color: var(--muted-foreground);
}

.empty-icon {
  font-size: 32px;
  margin-bottom: 8px;
  opacity: 0.2;
}

.empty-state p {
  font-size: 13px;
  margin: 0;
}

.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
  color: var(--muted-foreground);
  font-size: 12px;
  gap: 8px;
}

.run-card {
  width: 100%;
  text-align: left;
  border: 1px solid var(--border);
  border-left: 4px solid var(--border);
  border-radius: 8px;
  background: var(--card);
  padding: 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s;
}

.run-card:hover {
  background: var(--accent);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.run-card--success {
  border-left-color: #10b981;
}

.run-card--failed {
  border-left-color: #ef4444;
}

.run-card--partial {
  border-left-color: #f59e0b;
}

.run-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.status-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.status-icon--success {
  color: #10b981;
}

.status-icon--failed {
  color: #ef4444;
}

.status-icon--partial {
  color: #f59e0b;
}

.run-card__scene {
  font-size: 14px;
  font-weight: 600;
  color: var(--foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-card__badge {
  flex-shrink: 0;
}

.run-card__duration {
  font-size: 11px;
  color: var(--muted-foreground);
  display: flex;
  align-items: center;
  gap: 4px;
}

.run-card__time {
  margin-left: auto;
  font-size: 10px;
  color: var(--muted-foreground);
}

.run-card__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
  font-size: 11px;
  color: var(--muted-foreground);
}

.failed-count {
  color: #ef4444;
  margin-left: 4px;
}

.run-card__inputs {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  opacity: 0.7;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}

.run-card__error {
  margin-top: 6px;
  font-size: 11px;
  color: #ef4444;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.load-more {
  display: flex;
  justify-content: center;
  padding: 8px 0 16px;
}
</style>
