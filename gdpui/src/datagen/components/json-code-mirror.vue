<template>
  <div ref="host" class="json-code-mirror" :class="{ 'is-readonly': readOnly }"></div>
</template>

<script lang="ts">
import Vue from 'vue'
import { EditorState, type Extension } from '@codemirror/state'
import { EditorView, keymap, placeholder as cmPlaceholder } from '@codemirror/view'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { json } from '@codemirror/lang-json'
import { syntaxHighlighting, defaultHighlightStyle } from '@codemirror/language'

/**
 * Thin Vue 2 wrapper around CodeMirror 6 for JSON editing.
 *
 * The React source used `@uiw/react-codemirror` (React-only), so this rebuilds
 * the same capability on the framework-agnostic CodeMirror 6 core: JSON syntax
 * highlighting, optional read-only mode, and a `v-model`-style `value` prop with
 * a `change` event. Theme follows the app's design tokens rather than monokai/
 * basic-light, so it blends with the rest of the migrated UI.
 *
 * We diff `value` against the live document before dispatching so external
 * updates (e.g. "格式化") apply without clobbering the cursor on every keystroke.
 */
export default Vue.extend({
  name: 'JsonCodeMirror',
  props: {
    value: { type: String, default: '' },
    readOnly: { type: Boolean, default: false },
    placeholder: { type: String, default: '' },
    /** CSS height, e.g. "180px". */
    height: { type: String, default: '180px' },
  },
  data() {
    return {
      view: null as EditorView | null,
    }
  },
  watch: {
    value(next: string) {
      const view = this.view
      if (!view) return
      const current = view.state.doc.toString()
      if (next === current) return
      view.dispatch({
        changes: { from: 0, to: current.length, insert: next ?? '' },
      })
    },
    readOnly() {
      // Rebuild to swap the read-only/editable facets cleanly.
      this.destroyView()
      this.createView()
    },
  },
  mounted() {
    this.createView()
  },
  beforeDestroy() {
    this.destroyView()
  },
  methods: {
    extensions(): Extension[] {
      const base: Extension[] = [
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        json(),
        syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
        EditorView.lineWrapping,
        EditorView.theme({
          '&': { fontSize: '12px', backgroundColor: 'transparent' },
          '.cm-content': {
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          },
          '.cm-gutters': { backgroundColor: 'transparent', border: 'none' },
          '&.cm-focused': { outline: 'none' },
        }),
      ]
      if (this.placeholder) base.push(cmPlaceholder(this.placeholder))
      if (this.readOnly) {
        base.push(EditorState.readOnly.of(true))
        base.push(EditorView.editable.of(false))
      } else {
        base.push(
          EditorView.updateListener.of((update) => {
            if (update.docChanged) {
              this.$emit('change', update.state.doc.toString())
            }
          }),
        )
      }
      return base
    },
    createView() {
      const host = this.$refs.host as HTMLElement
      if (!host) return
      host.style.setProperty('--cm-height', this.height)
      this.view = new EditorView({
        state: EditorState.create({
          doc: this.value ?? '',
          extensions: this.extensions(),
        }),
        parent: host,
      })
    },
    destroyView() {
      if (this.view) {
        this.view.destroy()
        this.view = null
      }
    },
  },
})
</script>

<style scoped>
.json-code-mirror {
  width: 100%;
}

.json-code-mirror >>> .cm-editor {
  height: var(--cm-height, 180px);
}

.json-code-mirror >>> .cm-scroller {
  overflow: auto;
}
</style>
