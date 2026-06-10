import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  changePassword,
  getCurrentUser,
  getSetupStatus,
  initializeAdmin,
  loginLocal,
  logoutUser,
  registerUser,
} from '@/auth/api'
import type { User } from '@/auth/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const checked = ref(false)
  const loading = ref(false)

  const isAuthenticated = computed(() => user.value !== null)

  async function refreshUser(): Promise<User | null> {
    loading.value = true
    try {
      user.value = await getCurrentUser()
      checked.value = true
      return user.value
    } catch {
      user.value = null
      checked.value = true
      return null
    } finally {
      loading.value = false
    }
  }

  async function ensureUser(): Promise<User | null> {
    if (checked.value) return user.value
    return refreshUser()
  }

  async function login(email: string, password: string) {
    const result = await loginLocal(email, password)
    await refreshUser()
    return result
  }

  async function register(email: string, password: string) {
    const created = await registerUser(email, password)
    user.value = created
    checked.value = true
    return created
  }

  async function initialize(email: string, password: string) {
    const created = await initializeAdmin(email, password)
    user.value = created
    checked.value = true
    return created
  }

  async function completeSetup(email: string, currentPassword: string, newPassword: string) {
    await changePassword({
      current_password: currentPassword,
      new_password: newPassword,
      new_email: email || undefined,
    })
    await refreshUser()
  }

  async function logout() {
    user.value = null
    checked.value = true
    try {
      await logoutUser()
    } catch {
      // 登出时本地状态已经清空，后端请求失败不阻止跳转
    }
  }

  return {
    user,
    checked,
    loading,
    isAuthenticated,
    refreshUser,
    ensureUser,
    login,
    register,
    initialize,
    completeSetup,
    logout,
    getSetupStatus,
  }
})
