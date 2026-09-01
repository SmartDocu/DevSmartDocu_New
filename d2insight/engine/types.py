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

    # ── 조립 필드 (2026-09-01 카탈로그 재구조화) ──────────────────────────────
    # module_id는 이제 {measure, module_name, sub_name} 세 필드의 조합이다.
    #
    #     {"measure": "amount", "module_name": "ranking", "sub_name": "brand"}
    #
    #   measure     무엇을 분석하는가 (amount/quantity/cost ...)
    #   module_name 어떻게 분석하는가 (= 이 스펙의 module_id)
    #   sub_name    무엇별로 보는가 (item/party/region, 또는 역할이 없는 물리 차원명)
    #
    # 아래 선언은 이 모듈이 그중 무엇을 받는지, 그리고 실행 직전에 **어느 params 키로
    # 펼쳐지는지**를 정한다. 계산 로직(run)은 지금과 똑같이 params만 읽으면 된다 —
    # 조립 표현은 카탈로그·JSON·편집 연산 층에만 있고 실행 층에는 닿지 않는다.
    #
    # 방법론적 변형(by/order 같은 것)은 여기 두지 않는다. 그건 module_id 자체를
    # 나눠서 흡수한다(ranking / decline_ranking).
    sub_name_pool: str | None = None    # None(안 받음) | "dimensions" | "causal_dimensions"
    sub_name_required: bool = False     # sub_name 없이는 실행할 수 없다
    sub_name_param: str = "dimension"   # 펼쳐질 params 키 ("dimension" | "dimensions")
    accepts_measure: bool = False       # measure 필드를 받는가 → params["measure"]

    # 주제(topic) — 스텝-모듈 매트릭스의 근거 (2026-09-01).
    # 스텝도 같은 주제 목록을 갖는다(steps.py). 스텝과 모듈의 주제가 겹치면 그 칸이 O,
    # 안 겹치면 빈칸이다. 어느 쪽이든 "any"면 항상 O.
    #
    # 서로를 나열하지 않는 것이 핵심이다 — 스텝이 늘어도 모듈을 안 고치고, 모듈이 늘어도
    # 스텝을 안 고친다. 새 항목에 자기 주제 한 줄만 적으면 나머지 관계가 저절로 정해진다.
    #
    # 이 매트릭스는 **의미가 맞는가**만 본다. 실행 가능한가(선행 모듈·역할 유무·이름표
    # 충돌)는 planner/options가 실행 시점에 따로 검사한다 — 두 가지를 섞지 않는다.
    topics: list[str] = field(default_factory=lambda: ["any"])
