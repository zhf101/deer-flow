export interface User {
  id: string
  email: string
  system_role: 'admin' | 'user'
  needs_setup?: boolean
}

export interface AuthErrorResponse {
  code: string
  message: string
}

const AUTH_ERROR_CODES = new Set([
  'invalid_credentials',
  'token_expired',
  'token_invalid',
  'user_not_found',
  'email_already_exists',
  'provider_not_found',
  'not_authenticated',
  'system_already_initialized',
])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isAuthError(value: unknown): value is AuthErrorResponse {
  if (!isRecord(value)) return false
  return (
    typeof value.code === 'string' &&
    AUTH_ERROR_CODES.has(value.code) &&
    typeof value.message === 'string'
  )
}

function readValidationMessage(value: unknown): string | null {
  if (!isRecord(value)) return null
  return typeof value.msg === 'string' ? value.msg : null
}

export function parseAuthError(data: unknown): AuthErrorResponse {
  if (isAuthError(data)) return data

  if (isRecord(data) && 'detail' in data) {
    const detail = data.detail
    if (isAuthError(detail)) return detail
    if (typeof detail === 'string') {
      return { code: 'invalid_credentials', message: detail }
    }
    if (Array.isArray(detail)) {
      const message = readValidationMessage(detail[0])
      if (message) return { code: 'invalid_credentials', message }
    }
    const message = readValidationMessage(detail)
    if (message) return { code: 'invalid_credentials', message }
  }

  return { code: 'invalid_credentials', message: 'Authentication failed' }
}

export function validateNextParam(next: unknown): string | null {
  if (typeof next !== 'string' || !next) return null
  if (!next.startsWith('/')) return null
  if (next.startsWith('//')) return null
  if (next.startsWith('http://') || next.startsWith('https://')) return null
  if (next.includes(':') && !next.startsWith('/')) return null
  return next
}

export function buildLoginPath(returnPath: string): string {
  return `/login?next=${encodeURIComponent(returnPath)}`
}
