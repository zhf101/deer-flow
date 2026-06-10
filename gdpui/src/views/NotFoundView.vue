<script setup lang="ts">
import { useRouter } from 'vue-router/composables'

const router = useRouter()
</script>

<template>
  <main class="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 p-8 text-center">
    <p class="text-6xl font-bold text-gray-300">404</p>
    <h1 class="text-xl font-semibold">Page not found</h1>
    <p class="text-gray-500">The page you are looking for does not exist.</p>
    <el-button type="primary" @click="router.push('/')">Back to home</el-button>
  </main>
</template>

<style scoped></style>
