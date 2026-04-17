import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useConfigs() {
  return useQuery({
    queryKey: ['configs'],
    queryFn: () => apiClient.get('/configs').then((r) => r.data),
    staleTime: 10 * 60 * 1000,
  })
}
