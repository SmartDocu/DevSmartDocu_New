import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useApps({ enabled = true, accountuid } = {}) {
  return useQuery({
    queryKey: ['apps', accountuid],
    queryFn: () =>
      apiClient.get('/apps', { params: accountuid ? { accountuid } : {} }).then((r) => r.data),
    staleTime: 10 * 60 * 1000,
    enabled,
  })
}
