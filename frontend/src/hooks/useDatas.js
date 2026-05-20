import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { t } from '@/stores/langStore'
import apiClient from '@/api/client'

export function useAllDatas() {
  return useQuery({
    queryKey: ['datas', 'all'],
    queryFn: () => apiClient.get('/datas').then((r) => r.data.datas),
  })
}

export function useChapterDatas(chapteruid) {
  return useQuery({
    queryKey: ['datas', 'chapter', chapteruid],
    queryFn: () =>
      apiClient.get('/datas', { params: { chapteruid } }).then((r) => {
        const datas = r.data?.datas
        return Array.isArray(datas) ? datas : []
      }),
    enabled: !!chapteruid,
    retry: 1,
  })
}

export function useDatasProjects() {
  return useQuery({
    queryKey: ['datas-projects'],
    queryFn: () => apiClient.get('/datas/projects').then((r) => r.data.projects),
  })
}

export function useDatasDb() {
  return useQuery({
    queryKey: ['datas', 'db'],
    queryFn: () => apiClient.get('/datas', { params: { datasourcecd: 'db' } }).then((r) => r.data.datas),
  })
}

export function useDatasEx() {
  return useQuery({
    queryKey: ['datas', 'ex'],
    queryFn: () => apiClient.get('/datas', { params: { datasourcecd: 'ex' } }).then((r) => r.data.datas),
  })
}

export function useDatasAi() {
  return useQuery({
    queryKey: ['datas', 'df'],
    queryFn: () => apiClient.get('/datas', { params: { datasourcecd: 'df' } }).then((r) => r.data.datas),
  })
}

export function useDatasSource() {
  return useQuery({
    queryKey: ['datas', 'source'],
    queryFn: () => apiClient.get('/datas/source').then((r) => r.data.datas),
  })
}

export function useDbConnectors() {
  return useQuery({
    queryKey: ['dbconnectors'],
    queryFn: () => apiClient.get('/datas/dbconnectors').then((r) => r.data.connectors),
  })
}

export function useDatacols(datauid) {
  return useQuery({
    queryKey: ['datacols', datauid],
    queryFn: () => apiClient.get('/datas/datacols', { params: { datauid } }).then((r) => r.data.columns),
    enabled: !!datauid,
  })
}

export function useSaveDbData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/datas/db', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['datas', 'db'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useSaveExData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (formData) =>
      apiClient.post('/datas/ex', formData, { headers: { 'Content-Type': 'multipart/form-data' } }).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['datas', 'ex'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useSaveAiData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/datas/ai', body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['datas', 'df'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteData(datasourcecd) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (datauid) => apiClient.delete(`/datas/${datauid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      if (datasourcecd) qc.invalidateQueries({ queryKey: ['datas', datasourcecd] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

export function useCreateDatacols() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/datas/datacols/create', body).then((r) => r.data),
    onSuccess: (_data, body) => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['datacols', body.datauid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useSaveDatacols() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (cols) => apiClient.post('/datas/datacols', cols).then((r) => r.data),
    onSuccess: (_data, cols) => {
      message.success(t('msg.save.success'))
      if (cols.length > 0) qc.invalidateQueries({ queryKey: ['datacols', cols[0].datauid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDfDatas(docid) {
  return useQuery({
    queryKey: ['datas', 'df-list', docid],
    queryFn: () => apiClient.get('/datas/df-list', { params: { docid } }).then((r) => r.data.datas),
    enabled: !!docid,
  })
}

export function useSaveDfData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/datas/df', body).then((r) => r.data),
    onSuccess: (_, body) => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['datas', 'df-list', body.docid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useSaveDfvData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/datas/dfv', body).then((r) => r.data),
    onSuccess: (_, body) => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['datas', 'df-list', body.dfv_docid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useAiDataPreview() {
  return useMutation({
    mutationFn: (body) => apiClient.post('/datas/ai-preview', body).then((r) => r.data),
    onError: (err) => message.error(err.response?.data?.detail || t('msg.preview.error')),
  })
}

export function useDeleteDfData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ datauid }) => apiClient.delete(`/datas/${datauid}`).then((r) => r.data),
    onSuccess: (_, { docid }) => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['datas', 'df-list', docid] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}
