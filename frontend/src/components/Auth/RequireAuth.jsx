import { Navigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useTabStore } from '@/stores/tabStore'

export default function RequireAuth({ children }) {
  const isAuthenticated = useAuthStore((s) => !!s.accessToken)
  const location = useLocation()

  if (!isAuthenticated) {
    useTabStore.getState().clearTabs()
    return <Navigate to="/" state={{ from: location }} replace />
  }

  return children
}
