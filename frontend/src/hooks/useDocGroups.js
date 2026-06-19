import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useDocGroups(projectid) {
  return useQuery({
    queryKey: ['docgroups', projectid],
    queryFn: () =>
      apiClient.get('/docgroups', { params: { projectid } }).then((r) => r.data.docgroups),
    enabled: !!projectid,
  })
}

export function useSaveDocGroup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/docgroups', body).then((r) => r.data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['docgroups', variables.projectid] })
    },
  })
}

export function useDeleteDocGroup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ docgroupid }) =>
      apiClient.delete(`/docgroups/${docgroupid}`).then((r) => r.data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ['docgroups', variables.projectid] })
    },
  })
}
