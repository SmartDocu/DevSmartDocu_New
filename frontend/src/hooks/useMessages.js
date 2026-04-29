import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import apiClient from '@/api/client'
import { t } from '@/stores/langStore'

export function useAdminMessages() {
  return useQuery({
    queryKey: ['messages-admin'],
    queryFn: () => apiClient.get('/messages').then((r) => r.data.messages),
  })
}

export function useMessageTranslations(messagekey) {
  return useQuery({
    queryKey: ['message-translations', messagekey],
    queryFn: () => apiClient.get(`/messages/${messagekey}/translations`).then((r) => r.data.translations),
    enabled: !!messagekey,
  })
}

export function useSaveMessage() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ isNew, messagekey, ...body }) =>
      isNew
        ? apiClient.post('/messages', { messagekey, ...body }).then((r) => r.data)
        : apiClient.put(`/messages/${messagekey}`, { messagekey, ...body }).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.save.success'))
      qc.invalidateQueries({ queryKey: ['messages-admin'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.save.error')),
  })
}

export function useDeleteMessage() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: (messagekey) => apiClient.delete(`/messages/${messagekey}`).then((r) => r.data),
    onSuccess: () => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['messages-admin'] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}

export function useSaveMessageTranslation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ messagekey, languagecd, translated_text }) =>
      apiClient.post(`/messages/${messagekey}/translations`, { languagecd, translated_text }).then((r) => r.data),
    onSuccess: (_data, { messagekey }) => {
      qc.invalidateQueries({ queryKey: ['message-translations', messagekey] })
    },
  })
}

export function useDeleteMessageTranslation() {
  const qc = useQueryClient()
  const { message } = App.useApp()
  return useMutation({
    mutationFn: ({ messagekey, languagecd }) =>
      apiClient.delete(`/messages/${messagekey}/translations/${languagecd}`).then((r) => r.data),
    onSuccess: (_data, { messagekey }) => {
      message.success(t('msg.delete.success'))
      qc.invalidateQueries({ queryKey: ['message-translations', messagekey] })
    },
    onError: (err) => message.error(err.response?.data?.detail || t('msg.delete.error')),
  })
}
