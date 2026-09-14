import { t } from '@/stores/langStore'

// FastAPI 422(Pydantic 검증 실패)의 detail은 문자열이 아니라 배열이라,
// t(detail)을 그대로 message.error()에 넘기면 React가 plain object를 렌더하려다 크래시한다.
// 항상 이 헬퍼를 거쳐서 detail이 문자열일 때만 번역해서 보여줄 것.
export function getErrorMessage(err, fallbackKey) {
  const detail = err?.response?.data?.detail
  return (typeof detail === 'string' && t(detail)) || t(fallbackKey)
}

// fallback이 번역 키가 아니라 err.message/하드코딩 문자열 등 제각각인 호출부용 —
// detail이 문자열일 때만 번역해서 반환하고, 아니면 null이라 호출부의 기존 `|| fallback` 로직을 그대로 쓸 수 있다.
export function getErrorDetail(err) {
  const detail = err?.response?.data?.detail
  return typeof detail === 'string' ? t(detail) : null
}
