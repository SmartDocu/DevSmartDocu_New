import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useApps({ enabled = true } = {}) {
  return useQuery({
    queryKey: ['apps'],
    queryFn: () => apiClient.get('/apps').then((r) => r.data.apps),
    staleTime: 10 * 60 * 1000,
    enabled,
  })
}
