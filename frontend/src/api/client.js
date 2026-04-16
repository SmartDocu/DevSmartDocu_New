import axios from 'axios'
import { useAuthStore } from '@/stores/authStore'

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
})

// ─── 요청 인터셉터 ────────────────────────────────────────────────────────────
apiClient.interceptors.request.use((config) => {
  const token = useAuthStore.getState().accessToken
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ─── 응답 인터셉터: 401 시 토큰 갱신 후 재시도 ───────────────────────────────
let _isRefreshing = false
let _queue = [] // 갱신 대기 중인 요청들

const processQueue = (error, token = null) => {
  _queue.forEach(({ resolve, reject }) => {
    if (error) reject(error)
    else resolve(token)
  })
  _queue = []
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // 401이고 auth 엔드포인트 자체가 아닌 경우에만 갱신 시도
    if (
      error.response?.status === 401 &&
      !originalRequest._retried &&
      !originalRequest.url?.includes('/auth/refresh') &&
      !originalRequest.url?.includes('/auth/login')
    ) {
      const { useAuthStore } = await import('@/stores/authStore')
      const { refreshToken, updateTokens, clearAuth } = useAuthStore.getState()

      if (!refreshToken) {
        clearAuth()
        window.location.href = '/'
        return Promise.reject(error)
      }

      if (_isRefreshing) {
        // 이미 갱신 중이면 대기열에 추가
        return new Promise((resolve, reject) => {
          _queue.push({ resolve, reject })
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`
          return apiClient(originalRequest)
        })
      }

      originalRequest._retried = true
      _isRefreshing = true

      try {
        const resp = await axios.post('/api/auth/refresh', { refresh_token: refreshToken })
        const { access_token, refresh_token: new_refresh } = resp.data
        updateTokens({ accessToken: access_token, refreshToken: new_refresh })
        processQueue(null, access_token)
        originalRequest.headers.Authorization = `Bearer ${access_token}`
        return apiClient(originalRequest)
      } catch (refreshError) {
        processQueue(refreshError, null)
        clearAuth()
        window.location.href = '/'
        return Promise.reject(refreshError)
      } finally {
        _isRefreshing = false
      }
    }

    return Promise.reject(error)
  },
)

export default apiClient
