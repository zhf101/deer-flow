<template>
  <div class="rsn">
    <div class="rsn-row">
      <!-- Key -->
      <div class="rsn-key">
        <button
          v-if="!isLeaf"
          type="button"
          class="rsn-toggle"
          @click="expanded = !expanded"
        >
          <font-awesome-icon :icon="expanded ? 'chevron-down' : 'chevron-right'" />
        </button>
        <span v-else class="rsn-toggle-spacer" />
        <span class="rsn-name" :style="{ paddingLeft: depth * 12 + 'px' }">
          {{ field.name }}
        </span>
      </div>

      <!-- Type -->
      <div>
        <span class="rsn-type">{{ typeBadge }}</span>
      </div>

      <!-- Sample value -->
      <div>
        <el-input
          v-if="isLeaf"
          :value="sampleValue"
          size="small"
          class="rsn-mono"
          placeholder="示例值"
          @input="onUpdateField(flatIndex, 'defaultValue', $event)"
        />
        <span v-else class="rsn-container-label">
          ({{ field.type === 'array' ? `array[${(field.children || []).length}]` : 'object' }})
        </span>
      </div>

      <!-- Description -->
      <el-input
        :value="field.label || ''"
        size="small"
        placeholder="字段说明"
        @input="onUpdateField(flatIndex, 'label', $event)"
      />
    </div>

    <!-- Children -->
    <template v-if="!isLeaf && expanded">
      <response-schema-node
        v-for="(child, i) in field.children"
        :key="i"
        :field="child"
        :flat-index="childFlatIndex(i)"
        :depth="depth + 1"
        :on-update-field="onUpdateField"
      />
    </template>
  </div>
</template>

<script lang="ts">
import Vue, { type PropType } from 'vue'

import type { InputFieldDefinition } from '@/datagen/common/lib/types'
import { countFields } from '@/datagen/common/lib/schema-utils'
import { formatUnknownValue } from '@/datagen/common/lib/value-utils'

type FieldProp = 'defaultValue' | 'label' | 'remark'

/**
 * Recursive node for the response *schema* tree (read structure, edit
 * sample value + description). Distinct from the request body's TreeNode:
 * updates flow through a `flatIndex` + prop callback (matching the source's
 * `updateFieldPropAtPath`) rather than immutable child cloning, because the
 * response editor keeps the schema flat-indexed for in-place edits.
 */
export default Vue.extend({
  name: 'ResponseSchemaNode',
  props: {
    field: { type: Object as PropType<InputFieldDefinition>, required: true },
    flatIndex: { type: Number, required: true },
    depth: { type: Number, default: 0 },
    onUpdateField: {
      type: Function as PropType<(flatIndex: number, prop: FieldProp, value: unknown) => void>,
      required: true,
    },
  },
  data() {
    return {
      expanded: this.depth < 2,
    }
  },
  computed: {
    isLeaf(): boolean {
      return this.field.type !== 'object' && this.field.type !== 'array'
    },
    sampleValue(): string {
      return formatUnknownValue(this.field.defaultValue)
    },
    typeBadge(): string {
      if (!this.isLeaf) {
        return this.field.type === 'array'
          ? `array${this.field.children ? `[${this.field.children.length}]` : ''}`
          : 'object'
      }
      return this.field.type
    },
  },
  methods: {
    /** Compute a child's flat index: parent + 1 + sum of preceding siblings' field counts. */
    childFlatIndex(i: number): number {
      let idx = this.flatIndex + 1
      const children = this.field.children ?? []
      for (let j = 0; j < i; j += 1) {
        idx += countFields(children[j]!)
      }
      return idx
    },
  },
})
</script>

<style scoped>
.rsn-row {
  display: grid;
  grid-template-columns: 1fr 80px 150px 1fr;
  gap: 8px;
  align-items: center;
  padding: 6px 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}

.rsn-row:hover {
  background-color: var(--accent);
}

.rsn-key {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.rsn-toggle {
  flex-shrink: 0;
  padding: 2px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--muted-foreground);
  font-size: 11px;
}

.rsn-toggle-spacer {
  width: 16px;
  flex-shrink: 0;
}

.rsn-name {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  font-weight: 500;
  color: var(--foreground);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rsn-type {
  font-size: 9px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  text-transform: uppercase;
  color: var(--muted-foreground);
  background-color: var(--muted);
  padding: 1px 6px;
  border-radius: 3px;
}

.rsn-mono >>> .el-input__inner {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.rsn-container-label {
  font-size: 10px;
  font-style: italic;
  color: var(--muted-foreground);
}
</style>
