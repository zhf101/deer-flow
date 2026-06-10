import pluginVue from 'eslint-plugin-vue'
import oxlint from 'eslint-plugin-oxlint'

// Uses only the linters declared in package.json:
//   eslint, eslint-plugin-vue, eslint-plugin-oxlint, oxlint.
// TypeScript type errors are surfaced separately by `npm run type-check` (vue-tsc),
// so we keep ESLint focused on Vue/style rules and let oxlint handle correctness.
export default [
  {
    name: 'app/files-to-lint',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },

  {
    name: 'app/files-to-ignore',
    ignores: ['**/dist/**', '**/dist-ssr/**', '**/coverage/**', '**/node_modules/**'],
  },

  ...pluginVue.configs['flat/essential'],

  // Disable ESLint rules already reported by oxlint to avoid duplicate diagnostics.
  ...oxlint.configs['flat/recommended'],
]
