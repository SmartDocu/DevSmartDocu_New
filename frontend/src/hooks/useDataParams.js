import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'
import { t } from '@/stores/langStore'

export function useDataParams(docid) {
  return useQuery({
    queryKey: ['data-params', docid],
    queryFn: () => apiClient.get(`/docs/${docid}/params`).then((r) => r.data.params),
    enabled: !!docid,
  })
}

export function useConditionDatas(docid) {
  return useQuery({
    queryKey: ['condition-datas', docid],
    queryFn: () => apiClient.get(`/docs/${docid}/condition-datas`).then((r) => r.data),
    enabled: !!docid,
  })
}

export function useSaveDataParam() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/docs/params', body).then((r) => r.data),
    onSuccess: (_, body) => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['data-params', String(body.docid)] })
      // 데이터셋 매핑 화면(master/datasets)이 같은 docparams를 doc-params API로 따로 읽는다
      qc.invalidateQueries({ queryKey: ['doc-datasets', String(body.docid)] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.save.error'))
    },
  })
}

export function useDeleteDataParam(docid) {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (paramuid) => apiClient.delete(`/docs/params/${paramuid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['data-params', String(docid)] })
      qc.invalidateQueries({ queryKey: ['doc-datasets', String(docid)] })
    },
    onError: (err) => {
      const detail = err.response?.data?.detail
      message.error(detail ? t(detail) : t('msg.delete.error'))
    },
  })
}
