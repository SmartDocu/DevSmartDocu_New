import { useQuery, useMutation } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { useAuthStore } from '@/stores/authStore'

export function useLanguages() {
  return useQuery({
    queryKey: ['i18n', 'languages'],
    queryFn: () => apiClient.get('/i18n/languages').then((r) => r.data.languages),
    staleTime: Infinity,
  })
}

export function useTranslations(langCd) {
  return useQuery({
    queryKey: ['i18n', 'translations', langCd],
    queryFn: () => apiClient.get(`/i18n/translations/${langCd}`).then((r) => r.data),
    enabled: !!langCd,
    staleTime: Infinity,
  })
}

export function useSetLanguage() {
  const { isAuthenticated } = useAuthStore()
  return useMutation({
    mutationFn: (languagecd) => {
      if (!isAuthenticated()) return Promise.resolve()
      return apiClient.patch('/auth/language', { languagecd })
    },
  })
}
