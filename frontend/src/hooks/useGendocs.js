import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'

export function useGendocs(startDate, endDate) {
  return useQuery({
    queryKey: ['gendocs', startDate, endDate],
    queryFn: () =>
      apiClient.get('/gendocs', { params: { start_date: startDate, end_date: endDate } }).then((r) => r.data),
  })
}

export function useDataparams() {
  return useQuery({
    queryKey: ['gendocs-dataparams'],
    queryFn: () => apiClient.get('/gendocs/dataparams').then((r) => r.data),
  })
}

export function useGendocStatus(gendocuid) {
  return useQuery({
    queryKey: ['gendoc-status', gendocuid],
    queryFn: () => apiClient.get(`/gendocs/${gendocuid}/status`).then((r) => r.data),
    enabled: !!gendocuid,
  })
}

export function useGenchapters(gendocuid) {
  return useQuery({
    queryKey: ['genchapters', gendocuid],
    queryFn: () => apiClient.get(`/gendocs/${gendocuid}/chapters`).then((r) => r.data),
    enabled: !!gendocuid,
    refetchInterval: (data) => {
      // Auto-refetch if chapters are still generating
      const chapters = data?.chapters || []
      const pending = chapters.some((c) => !c.createfiledts)
      return pending ? 3000 : false
    },
  })
}

export function useCreateGendoc() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/gendocs', body).then((r) => r.data),
    onSuccess: () => {
      message.success('문서가 생성되었습니다.')
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '생성에 실패했습니다.'),
  })
}

export function useDeleteGendoc() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (gendocuid) => apiClient.delete(`/gendocs/${gendocuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success('삭제되었습니다.')
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '삭제에 실패했습니다.'),
  })
}

export function useUpdateGendocParams() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/gendocs/params/update', body).then((r) => r.data),
    onSuccess: () => {
      message.success('파라미터가 변경되었습니다.')
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || '변경에 실패했습니다.'),
  })
}
