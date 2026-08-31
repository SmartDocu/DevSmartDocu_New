"""엔진 공통 자료구조 — 모듈 출력 계약과 모듈 명세 (Step 3).

`documents/module_catalog_schema.md` §4(표준 출력 계약)의 파이썬 표현.
모듈 결과는 두 갈래로 분리한다.
  - outputs : 공유 컨텍스트에 저장(produces 이름표 → 값). 다른 모듈이 requires로 꺼내 씀.
  - render  : 보고서에 렌더(table/chart/summary/key_value). summary는 필수.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# 본문 블록 배치 기본 순서 (§7.1, 결정 2026-07-14). 모듈·계획이 자유롭게 바꿀 수 있다.
DEFAULT_LAYOUT: list[str] = ["narrative", "key_value", "table", "chart"]


@dataclass
class Render:
    """보고서에 렌더되는 모듈 산출물 (§7.1).

    summary와 narrative는 독자가 다르다(결정 2026-07-14).
      - summary   : 결론 LLM이 읽는 1~2줄. **본문에 출력하지 않고 보관만 한다.**
      - narrative : 사람이 읽는 해설 문단. 표/차트를 근거로 스텝 해설자가 LLM으로 쓴다.
                    모듈은 이 값을 비워 두고, 엔진의 해설 단계가 채운다.
    """
    summary: str                              # 필수 — 결론 전용 (본문 미출력)
    table: Any = None                         # DataFrame 등 (기본 생성)
    table_note: Optional[str] = None          # 표 캡션(예: "단위: 백만원") — table 바로 위에 출력
    llm_spec: Optional[dict] = None           # _llm_render가 고른 표열/차트/서술 명세(정기 보고서 캐싱용)
    chart: Any = None                         # 차트 스펙/이미지 (기본 생성)
    key_value: Optional[dict] = None          # 단일 수치/키-값 (선택)
    narrative: Optional[str] = None           # 본문 해설 (해설 단계에서 채움)
    layout: Optional[list[str]] = None        # 블록 배치 순서(미지정 시 모듈 명세 → 기본값)


@dataclass
class ModuleResult:
    """모듈 1회 실행 결과."""
    outputs: dict[str, Any] = field(default_factory=dict)   # produces 이름표 → 값
    render: Optional[Render] = None
    status: str = "ok"                        # ok | failed
    error: Optional[str] = None


# 모듈 실행 함수 시그니처: (ctx, params, tools) -> ModuleResult
ModuleRun = Callable[..., ModuleResult]


@dataclass
class ModuleSpec:
    """Module Registry 한 항목 + 실행 함수(run).

    메타데이터(purpose/kind/requires/produces/params/tools/model_tier)는 카탈로그 스키마 §2와 동일.
    run은 모듈의 구체 구현으로, 실제 모듈은 src/engine/modules/ 하위에 두고 여기에 등록한다(Step 4).
    """
    module_id: str
    run: ModuleRun
    purpose: str = ""
    kind: str = "analysis"                    # aggregate | analysis (탐색용 분류, 실행 분기 아님)
    requires: list[str] = field(default_factory=list)   # AND only
    produces: list[str] = field(default_factory=list)
    params: dict = field(default_factory=dict)
    tools: dict = field(default_factory=dict)           # {"available":[...], "default":...}
    model_tier: str = "balanced"                        # 이 모듈 해설을 쓸 LLM 등급
    narrative_hint: str = ""                            # 해설자에게 주는 모듈별 서술 지침(선택)
    layout: list[str] = field(default_factory=lambda: list(DEFAULT_LAYOUT))
    # dimension/measure 파라미터로 드러나지 않는, 모듈 내부에서만 쓰는 역할(예: party).
    # 계획 단계에서 이 역할이 schema에 없으면 모듈을 건너뛴다(dimension 파라미터와 같은 원칙).
    required_roles: list[str] = field(default_factory=list)
