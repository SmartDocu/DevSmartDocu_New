import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import apiClient from '@/api/client'

export function useSentence(chapteruid, objectnm) {
  return useQuery({
    queryKey: ['sentence', chapteruid, objectnm],
    queryFn: () =>
      apiClient.get('/sentences', { params: { chapteruid, objectnm } }).then((r) => r.data.sentence),
    enabled: !!(chapteruid && objectnm),
  })
}

export function useSaveSentence() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/sentences', body).then((r) => r.data),
    onSuccess: (_data, body) => {
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['sentence', body.chapteruid, body.objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', body.chapteruid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteSentence() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ chapteruid, objectnm }) =>
      apiClient.delete('/sentences', { params: { chapteruid, objectnm } }).then((r) => r.data),
    onSuccess: (_data, { chapteruid, objectnm }) => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['sentence', chapteruid, objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', chapteruid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
  })
}
