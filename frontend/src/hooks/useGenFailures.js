import { useQuery } from '@tanstack/react-query'
import apiClient from '@/api/client'
import { FRESH_ON_OPEN } from '@/hooks/freshOnOpen'

// 문서/챕터 작성 실패 이력(일반 사용자용) — 소속별 범위는 서버가 정한다. 원문(traceback)은 내려오지 않는다.
export function useMyGenFailures(params) {
  return useQuery({
    queryKey: ['gen-failures', params],
    queryFn: () => apiClient.get('/gen-failures', { params }).then((r) => r.data),
    placeholderData: (prev) => prev,
    ...FRESH_ON_OPEN,
  })
}
