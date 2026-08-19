"""공유 컨텍스트 — 모듈 간 통신 저장소 (Step 2).

지시서 §5(공유 컨텍스트), §6.2(재계산 금지·summary 전달), §11 Step 2(실패 처리 정책) 구현.

핵심 원칙
  - 모듈끼리 서로의 이름을 직접 참조하지 않는다. 정해진 이름표(key)로만 저장·조회한다.
  - 이름표는 의미 기반·생산자 비의존(§5). 생산 모듈 이름을 넣지 않는다.
  - `requires`는 전부 AND 조건만 지원한다.
  - 공용 수치(기준 기간 값, 전체 증감액 등)는 최초 계산값을 재사용하고 어떤 모듈도 재계산하지 않는다.
    → `put()`은 기존 이름표 덮어쓰기를 기본 거부하고, `get_or_compute()`로 1회만 계산한다.
  - 모듈 실패는 조용히 생략하지 않는다. 기록하고, 의존 후속 모듈은 함께 생략하며 사유를 남긴다.

이 클래스는 이름표에 대해 의미를 모른다(어떤 label이 무엇인지 판단하지 않음). 이름표 네이밍·네임스페이스
결정은 실행 엔진(runner)과 카탈로그의 몫이다. 컨텍스트는 순수 저장소·기록소로만 동작한다.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable


class ContextError(Exception):
    """공유 컨텍스트 사용 규약 위반 (예: 공용 이름표 재계산 시도)."""


class SharedContext:
    """세션 단위 공용 저장소.

    저장 대상은 세 갈래다.
      1. 이름표 값(_store)   — 모듈이 produces로 넣고 다른 모듈이 requires로 꺼내 씀
      2. 요약 문장(_summaries) — 결론 스텝이 모두 모아 읽음(§6.2)
      3. 실패/생략 기록(_notes) — 결론에 "OO 분석은 [사유]로 생략됨" 명시(§11 Step 2)
    """

    def __init__(self, session_id: str | None = None, meta: dict | None = None) -> None:
        self.session_id = session_id
        self.meta = meta or {}                 # 기준월·비교유형 등 세션 공통 정보(읽기 참고용)
        self._store: dict[str, Any] = {}
        self._summaries: list[dict] = []
        self._notes: list[dict] = []           # {"ref", "reason", "kind": "failed"|"skipped"}

    # ── 이름표 값 저장·조회 ────────────────────────────────────────────────
    def put(self, label: str, value: Any, *, overwrite: bool = False) -> None:
        """이름표에 값을 저장한다.

        공용 수치 재계산 금지(§6.2)를 위해 이미 존재하는 이름표는 기본적으로 덮어쓰지 않는다.
        의도적으로 갱신해야 하면 overwrite=True를 명시한다(권장하지 않음).
        같은 모듈을 파라미터만 달리해 여러 번 실행하는 경우(§3.4-2)는 runner가 서로 다른
        이름표를 부여하므로 여기서 충돌하지 않는다.
        """
        if label in self._store and not overwrite:
            raise ContextError(
                f"이름표 '{label}'가 이미 존재합니다. 공용 수치는 재계산·재저장하지 않습니다"
                f"(§6.2). 갱신이 필요하면 overwrite=True를 명시하세요."
            )
        self._store[label] = value

    def get(self, label: str, default: Any = None) -> Any:
        return self._store.get(label, default)

    def has(self, label: str) -> bool:
        return label in self._store

    def available_labels(self) -> set[str]:
        return set(self._store.keys())

    def get_or_compute(self, label: str, compute_fn: Callable[[], Any]) -> Any:
        """공용 수치 최초 1회 계산 후 재사용(재계산 금지 §6.2).

        이름표가 있으면 저장값을 그대로 돌려주고, 없으면 compute_fn()으로 계산해 저장한 뒤 반환한다.
        """
        if label in self._store:
            return self._store[label]
        value = compute_fn()
        self._store[label] = value
        return value

    # ── requires(선행 이름표) 점검 ─────────────────────────────────────────
    def missing_requires(self, requires: Iterable[str]) -> list[str]:
        """아직 존재하지 않는 선행 이름표 목록(AND 조건). 비어 있으면 실행 가능."""
        return [label for label in (requires or []) if label not in self._store]

    def requires_satisfied(self, requires: Iterable[str]) -> bool:
        return not self.missing_requires(requires)

    # ── 요약 문장 수집 (결론용, §6.2) ──────────────────────────────────────
    def add_summary(self, ref: str, text: str) -> None:
        """모듈이 만든 1~2줄 요약을 결론용으로 모은다. ref는 스텝/모듈 식별 표시."""
        if text:
            self._summaries.append({"ref": ref, "text": text})

    def all_summaries(self) -> list[dict]:
        return list(self._summaries)

    # ── 실패/생략 기록 (§11 Step 2) ────────────────────────────────────────
    def mark_failed(self, ref: str, reason: str) -> None:
        """모듈 실행 실패를 기록한다(조용히 생략 금지). produces 이름표는 저장되지 않는다."""
        self._notes.append({"ref": ref, "reason": reason, "kind": "failed"})

    def mark_skipped(self, ref: str, reason: str) -> None:
        """선행 모듈 실패 등으로 실행하지 못한 모듈을 기록한다."""
        self._notes.append({"ref": ref, "reason": reason, "kind": "skipped"})

    def notes(self) -> list[dict]:
        """결론 스텝이 "OO 분석은 [사유]로 생략됨"을 명시할 때 참조하는 실패/생략 기록."""
        return list(self._notes)

    def has_notes(self) -> bool:
        return bool(self._notes)
