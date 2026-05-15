import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import axios from 'axios'

try {
  localStorage.removeItem('smart-doc-auth')
} catch (_) {}

let _refreshTimer = null

function _getExpMs(token) {
  try {
    return JSON.parse(atob(token.split('.')[1])).exp * 1000
  } catch {
    return null
  }
}

async function _doRefresh(refreshToken) {
  try {
    const resp = await axios.post('/api/auth/refresh', { refresh_token: refreshToken })
    const { access_token, refresh_token: newRefresh } = resp.data
    useAuthStore.getState().updateTokens({ accessToken: access_token, refreshToken: newRefresh })
  } catch {
    useAuthStore.getState().clearAuth()
    window.location.href = '/'
  }
}

function _schedule(accessToken, refreshToken) {
  if (_refreshTimer) { clearTimeout(_refreshTimer); _refreshTimer = null }
  if (!accessToken || !refreshToken) return
  const exp = _getExpMs(accessToken)
  if (!exp) return
  const delay = exp - Date.now() - 5 * 60 * 1000 // 만료 5분 전 갱신
  if (delay <= 0) {
    _doRefresh(refreshToken)
    return
  }
  _refreshTimer = setTimeout(() => _doRefresh(refreshToken), delay)
}

export const useAuthStore = create(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,

      setAuth: ({ accessToken, refreshToken, user }) => {
        set({ accessToken, refreshToken, user })
        _schedule(accessToken, refreshToken)
      },

      updateTokens: ({ accessToken, refreshToken }) => {
        set({ accessToken, refreshToken })
        _schedule(accessToken, refreshToken)
      },

      updateUser: (patch) =>
        set((state) => ({ user: state.user ? { ...state.user, ...patch } : state.user })),

      clearAuth: () => {
        if (_refreshTimer) { clearTimeout(_refreshTimer); _refreshTimer = null }
        set({ accessToken: null, refreshToken: null, user: null })
      },

      isAuthenticated: () => !!get().accessToken,

      initRefresh: () => {
        const { accessToken, refreshToken } = get()
        _schedule(accessToken, refreshToken)
      },
    }),
    {
      name: 'smart-doc-auth',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
    },
  ),
)
