import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

/**
 * 인증이 필요한 라우트를 보호하는 컴포넌트.
 * 로그인되지 않은 경우 /login 으로 리다이렉트하고
 * 원래 접근하려던 경로를 state로 전달한다.
 */
export default function RequireAuth({ children }) {
  const isAuthenticated = useAuthStore((s) => !!s.accessToken)
  const location = useLocation()

  if (!isAuthenticated) {
    return <Navigate to="/" state={{ from: location }} replace />
  }

  return children
}
