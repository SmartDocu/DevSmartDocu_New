/**
 * useMfa.js
 * MFA 관련 React Query 훅 모음
 *
 * 필요한 API 함수들은 기존 프로젝트의 api 모듈 구조에 맞게
 * @/api/auth (또는 @/api/mfa) 에 아래 함수들을 추가해주세요:
 *
 *   getMfaFactors()              GET  /auth/mfa-factors
 *   postMfaEnroll()              POST /auth/mfa-enroll
 *   postMfaEnrollVerify(data)    POST /auth/mfa-enroll-verify
 *   deleteMfaUnenroll(data)      DELETE /auth/mfa-unenroll
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { t } from '@/stores/langStore'

// ── API 함수 (기존 프로젝트 api 클라이언트 방식에 맞게 교체하세요) ───────────
import apiClient from '@/api/client'   // axios 인스턴스 등 기존 클라이언트

// refresh_token 가져오는 헬퍼 함수로 분리
const getRefreshToken = () => {
  const auth = JSON.parse(sessionStorage.getItem('smart-doc-auth') ?? '{}')
  return auth?.state?.refreshToken ?? ''
}

const getMfaFactors       = ()       => apiClient.get('/auth/mfa-factors').then((r) => r.data)
const postMfaEnroll       = ()       => //apiClient.post('/auth/mfa-enroll').then((r) => r.data)
{
  const auth = JSON.parse(sessionStorage.getItem('smart-doc-auth') ?? '{}')
  const refresh_token = auth?.state?.refreshToken ?? ''
  console.log('refresh_token:', refresh_token)  // 확인 후 제거
  return apiClient.post('/auth/mfa-enroll', { refresh_token }).then((r) => r.data)
  // const refresh_token = sessionStorage.getItem('refresh_token') ?? ''
  // return apiClient.post('/auth/mfa-enroll', { refresh_token }).then((r) => r.data)
}
const postMfaEnrollVerify = (data)   => apiClient.post('/auth/mfa-enroll-verify', data).then((r) => r.data)
const deleteMfaUnenroll   = (data)   => //apiClient.delete('/auth/mfa-unenroll', { data }).then((r) => r.data)
{
  return apiClient.delete('/auth/mfa-unenroll', {
    data: { ...data, refresh_token: getRefreshToken() },  // ← 추가 (unenroll도 동일 이슈 있을 수 있음)
  }).then((r) => r.data)
}

// ─── 훅 ─────────────────────────────────────────────────────────────────────

/** 현재 사용자의 MFA factor 목록 조회 */
export function useMfaFactors() {
  return useQuery({
    queryKey: ['mfa-factors'],
    queryFn: getMfaFactors,
    staleTime: 30_000,
  })
}

/** MFA 등록 시작 → QR URI / secret 반환 */
export function useMfaEnroll() {
  return useMutation({
    mutationFn: postMfaEnroll,
    onError: () => {
      message.error(t('msg.mfa.enroll_failed'))
    },
  })
}

/** MFA 등록 확인 → verified 상태 전환 */
export function useMfaEnrollVerify() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: postMfaEnrollVerify,
    onSuccess: () => {
      message.success(t('msg.mfa.activated'))
      queryClient.invalidateQueries({ queryKey: ['mfa-factors'] })
    },
    onError: () => {
      message.error(t('msg.mfa.code_invalid'))
    },
  })
}

/** MFA 해제 */
export function useMfaUnenroll() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteMfaUnenroll,
    onSuccess: () => {
      message.success(t('msg.mfa.disabled'))
      queryClient.invalidateQueries({ queryKey: ['mfa-factors'] })
    },
    onError: () => {
      message.error(t('msg.mfa.unenroll_failed'))
    },
  })
}