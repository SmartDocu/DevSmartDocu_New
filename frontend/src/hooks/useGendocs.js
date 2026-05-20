import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import { t } from '@/stores/langStore'
import apiClient from '@/api/client'

export function useGendocs(startDate, endDate, docid) {
  return useQuery({
    queryKey: ['gendocs', startDate, endDate, docid],
    queryFn: () =>
      apiClient.get('/gendocs', { params: { start_date: startDate, end_date: endDate, docid } }).then((r) => r.data),
    enabled: !!docid,
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
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteGendoc() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (gendocuid) => apiClient.delete(`/gendocs/${gendocuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

export function useUpdateGendocParams() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/gendocs/params/update', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useCloseGendoc() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (gendocuid) => apiClient.post(`/gendocs/${gendocuid}/close`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.gendoc.closed'))
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useOpenGendoc() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (gendocuid) => apiClient.post(`/gendocs/${gendocuid}/open`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.gendoc.opened'))
      qc.invalidateQueries({ queryKey: ['gendocs'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}
