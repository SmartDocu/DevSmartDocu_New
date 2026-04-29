import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useChartTypes() {
  return useQuery({
    queryKey: ['chart-types'],
    queryFn: () => apiClient.get('/charts/types').then((r) => r.data.chart_types),
  })
}

export function useChart(chapteruid, objectnm) {
  return useQuery({
    queryKey: ['chart', chapteruid, objectnm],
    queryFn: () =>
      apiClient.get('/charts', { params: { chapteruid, objectnm } }).then((r) => r.data.chart),
    enabled: !!(chapteruid && objectnm),
  })
}

export function useSaveChart() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/charts', body).then((r) => r.data),
    onSuccess: (_data, body) => {
      qc.invalidateQueries({ queryKey: ['chart', body.chapteruid, body.objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', body.chapteruid] })
    },
  })
}

export function useDeleteChart() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ chapteruid, objectnm }) =>
      apiClient.delete('/charts', { params: { chapteruid, objectnm } }).then((r) => r.data),
    onSuccess: (_data, { chapteruid, objectnm }) => {
      qc.invalidateQueries({ queryKey: ['chart', chapteruid, objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', chapteruid] })
    },
  })
}
