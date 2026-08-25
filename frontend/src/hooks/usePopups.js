import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'
import { t } from '@/stores/langStore'

// FastAPI 422(Pydantic validation) 에러는 detail이 [{msg, loc, type}, ...] 배열로 온다.
// 그 외(400/404/500)는 detail이 문자열이라 그대로 사용.
function extractErrorMessage(err, fallback) {
  const detail = err.response?.data?.detail
  if (Array.isArray(detail)) return detail.map((d) => d.msg).filter(Boolean).join(' / ') || fallback
  return detail || fallback
}

export function usePopups(mainlogin) {
  return useQuery({
    queryKey: ['popups', mainlogin],
    queryFn: () =>
      apiClient.get('/popups', { params: mainlogin ? { mainlogin } : {} }).then(r => r.data.popups),
    staleTime: 5 * 60 * 1000,
  })
}

export function useDeactivatePopup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (popupid) => apiClient.post(`/popups/${popupid}/deactivate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['popups'] }),
  })
}

// ─── 관리자 CRUD ──────────────────────────────────────────────────────────────

export function useAdminPopups() {
  return useQuery({
    queryKey: ['popups-admin'],
    queryFn: () => apiClient.get('/popups/admin').then((r) => r.data.popups),
  })
}

export function usePopupTranslations(popupid) {
  return useQuery({
    queryKey: ['popup-translations', popupid],
    queryFn: () => apiClient.get(`/popups/${popupid}/translations`).then((r) => r.data.translations),
    enabled: !!popupid,
  })
}

export function useSavePopup() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ isNew, popupid, ...body }) =>
      isNew
        ? apiClient.post('/popups', body).then((r) => r.data)
        : apiClient.put(`/popups/${popupid}`, body).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['popups-admin'] })
      qc.invalidateQueries({ queryKey: ['popups'] })
    },
    onError: (err) => { message.error(extractErrorMessage(err, t('msg.save.error'))) },
  })
}

export function useDeletePopup() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (popupid) => apiClient.delete(`/popups/${popupid}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['popups-admin'] })
      qc.invalidateQueries({ queryKey: ['popups'] })
    },
    onError: (err) => { message.error(extractErrorMessage(err, t('msg.delete.error'))) },
  })
}

export function useSavePopupTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ popupid, languagecd, title, body, button_text }) =>
      apiClient.post(`/popups/${popupid}/translations`, { languagecd, title, body, button_text }).then((r) => r.data),
    onSuccess: (_data, { popupid }) => {
      qc.invalidateQueries({ queryKey: ['popup-translations', popupid] })
      qc.invalidateQueries({ queryKey: ['popups'] })
    },
    onError: (err) => { message.error(extractErrorMessage(err, t('msg.save.error'))) },
  })
}

export function useDeletePopupTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ popupid, languagecd }) =>
      apiClient.delete(`/popups/${popupid}/translations/${languagecd}`).then((r) => r.data),
    onSuccess: (_data, { popupid }) => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['popup-translations', popupid] })
      qc.invalidateQueries({ queryKey: ['popups'] })
    },
    onError: (err) => { message.error(extractErrorMessage(err, t('msg.delete.error'))) },
  })
}
