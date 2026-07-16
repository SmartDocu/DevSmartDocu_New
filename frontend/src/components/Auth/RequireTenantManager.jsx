import { Navigate, useParams } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'

export default function RequireTenantManager({ children }) {
  const { appcd } = useParams()
  const tenantmanager = useAuthStore((s) => s.user?.tenantmanager)

  if (tenantmanager !== 'Y') {
    return <Navigate to={`/app/${appcd}`} replace />
  }

  return children
}
