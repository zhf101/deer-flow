import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// Example store using the setup syntax. Demonstrates state, getters,
// actions, and persistence via pinia-plugin-persistedstate.
export const useCounterStore = defineStore(
  'counter',
  () => {
    const count = ref(0)
    const doubled = computed(() => count.value * 2)

    function increment() {
      count.value++
    }

    function reset() {
      count.value = 0
    }

    return { count, doubled, increment, reset }
  },
  {
    persist: true,
  },
)
