import { Navigate, useParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

export default function RequireNotSystemTenant({ children }) {
  const { appcd } = useParams()
  const issystemtenant = useAuthStore((s) => s.user?.issystemtenant)

  if (issystemtenant) {
    return <Navigate to={`/app/${appcd}`} replace />
  }

  return children
}
