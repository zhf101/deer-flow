import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios'

import { buildLoginPath } from '@/auth/types'

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

/** 统一封装非 2xx 响应和网络异常 */
export class HttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly statusText: string,
    public readonly data: unknown,
  ) {
    super(`HTTP ${status} ${statusText}`)
    this.name = 'HttpError'
  }
}

const instance: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  withCredentials: true,
  xsrfCookieName: 'csrf_token',
  xsrfHeaderName: 'X-CSRF-Token',
  headers: {
    Accept: 'application/json',
  },
})

instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  return config
})

instance.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401 && window.location.pathname !== '/login') {
      window.location.href = buildLoginPath(window.location.pathname + window.location.search)
    }
    if (error.response) {
      return Promise.reject(
        new HttpError(
          error.response.status,
          error.response.statusText,
          error.response.data,
        ),
      )
    }
    return Promise.reject(new HttpError(0, error.message, null))
  },
)

export const http = {
  get: <T>(url: string, config?: AxiosRequestConfig) =>
    instance.get<T>(url, config).then((r) => r.data),
  post: <T>(url: string, body?: unknown, config?: AxiosRequestConfig) =>
    instance.post<T>(url, body, config).then((r) => r.data),
  put: <T>(url: string, body?: unknown, config?: AxiosRequestConfig) =>
    instance.put<T>(url, body, config).then((r) => r.data),
  patch: <T>(url: string, body?: unknown, config?: AxiosRequestConfig) =>
    instance.patch<T>(url, body, config).then((r) => r.data),
  delete: <T>(url: string, config?: AxiosRequestConfig) =>
    instance.delete<T>(url, config).then((r) => r.data),
}

/** 原始 axios 实例，供特殊场景直接配置 */
export { instance as axiosInstance }
