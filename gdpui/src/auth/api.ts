import axios, { AxiosError, type AxiosInstance } from 'axios'

import { parseAuthError, type AuthErrorResponse, type User } from './types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'
const CSRF_COOKIE_PREFIX = 'csrf_token='

const authClient: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/v1/auth`,
  timeout: 30_000,
  withCredentials: true,
  xsrfCookieName: 'csrf_token',
  xsrfHeaderName: 'X-CSRF-Token',
  headers: { Accept: 'application/json' },
})

export class AuthRequestError extends Error {
  constructor(
    public readonly status: number,
    public readonly authError: AuthErrorResponse,
  ) {
    super(authError.message)
    this.name = 'AuthRequestError'
  }
}

function readCsrfCookie(): string | null {
  for (const pair of document.cookie.split('; ')) {
    if (pair.startsWith(CSRF_COOKIE_PREFIX)) {
      return decodeURIComponent(pair.slice(CSRF_COOKIE_PREFIX.length))
    }
  }
  return null
}

function csrfHeaders(): Record<string, string> {
  const token = readCsrfCookie()
  return token ? { 'X-CSRF-Token': token } : {}
}

function toAuthRequestError(error: unknown): AuthRequestError {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError
    return new AuthRequestError(
      axiosError.response?.status ?? 0,
      parseAuthError(axiosError.response?.data),
    )
  }
  return new AuthRequestError(0, {
    code: 'invalid_credentials',
    message: 'Network error. Please try again.',
  })
}

async function request<T>(runner: () => Promise<{ data: T }>): Promise<T> {
  try {
    const response = await runner()
    return response.data
  } catch (error) {
    throw toAuthRequestError(error)
  }
}

export function getCurrentUser(): Promise<User> {
  return request<User>(() => authClient.get('/me'))
}

export function getSetupStatus(): Promise<{ needs_setup?: boolean }> {
  return request<{ needs_setup?: boolean }>(() => authClient.get('/setup-status'))
}

export function loginLocal(email: string, password: string): Promise<{ expires_in: number; needs_setup?: boolean }> {
  const body = new URLSearchParams()
  body.set('username', email)
  body.set('password', password)
  return request(() =>
    authClient.post('/login/local', body.toString(), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  )
}

export function registerUser(email: string, password: string): Promise<User> {
  return request<User>(() => authClient.post('/register', { email, password }))
}

export function initializeAdmin(email: string, password: string): Promise<User> {
  return request<User>(() => authClient.post('/initialize', { email, password }))
}

export function changePassword(body: {
  current_password: string
  new_password: string
  new_email?: string
}): Promise<{ message: string }> {
  return request(() =>
    authClient.post('/change-password', body, {
      headers: {
        'Content-Type': 'application/json',
        ...csrfHeaders(),
      },
    }),
  )
}

export function logoutUser(): Promise<{ message: string }> {
  return request(() => authClient.post('/logout'))
}
