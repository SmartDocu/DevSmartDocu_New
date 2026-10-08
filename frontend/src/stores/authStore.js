import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import axios from 'axios'

const AUTH_KEY = 'smart-doc-auth'
const KEEP_KEY = 'smart-doc-keep'

function _isKeep() {
  try { return localStorage.getItem(KEEP_KEY) === '1' } catch { return false }
}

// "로그인 상태 유지" 플래그 — 켜져 있으면 인증 정보를 localStorage(브라우저를 닫아도 유지)에,
// 꺼져 있으면 sessionStorage(탭 단위)에 저장한다. 로그인 직전에 호출할 것.
export function setKeepLogin(keep) {
  try {
    if (keep) localStorage.setItem(KEEP_KEY, '1')
    else localStorage.removeItem(KEEP_KEY)
  } catch (_) {}
}

const authStorage = {
  getItem: (name) => {
    try {
      return (_isKeep() ? localStorage : sessionStorage).getItem(name)
    } catch { return null }
  },
  setItem: (name, value) => {
    try {
      if (_isKeep()) { localStorage.setItem(name, value); sessionStorage.removeItem(name) }
      else { sessionStorage.setItem(name, value); localStorage.removeItem(name) }
    } catch (_) {}
  },
  removeItem: (name) => {
    try { localStorage.removeItem(name); sessionStorage.removeItem(name) } catch (_) {}
  },
}

// 유지 플래그 없이 남은 예전 localStorage 인증 정보는 정리
try {
  if (!_isKeep()) localStorage.removeItem(AUTH_KEY)
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

      switchTenant: (tenantid) =>
        set((state) => ({
          user: state.user ? {
            ...state.user,
            tenantid: String(tenantid),
            docid: null,
            docnm: null,
            projectid: null,
            editbuttonyn: 'N',
            accountuid: null,
            accountmanager: 'N',
          } : state.user,
        })),

      clearAuth: () => {
        if (_refreshTimer) { clearTimeout(_refreshTimer); _refreshTimer = null }
        setKeepLogin(false)
        set({ accessToken: null, refreshToken: null, user: null })
      },

      isAuthenticated: () => !!get().accessToken,

      initRefresh: () => {
        const { accessToken, refreshToken } = get()
        _schedule(accessToken, refreshToken)
      },
    }),
    {
      name: AUTH_KEY,
      storage: createJSONStorage(() => authStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
    },
  ),
)

// 로그인 유지(localStorage) 모드에서 여러 탭이 같은 리프레시 토큰을 각자 갱신하면 서로의 토큰을 무효화하므로,
// 다른 탭이 갱신/로그아웃한 결과를 토큰만 따라간다(user 컨텍스트는 탭별로 독립 유지).
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.storageArea !== localStorage || e.key !== AUTH_KEY) return
    try {
      const next = e.newValue ? JSON.parse(e.newValue)?.state : null
      const st = useAuthStore.getState()
      if (!next?.accessToken) {
        if (st.accessToken) st.clearAuth()
      } else if (next.accessToken !== st.accessToken) {
        st.updateTokens({ accessToken: next.accessToken, refreshToken: next.refreshToken })
      }
    } catch (_) {}
  })
}
