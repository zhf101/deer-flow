<template>
  <div v-if="mode === 'loading'" class="setup-loading">
    <span>Loading...</span>
  </div>

  <div v-else class="auth-page">
    <div class="auth-background" />
    <section class="auth-panel">
      <div class="auth-header">
        <h1>DeerFlow</h1>
        <template v-if="mode === 'init_admin'">
          <p>Create admin account</p>
          <small>Set up the administrator account to get started.</small>
        </template>
        <template v-else>
          <p>Complete admin account setup</p>
          <small>Set your real email and a new password.</small>
        </template>
      </div>

      <el-form class="auth-form" @submit.native.prevent="handleSubmit">
        <el-form-item label="Email" required>
          <el-input
            v-model="email"
            type="email"
            autocomplete="username"
            placeholder="you@example.com"
          />
        </el-form-item>

        <el-form-item v-if="mode === 'change_password'" label="Current password" required>
          <el-input
            v-model="currentPassword"
            type="password"
            autocomplete="current-password"
            placeholder="Current password"
            show-password
          />
        </el-form-item>

        <el-form-item label="Password" required>
          <el-input
            v-model="newPassword"
            type="password"
            autocomplete="new-password"
            placeholder="Password (min. 8 characters)"
            show-password
          />
        </el-form-item>

        <el-form-item label="Confirm password" required>
          <el-input
            v-model="confirmPassword"
            type="password"
            autocomplete="new-password"
            placeholder="Confirm password"
            show-password
          />
        </el-form-item>

        <p v-if="error" class="auth-error">{{ error }}</p>

        <el-button
          native-type="submit"
          type="primary"
          class="auth-submit"
          :loading="loading"
        >
          {{ submitText }}
        </el-button>
      </el-form>
    </section>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import { AuthRequestError } from '@/auth/api'
import { useAuthStore } from '@/stores/auth'

type SetupMode = 'loading' | 'init_admin' | 'change_password'

export default Vue.extend({
  name: 'SetupView',
  data() {
    return {
      mode: 'loading' as SetupMode,
      email: '',
      currentPassword: '',
      newPassword: '',
      confirmPassword: '',
      error: '',
      loading: false,
    }
  },
  computed: {
    submitText(): string {
      if (this.loading) return this.mode === 'init_admin' ? 'Creating account...' : 'Setting up...'
      return this.mode === 'init_admin' ? 'Create Admin Account' : 'Complete Setup'
    },
  },
  created() {
    void this.resolveMode()
  },
  methods: {
    async resolveMode() {
      const auth = useAuthStore()
      const user = await auth.ensureUser()

      if (user?.needs_setup) {
        this.email = user.email || ''
        this.mode = 'change_password'
        return
      }

      if (!user) {
        try {
          const data = await auth.getSetupStatus()
          if (data.needs_setup) {
            this.mode = 'init_admin'
          } else {
            void this.$router.replace('/login')
          }
        } catch {
          void this.$router.replace('/login')
        }
        return
      }

      void this.$router.replace('/datagen/scenes')
    },
    validateForm(): boolean {
      if (!this.email || !this.newPassword || !this.confirmPassword) {
        this.error = 'Email and password are required'
        return false
      }
      if (this.mode === 'change_password' && !this.currentPassword) {
        this.error = 'Current password is required'
        return false
      }
      if (this.newPassword !== this.confirmPassword) {
        this.error = 'Passwords do not match'
        return false
      }
      if (this.newPassword.length < 8) {
        this.error = 'Password must be at least 8 characters'
        return false
      }
      return true
    },
    async handleSubmit() {
      if (!this.validateForm()) return

      this.error = ''
      this.loading = true
      const auth = useAuthStore()

      try {
        if (this.mode === 'init_admin') {
          await auth.initialize(this.email, this.newPassword)
        } else {
          await auth.completeSetup(this.email, this.currentPassword, this.newPassword)
        }
        void this.$router.push('/datagen/scenes')
      } catch (error) {
        this.error = error instanceof AuthRequestError
          ? error.message
          : 'Network error. Please try again.'
      } finally {
        this.loading = false
      }
    },
  },
})
</script>

<style scoped>
.setup-loading,
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--background);
  color: var(--foreground);
}

.setup-loading {
  color: var(--muted-foreground);
  font-size: 14px;
}

.auth-page {
  position: relative;
  overflow: hidden;
  padding: 24px;
}

.auth-background {
  position: absolute;
  inset: 0;
  opacity: 0.45;
  background-image:
    linear-gradient(var(--border) 1px, transparent 1px),
    linear-gradient(90deg, var(--border) 1px, transparent 1px);
  background-size: 22px 22px;
  mask-image: radial-gradient(circle at center, black 0, transparent 68%);
}

.auth-panel {
  position: relative;
  width: min(100%, 420px);
  padding: 32px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: color-mix(in oklch, var(--card) 92%, transparent);
  box-shadow: 0 18px 60px rgb(0 0 0 / 12%);
  backdrop-filter: blur(10px);
}

.auth-header {
  text-align: center;
  margin-bottom: 24px;
}

.auth-header h1 {
  margin: 0;
  font-size: 30px;
  font-weight: 700;
}

.auth-header p {
  margin: 8px 0 0;
  color: var(--muted-foreground);
  font-size: 14px;
}

.auth-header small {
  display: block;
  margin-top: 4px;
  color: var(--muted-foreground);
}

.auth-error {
  margin: -2px 0 12px;
  color: #dc2626;
  font-size: 13px;
}

.auth-submit {
  width: 100%;
}
</style>
