import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useTabStore } from '@/stores/tabStore'
import { useJobNotifications } from '@/hooks/useJobNotifications'

export default function RequireAuth({ children }) {
  const isAuthenticated = useAuthStore((s) => !!s.accessToken)

  useJobNotifications()

  if (!isAuthenticated) {
    useTabStore.getState().clearTabs()
    return <Navigate to="/" replace />
  }

  return children
}
