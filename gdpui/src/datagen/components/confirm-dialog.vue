<template>
  <el-dialog
    :visible="open"
    :width="'400px'"
    :show-close="false"
    append-to-body
    custom-class="confirm-dialog"
    @update:visible="$emit('update:open', $event)"
  >
    <div class="confirm-body">
      <div class="confirm-icon" :class="variant">
        <font-awesome-icon icon="triangle-exclamation" />
      </div>
      <div class="confirm-text">
        <h3 class="confirm-title">{{ title }}</h3>
        <p class="confirm-desc">{{ description }}</p>
      </div>
    </div>
    <span slot="footer">
      <el-button size="small" :disabled="loading" @click="close">
        {{ cancelText }}
      </el-button>
      <el-button
        size="small"
        :type="variant === 'warning' ? 'warning' : 'danger'"
        :loading="loading"
        @click="confirm"
      >
        {{ confirmText }}
      </el-button>
    </span>
  </el-dialog>
</template>

<script lang="ts">
import Vue from 'vue'

/**
 * Confirmation modal ported from the React `ConfirmDialog`.
 *
 * Keeps the source's open/onOpenChange/onConfirm contract via the `open` prop
 * (with `update:open` for `.sync`) and a `confirm` event. The React component
 * auto-closed after confirming, so this mirrors that by emitting both.
 */
export default Vue.extend({
  name: 'ConfirmDialog',
  props: {
    open: { type: Boolean, default: false },
    title: { type: String, default: '确认删除' },
    description: { type: String, default: '此操作不可撤销，确定要继续吗？' },
    confirmText: { type: String, default: '删除' },
    cancelText: { type: String, default: '取消' },
    variant: { type: String, default: 'danger' }, // 'danger' | 'warning'
    loading: { type: Boolean, default: false },
  },
  methods: {
    close() {
      this.$emit('update:open', false)
    },
    confirm() {
      this.$emit('confirm')
      this.$emit('update:open', false)
    },
  },
})
</script>

<style scoped>
.confirm-body {
  display: flex;
  align-items: flex-start;
  gap: 16px;
}

.confirm-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  flex-shrink: 0;
  font-size: 18px;
}

.confirm-icon.danger {
  background-color: rgba(239, 68, 68, 0.12);
  color: #dc2626;
}

.confirm-icon.warning {
  background-color: rgba(245, 158, 11, 0.12);
  color: #d97706;
}

.confirm-text {
  flex: 1;
  padding-top: 2px;
}

.confirm-title {
  margin: 0 0 6px;
  font-size: 16px;
  font-weight: 600;
  color: var(--foreground);
}

.confirm-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--muted-foreground);
}
</style>
