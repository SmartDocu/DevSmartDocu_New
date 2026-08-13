from d2shared.config import DEFAULT_LLM_MODEL

# 세션별 대화 히스토리(메모리) 관리 - 버퍼 트림 방식
# TARGET_TURNS 초과가 아니라 THRESHOLD_TURNS 초과 시점에만 한 번에 TARGET_TURNS로 자른다.
# (매 턴 슬라이딩 트림 방식은 프롬프트 캐싱의 시작 지점을 매번 흔들어 캐시 히트율을 떨어뜨리므로
# 사용하지 않음 — 2026-08 pr_d2chat에서 이식. d2insight에도 동일한 방식 적용 예정.)
TARGET_TURNS = 15
THRESHOLD_TURNS = 23

__all__ = ['DEFAULT_LLM_MODEL', 'TARGET_TURNS', 'THRESHOLD_TURNS']
