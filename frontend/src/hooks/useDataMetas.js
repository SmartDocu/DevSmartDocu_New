import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useDataMetaDatas() {
  return useQuery({
    queryKey: ['data-meta-datas'],
    queryFn: () => apiClient.get('/data-metas/datas').then((r) => r.data.datas),
  })
}

export function useDataMeta(datauid) {
  return useQuery({
    queryKey: ['data-meta', datauid],
    queryFn: () => apiClient.get(`/data-metas/${datauid}`).then((r) => r.data.meta),
    enabled: !!datauid,
  })
}

export function useSaveDataMeta() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/data-metas', body).then((r) => r.data),
    onSuccess: (_, body) => {
      qc.invalidateQueries({ queryKey: ['data-meta', body.datauid] })
      qc.invalidateQueries({ queryKey: ['data-meta-datas'] })
    },
  })
}

export function useDeleteDataMeta() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (datauid) => apiClient.delete(`/data-metas/${datauid}`).then((r) => r.data),
    onSuccess: (_, datauid) => {
      qc.invalidateQueries({ queryKey: ['data-meta', datauid] })
      qc.invalidateQueries({ queryKey: ['data-meta-datas'] })
    },
  })
}
