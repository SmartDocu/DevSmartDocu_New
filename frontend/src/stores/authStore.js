import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

// 이전 버전에서 localStorage에 저장된 인증 데이터 제거
// (세션 정책 변경: localStorage → sessionStorage)
try {
  localStorage.removeItem('smart-doc-auth')
} catch (_) {}

export const useAuthStore = create(
  persist(
    (set, get) => ({
      accessToken: null,
      refreshToken: null,
      user: null,

      setAuth: ({ accessToken, refreshToken, user }) =>
        set({ accessToken, refreshToken, user }),

      updateTokens: ({ accessToken, refreshToken }) =>
        set({ accessToken, refreshToken }),

      updateUser: (patch) =>
        set((state) => ({ user: state.user ? { ...state.user, ...patch } : state.user })),

      clearAuth: () =>
        set({ accessToken: null, refreshToken: null, user: null }),

      isAuthenticated: () => !!get().accessToken,
    }),
    {
      name: 'smart-doc-auth',
      // sessionStorage 사용: 브라우저 창/탭을 닫으면 자동 소멸
      // → 이전 Django 앱의 session cookie 방식과 동일한 라이프사이클
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        user: state.user,
      }),
    },
  ),
)
