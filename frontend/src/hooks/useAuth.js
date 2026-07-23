import { useMutation, useQuery } from '@tanstack/react-query'
import { useNavigate, useLocation } from 'react-router-dom'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'
import { t } from '@/stores/langStore'

export function useLogin() {
  const navigate = useNavigate()
  const location = useLocation()
  const setAuth = useAuthStore((s) => s.setAuth)

  return useMutation({
    mutationFn: (credentials) => apiClient.post('/auth/login', credentials).then((r) => r.data),
    onSuccess: (data) => {
      setAuth({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
        user: data.user,
      })
      alert(t('msg.login.success'))
      const from = location.state?.from?.pathname || '/launcher'
      navigate(from, { replace: true })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail || t('msg.login.failed')
      alert(detail)
    },
  })
}

export function useLogout() {
  const navigate = useNavigate()
  const clearAuth = useAuthStore((s) => s.clearAuth)

  return useMutation({
    mutationFn: () => apiClient.post('/auth/logout').then((r) => r.data),
    onSettled: () => {
      clearAuth()
      navigate('/', { replace: true })
    },
  })
}

export function useSendResetEmail() {
  return useMutation({
    mutationFn: (email) =>
      apiClient.post('/auth/send-reset-email', { email }).then((r) => r.data),
    onSuccess: () => alert(t('msg.reset.sent')),
    onError: (err) => {
      const detail = err.response?.data?.detail || t('msg.reset.failed')
      alert(detail)
    },
  })
}

export function useRegister() {
  const navigate = useNavigate()

  return useMutation({
    mutationFn: (data) => apiClient.post('/auth/register', data).then((r) => r.data),
    onSuccess: () => {
      alert(t('msg.register.success'))
      navigate('/')
    },
    onError: (err) => {
      const detail = err.response?.data?.detail || t('msg.register.failed')
      alert(detail)
    },
  })
}

export function useMe(enabled) {
  return useQuery({
    queryKey: ['auth-me'],
    queryFn: () => apiClient.get('/auth/me').then((r) => r.data),
    enabled,
    staleTime: Infinity,
    retry: false,
  })
}

export function useInviteInfo(req) {
  return useQuery({
    queryKey: ['invite-info', req],
    queryFn: () => apiClient.get('/auth/invite-info', { params: { req } }).then((r) => r.data),
    enabled: !!req,
    retry: false,
  })
}

export function useRegisterInvite() {
  return useMutation({
    mutationFn: (data) => apiClient.post('/auth/register-invite', data).then((r) => r.data),
  })
}
