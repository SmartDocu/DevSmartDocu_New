import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
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
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['chart', body.chapteruid, body.objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', body.chapteruid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteChart() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ chapteruid, objectnm }) =>
      apiClient.delete('/charts', { params: { chapteruid, objectnm } }).then((r) => r.data),
    onSuccess: (_data, { chapteruid, objectnm }) => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['chart', chapteruid, objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', chapteruid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
  })
}
