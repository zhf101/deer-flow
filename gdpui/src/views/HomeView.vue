<script setup lang="ts">
import { ref } from 'vue'
import { useCounterStore } from '@/stores/counter'

const counter = useCounterStore()
const message = ref('Welcome to gdpui')
</script>

<template>
  <main class="mx-auto flex max-w-3xl flex-col gap-6 p-8">
    <header class="flex items-center gap-3">
      <font-awesome-icon icon="bolt" class="text-2xl text-blue-500" />
      <h1 class="text-2xl font-semibold">{{ message }}</h1>
    </header>

    <section class="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <p class="mb-4 text-gray-600">
        Vue 2.7 + TypeScript + Vite + Pinia + Element UI + Tailwind CSS v4
      </p>

      <div class="flex items-center gap-4">
        <el-button type="primary" @click="counter.increment">
          Count is {{ counter.count }}
        </el-button>
        <el-button @click="counter.reset">Reset</el-button>
        <span class="text-sm text-gray-500">doubled: {{ counter.doubled }}</span>
      </div>
    </section>
  </main>
</template>

<style scoped></style>
