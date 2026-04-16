import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import apiClient from '@/api/client'

export function useDocs() {
  return useQuery({
    queryKey: ['docs'],
    queryFn: () => apiClient.get('/docs').then((r) => r.data.docs),
  })
}

export function useProjects() {
  return useQuery({
    queryKey: ['docs-projects'],
    queryFn: () => apiClient.get('/docs/projects').then((r) => r.data.projects),
  })
}

export function useSaveDoc() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (formData) => apiClient.post('/docs', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data),
    onSuccess: () => {
      message.success('문서가 저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['docs'] })
    },
    onError: (err) => {
      message.error(err.response?.data?.detail || '저장에 실패했습니다.')
    },
  })
}

export function useParams(docid) {
  return useQuery({
    queryKey: ['doc-params', docid],
    queryFn: () => apiClient.get(`/docs/${docid}/params`).then((r) => r.data.params),
    enabled: !!docid,
  })
}

export function useSaveParam() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/docs/params', body).then((r) => r.data),
    onSuccess: (_data, body) => {
      message.success('저장되었습니다.')
      qc.invalidateQueries({ queryKey: ['doc-params', body.docid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '저장에 실패했습니다.'),
  })
}

export function useDeleteParam() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ paramuid, docid }) => apiClient.delete(`/docs/params/${paramuid}`).then((r) => r.data),
    onSuccess: (_data, { docid }) => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['doc-params', docid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
  })
}

export function useDeleteDoc() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (docid) => apiClient.delete(`/docs/${docid}`).then((r) => r.data),
    onSuccess: () => {
      message.success('문서가 삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['docs'] })
    },
    onError: (err) => {
      message.error(err.response?.data?.detail || '삭제에 실패했습니다.')
    },
  })
}
