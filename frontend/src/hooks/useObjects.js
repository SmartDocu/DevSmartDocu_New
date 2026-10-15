import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import { t } from '@/stores/langStore'
import apiClient from '@/api/client'
import { getErrorMessage } from '@/utils/apiError'
import { FRESH_ON_OPEN } from '@/hooks/freshOnOpen'

export function useObjects(chapteruid) {
  return useQuery({
    queryKey: ['objects', chapteruid],
    queryFn: () => apiClient.get('/objects', { params: { chapteruid } }).then((r) => r.data.objects),
    enabled: !!chapteruid,
    // 항목은 챕터 템플릿 화면에서도 추가·삭제된다 — 열 때마다 새로 읽어 낡은 목록을 보여주지 않는다.
    ...FRESH_ON_OPEN,
  })
}

export function useSaveObject() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (body) => apiClient.post('/objects', body).then((r) => r.data),
    onSuccess: (_data, body) => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['objects', body.chapteruid] })
    },
    onError: (err) => {
      message.error(getErrorMessage(err, 'msg.save.error'))
    },
  })
}

export function useDeleteObject() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ objectuid, chapteruid }) =>
      apiClient.delete(`/objects/${objectuid}`).then((r) => r.data),
    onSuccess: (_data, { chapteruid }) => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['objects', chapteruid] })
    },
    onError: (err) => {
      message.error(getErrorMessage(err, 'msg.delete.error'))
    },
  })
}
