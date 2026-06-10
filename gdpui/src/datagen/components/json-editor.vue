<template>
  <div class="json-editor" :class="className">
    <div class="json-editor-head">
      <span class="json-editor-label">{{ label }}</span>
      <el-button type="text" size="mini" @click="formatNow">格式化</el-button>
    </div>
    <div class="json-editor-box">
      <json-code-mirror :value="text" :height="height" @change="apply" />
    </div>
    <p v-if="error" class="json-editor-error">{{ error }}</p>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import { formatJson, parseJsonObject } from '@/datagen/common/lib/validation'
import JsonCodeMirror from './json-code-mirror.vue'

/**
 * JSON object editor ported from the React `JsonEditor`. Edits a
 * `Record<string, unknown>` as formatted JSON text; emits parsed objects via
 * `change`, surfacing parse errors inline without losing the user's text.
 */
export default Vue.extend({
  name: 'JsonEditor',
  components: { JsonCodeMirror },
  props: {
    label: { type: String, required: true },
    value: { type: Object, default: () => ({}) },
    className: { type: String, default: '' },
    height: { type: String, default: '180px' },
  },
  data() {
    return {
      text: formatJson(this.value as Record<string, unknown>),
      error: null as string | null,
    }
  },
  watch: {
    value: {
      handler(next: Record<string, unknown>) {
        // Re-sync when the parent replaces the object wholesale (not on our own edits).
        try {
          const parsedCurrent = parseJsonObject(this.text)
          if (JSON.stringify(parsedCurrent) === JSON.stringify(next)) return
        } catch {
          /* fall through to reformat */
        }
        this.text = formatJson(next)
        this.error = null
      },
      deep: true,
    },
  },
  methods: {
    apply(nextText: string) {
      this.text = nextText
      try {
        const parsed = parseJsonObject(nextText)
        this.error = null
        this.$emit('change', parsed)
      } catch (cause) {
        this.error = cause instanceof Error ? cause.message : 'JSON 格式错误'
      }
    },
    formatNow() {
      this.apply(formatJson(this.value as Record<string, unknown>))
    },
  },
})
</script>

<style scoped>
.json-editor-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.json-editor-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--muted-foreground);
}

.json-editor-box {
  border: 1px solid var(--input);
  background-color: var(--muted);
  border-radius: 6px;
  overflow: hidden;
}

.json-editor-error {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--destructive);
}
</style>
