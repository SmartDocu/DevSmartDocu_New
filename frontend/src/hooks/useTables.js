import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useTable(chapteruid, objectnm) {
  return useQuery({
    queryKey: ['table', chapteruid, objectnm],
    queryFn: () =>
      apiClient.get('/tables', { params: { chapteruid, objectnm } }).then((r) => r.data.table),
    enabled: !!(chapteruid && objectnm),
  })
}

export function useObjectFilterDatauid(objectuid, enabled) {
  return useQuery({
    queryKey: ['objectfilter-datauid', objectuid],
    queryFn: () =>
      apiClient.get(`/chapters/objectfilter/${objectuid}`).then((r) => r.data.filter?.objectdatauid || null),
    enabled: !!(objectuid && enabled),
  })
}

export function useSaveTable() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/tables', body).then((r) => r.data),
    onSuccess: (_data, body) => {
      qc.invalidateQueries({ queryKey: ['table', body.chapteruid, body.objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', body.chapteruid] })
    },
  })
}

export function useDeleteTable() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ chapteruid, objectnm }) =>
      apiClient.delete('/tables', { params: { chapteruid, objectnm } }).then((r) => r.data),
    onSuccess: (_data, { chapteruid, objectnm }) => {
      qc.invalidateQueries({ queryKey: ['table', chapteruid, objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', chapteruid] })
    },
  })
}
