import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import apiClient from '@/api/client'

export function useTable(chapteruid, objectnm) {
  return useQuery({
    queryKey: ['table', chapteruid, objectnm],
    queryFn: () =>
      apiClient.get('/tables', { params: { chapteruid, objectnm } }).then((r) => r.data.table),
    enabled: !!(chapteruid && objectnm),
  })
}

export function useSaveTable() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/tables', body).then((r) => r.data),
    onSuccess: (_data, body) => {
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['table', body.chapteruid, body.objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', body.chapteruid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteTable() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ chapteruid, objectnm }) =>
      apiClient.delete('/tables', { params: { chapteruid, objectnm } }).then((r) => r.data),
    onSuccess: (_data, { chapteruid, objectnm }) => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['table', chapteruid, objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', chapteruid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
  })
}
