import { useMutation } from '@tanstack/react-query'
import { useNavigate, useLocation } from 'react-router-dom'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

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
      alert('로그인이 완료되었습니다.')
      const from = location.state?.from?.pathname || '/'
      navigate(from, { replace: true })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail || '로그인에 실패했습니다.'
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
    onSuccess: () => alert('비밀번호 재설정 이메일을 발송했습니다.'),
    onError: (err) => {
      const detail = err.response?.data?.detail || '이메일 발송에 실패했습니다.'
      alert(detail)
    },
  })
}

export function useSendSms() {
  return useMutation({
    mutationFn: (phone_number) =>
      apiClient.post('/auth/send-sms', { phone_number }).then((r) => r.data),
    onSuccess: () => alert('인증번호를 발송했습니다.'),
    onError: (err) => {
      const detail = err.response?.data?.detail || 'SMS 발송에 실패했습니다.'
      alert(detail)
    },
  })
}

export function useVerifySms() {
  return useMutation({
    mutationFn: ({ phone_number, code }) =>
      apiClient.post('/auth/verify-sms', { phone_number, code }).then((r) => r.data),
    onError: (err) => {
      const detail = err.response?.data?.detail || '인증에 실패했습니다.'
      alert(detail)
    },
  })
}

export function useRegister() {
  const navigate = useNavigate()

  return useMutation({
    mutationFn: (data) => apiClient.post('/auth/register', data).then((r) => r.data),
    onSuccess: () => {
      alert('회원가입이 완료되었습니다. 로그인해주세요.')
      navigate('/login')
    },
    onError: (err) => {
      const detail = err.response?.data?.detail || '회원가입에 실패했습니다.'
      alert(detail)
    },
  })
}
