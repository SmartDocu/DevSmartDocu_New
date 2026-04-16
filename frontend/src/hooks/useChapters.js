import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import apiClient from '@/api/client'

export function useChapters(docid) {
  return useQuery({
    queryKey: ['chapters', docid],
    queryFn: () => apiClient.get('/chapters', { params: { docid } }).then((r) => r.data.chapters),
    enabled: !!docid,
  })
}

export function useSaveChapter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (formData) => apiClient.post('/chapters', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data),
    onSuccess: (_data, formData) => {
      message.success('챕터가 저장되었습니다.')
      const docid = formData.get('docid')
      qc.invalidateQueries({ queryKey: ['chapters', Number(docid)] })
    },
    onError: (err) => {
      message.error(err.response?.data?.detail || '저장에 실패했습니다.')
    },
  })
}

export function useDeleteChapter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ chapteruid, docid }) =>
      apiClient.delete(`/chapters/${chapteruid}`).then((r) => r.data),
    onSuccess: (_data, { docid }) => {
      message.success('챕터가 삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['chapters', docid] })
    },
    onError: (err) => {
      message.error(err.response?.data?.detail || '삭제에 실패했습니다.')
    },
  })
}
