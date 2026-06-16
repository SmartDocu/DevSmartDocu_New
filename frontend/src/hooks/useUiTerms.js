import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useAdminUiTerms() {
  return useQuery({
    queryKey: ['admin-ui-terms'],
    queryFn: () => apiClient.get('/admin/ui-terms').then((r) => r.data.items),
  })
}
