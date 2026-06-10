<template>
  <div class="auth-page">
    <div class="auth-background" />
    <section class="auth-panel">
      <div class="auth-header">
        <h1>DeerFlow</h1>
        <p>{{ isLogin ? 'Sign in to your account' : 'Create a new account' }}</p>
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
        <el-form-item label="Password" required>
          <el-input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="Password"
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
          {{ loading ? 'Please wait...' : isLogin ? 'Sign In' : 'Create Account' }}
        </el-button>
      </el-form>

      <button class="mode-switch" type="button" @click="toggleMode">
        {{ isLogin ? "Don't have an account? Sign up" : 'Already have an account? Sign in' }}
      </button>
    </section>
  </div>
</template>

<script lang="ts">
import Vue from 'vue'

import { AuthRequestError } from '@/auth/api'
import { validateNextParam } from '@/auth/types'
import { useAuthStore } from '@/stores/auth'

const DEFAULT_REDIRECT = '/datagen/scenes'

export default Vue.extend({
  name: 'LoginView',
  data() {
    return {
      email: '',
      password: '',
      isLogin: true,
      error: '',
      loading: false,
    }
  },
  computed: {
    redirectPath(): string {
      return validateNextParam(this.$route.query.next) ?? DEFAULT_REDIRECT
    },
  },
  created() {
    void this.redirectAuthenticatedUser()
    void this.redirectToSetupWhenNeeded()
  },
  methods: {
    async redirectAuthenticatedUser() {
      const auth = useAuthStore()
      const user = await auth.ensureUser()
      if (user?.needs_setup) {
        void this.$router.replace('/setup')
        return
      }
      if (user) {
        void this.$router.replace(this.redirectPath)
      }
    },
    async redirectToSetupWhenNeeded() {
      try {
        const auth = useAuthStore()
        const data = await auth.getSetupStatus()
        if (data.needs_setup) {
          void this.$router.replace('/setup')
        }
      } catch {
        // setup-status 失败时保留在登录页，行为与 React 版一致
      }
    },
    toggleMode() {
      this.isLogin = !this.isLogin
      this.error = ''
    },
    validateForm(): boolean {
      if (!this.email || !this.password) {
        this.error = 'Email and password are required'
        return false
      }
      const minLength = this.isLogin ? 6 : 8
      if (this.password.length < minLength) {
        this.error = `Password must be at least ${minLength} characters`
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
        if (this.isLogin) {
          const result = await auth.login(this.email, this.password)
          if (result.needs_setup) {
            void this.$router.push('/setup')
            return
          }
        } else {
          await auth.register(this.email, this.password)
        }
        void this.$router.push(this.redirectPath)
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
.auth-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: var(--background);
  color: var(--foreground);
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

.auth-form {
  display: flex;
  flex-direction: column;
}

.auth-error {
  margin: -2px 0 12px;
  color: #dc2626;
  font-size: 13px;
}

.auth-submit {
  width: 100%;
}

.mode-switch {
  display: block;
  width: 100%;
  margin-top: 16px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #2563eb;
  font-size: 13px;
  cursor: pointer;
}

.mode-switch:hover {
  text-decoration: underline;
}
</style>
