import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useApps({ enabled = true, tenantid } = {}) {
  return useQuery({
    queryKey: ['apps', tenantid],
    queryFn: () =>
      apiClient.get('/apps', { params: tenantid ? { tenantid } : {} }).then((r) => r.data),
    staleTime: 10 * 60 * 1000,
    enabled,
  })
}
