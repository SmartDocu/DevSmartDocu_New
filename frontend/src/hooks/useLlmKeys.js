import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useLlmKeysInit() {
  return useQuery({
    queryKey: ['llmkeys-init'],
    queryFn: () => apiClient.get('/llmkeys/init').then((r) => r.data),
  })
}

export function useLlmKeys() {
  return useQuery({
    queryKey: ['llmkeys'],
    queryFn: () => apiClient.get('/llmkeys').then((r) => r.data),
  })
}

export function useSaveLlmKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/llmkeys', body).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['llmkeys'] })
    },
  })
}

export function useDeleteLlmKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (llmkeyuid) => apiClient.delete(`/llmkeys/${llmkeyuid}`).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['llmkeys'] })
    },
  })
}
