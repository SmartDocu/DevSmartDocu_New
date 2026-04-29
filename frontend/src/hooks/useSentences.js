import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

export function useSentence(chapteruid, objectnm) {
  return useQuery({
    queryKey: ['sentence', chapteruid, objectnm],
    queryFn: () =>
      apiClient.get('/sentences', { params: { chapteruid, objectnm } }).then((r) => r.data.sentence),
    enabled: !!(chapteruid && objectnm),
  })
}

export function useSaveSentence() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body) => apiClient.post('/sentences', body).then((r) => r.data),
    onSuccess: (_data, body) => {
      qc.invalidateQueries({ queryKey: ['sentence', body.chapteruid, body.objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', body.chapteruid] })
    },
  })
}

export function useDeleteSentence() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ chapteruid, objectnm }) =>
      apiClient.delete('/sentences', { params: { chapteruid, objectnm } }).then((r) => r.data),
    onSuccess: (_data, { chapteruid, objectnm }) => {
      qc.invalidateQueries({ queryKey: ['sentence', chapteruid, objectnm] })
      qc.invalidateQueries({ queryKey: ['objects', chapteruid] })
    },
  })
}
