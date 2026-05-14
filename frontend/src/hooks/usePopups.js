import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import apiClient from '@/api/client'

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
