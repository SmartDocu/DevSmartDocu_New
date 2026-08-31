"""카탈로그 → 외부(사람이 읽는 목록·UI·LLM) 노출용 JSON (1단계, 2026-07-24).

이전엔 시나리오·스텝·모듈·툴 카탈로그가 파이썬 dict 안에만 있어 "무엇을 고를 수 있는지"
목록을 외부로 낼 통로가 없었다(계획_2026-07-24_상세.md G4). 여기서 하나의 JSON으로
직렬화한다 — 사람이 읽는 라벨(label)·입력 위젯(widget)·값 범위(min/max)·툴 선택이 바꾸는
것(effect)까지 담아 "이 응답을 그대로 UI가 읽을 수 있다"를 목표로 한다.

**카탈로그 JSON(이 파일) vs 옵션 JSON(options.py)은 서로 다른 것이다** — 헷갈리지 않는다.
  - 카탈로그 JSON: 무엇을 고를 수 있는가 (앱 → 사용자/UI/LLM, 읽기 전용)
  - 옵션 JSON:     무엇을 골랐는가       (사용자/UI/LLM → 앱, 실행 입력)

이 파일은 레지스트리를 조회해 직렬화만 한다 — 레지스트리 자체를 바꾸지 않는다.
"""
from __future__ import annotations

from d2insight.engine.catalog.modules import get_module_registry
from d2insight.engine.catalog.scenarios import SCENARIO_REGISTRY
from d2insight.engine.catalog.steps import get_step_registry
from d2insight.engine.catalog.tools import get_tool_registry
from d2insight.engine.datasource import DEFAULT_SOURCE_ID, build_meta_columns
from d2insight.engine.schema import (
    ROLE_AMOUNT, ROLE_COST, ROLE_DISCOUNT, ROLE_INBOUND, ROLE_INVENTORY,
    ROLE_ITEM, ROLE_ITEM_GROUP, ROLE_OPEX, ROLE_OUTBOUND, ROLE_PARTY,
    ROLE_QUANTITY, ROLE_SAFETY_STOCK, Schema,
)

# 파라미터 이름 → UI 메타(사람이 읽는 라벨·입력 위젯·값 범위). `옵션_카탈로그.md §4`를 코드로
# 옮긴 것 — 모듈마다 따로 정의하지 않고 이름으로 공유한다(같은 이름은 여러 모듈에서 같은 뜻이므로).
_PARAM_UI: dict[str, dict] = {
    "dimension":       {"label": "분석 차원", "widget": "select"},
    "dimensions":       {"label": "분석 차원(복수)", "widget": "multiselect"},
    "measure":         {"label": "측정값", "widget": "select"},
    "measures":         {"label": "측정값(복수)", "widget": "multiselect"},
    "top_n":           {"label": "상위 개수", "widget": "number", "min": 1, "max": 100},
    "cross_top_n":      {"label": "교차 상위 개수", "widget": "number", "min": 1, "max": 100},
    "sigma":           {"label": "민감도(σ)", "widget": "slider", "min": 1.0, "max": 4.0},
    "order":           {"label": "정렬 방향", "widget": "toggle", "choices": ["desc", "asc"]},
    "by":              {"label": "정렬 기준", "widget": "toggle", "choices": ["actual", "variance"]},
    "window_months":    {"label": "이력 창(개월)", "widget": "number", "min": 1},
    "slow_days":        {"label": "장기체화 기준일수", "widget": "number", "min": 0},
    "target":          {"label": "목표값", "widget": "number"},
    "exclude_dormant":  {"label": "일시미구매 제외", "widget": "checkbox"},
    "rate":            {"label": "증감률 임계", "widget": "number", "min": 0.0, "max": 1.0},
    "compare_type":     {"label": "비교 기준", "widget": "toggle", "choices": ["MoM", "YoY", "QoQ"]},
    "months_back":      {"label": "이력 개월수", "widget": "number", "min": 1},
    "grain":           {"label": "기간 단위", "widget": "toggle",
                        "choices": ["month", "quarter", "year", "week"]},
    "plan_source":      {"label": "계획 데이터 소스", "widget": "text"},
}

# 실제로 결과의 "의미"가 달라지는 툴 선택지만 effect를 채운다(dimension_impact·anomaly_detection·
# volume_effect·price_effect·kpi_alert — 5개 모듈). 나머지는 이름표 하나뿐인 단일 방식이라
# effect가 없다 — 없다는 사실 자체가 "고를 게 없다"는 신호다(옵션_카탈로그.md §6-3).
_TOOL_EFFECT: dict[str, str] = {
    "pvm": (
        "두 기간 모두 판매된 항목만 대상으로 비교월 단가를 고정해 물량 변화만 본다. "
        "신규·단종 항목은 빠진다 — 합이 전체 증감액과 정확히 맞지 않을 수 있다."
    ),
    "bridge_decompose": (
        "신규·단종·복귀까지 전부 포함해 항목별로 계산한 뒤 합산한다. "
        "합이 전체 증감액과 정확히 일치한다(검산 통과)."
    ),
    "shapley": (
        "차원별 기여도를 게임이론(Shapley Value) 방식으로 배분한다. "
        "계산 비용이 더 크지만 차원 간 상호작용을 반영한다."
    ),
    "dvi": "DVI = Impact × HHI × 평균Z. 영향 크기에 집중도(소수 항목 쏠림)까지 곱해 종합 순위를 매긴다.",
    "z_score": "평균·표준편차 기준 이상치 점수. 정규분포를 가정하며 극단값에 민감하다.",
    "iqr": "사분위 범위(IQR) 기준 이상치 점수. 극단값에 덜 흔들려 분포가 치우친 데이터에 안정적이다.",
    "mad": "중앙값 절대편차(MAD) 기준 이상치 점수. 세 방식 중 극단값에 가장 강건하다.",
    "attainment": (
        "계획/목표 대비 달성률 기준 판정. 계획 데이터가 있어야 하며, "
        "현재 데이터소스엔 없어 보류 상태다."
    ),
    "history_z": (
        "이 measure의 과거 이력(분석월 제외) 평균·σ 대비 이탈 정도로 판정한다 — "
        "같은 달 다른 항목이 아니라 같은 지표의 과거와 비교하는 시계열 판정."
    ),
    "threshold": "고정 증감률(%) 초과 여부로 판정한다. 이력이 짧아 σ를 못 낼 때의 보조 잣대.",
}

# 시나리오 한글 이름 → 짧은 영문 키. JSON 키·URL에 쓰기 위함 — 한글 이름은 띄어쓰기 불일치로
# 이미 한 번 사고가 났다("매출증감원인분석" vs "매출 증감 원인 분석", 작업정리_2026-07-22.md).
_SCENARIO_ID: dict[str, str] = {
    "매출 증감 원인 분석": "s1_revenue_variance_cause",
    "KPI Executive Summary": "s2_kpi_executive_summary",
    "고객 분석": "s3_customer",
    "제품 분석": "s4_product",
    "손익 분석": "s5_pnl",
    "재고 분석": "s6_inventory",
    "판매분석": "legacy_sales",
}

# 데이터소스가 선언했을 수 있는 전체 역할 — 실제로 declared된 것만 골라 노출한다.
_ALL_ROLES = [
    ROLE_AMOUNT, ROLE_QUANTITY, ROLE_DISCOUNT, ROLE_COST, ROLE_OPEX,
    ROLE_INVENTORY, ROLE_INBOUND, ROLE_OUTBOUND, ROLE_SAFETY_STOCK,
    ROLE_ITEM, ROLE_PARTY, ROLE_ITEM_GROUP,
]


def _scenario_id(name: str) -> str:
    return _SCENARIO_ID.get(name, name)


def _module_json(module_id: str, spec) -> dict:
    params = []
    for name, field in (spec.params or {}).items():
        ui = _PARAM_UI.get(name, {})
        entry = {
            "name": name,
            "type": field.get("type", "str"),
            "required": bool(field.get("required")),
            "default": field.get("default"),
            "label": ui.get("label", name),
            "widget": ui.get("widget", "text"),
        }
        for k in ("min", "max", "choices"):
            if k in ui:
                entry[k] = ui[k]
        params.append(entry)

    available = spec.tools.get("available") or []
    tools: dict = {"available": available, "default": spec.tools.get("default")}
    # 선택지가 2개 이상일 때만 effect를 채운다 — 툴이 하나뿐이면 이름이 우연히
    # _TOOL_EFFECT 사전에 있어도 선택이 있는 것처럼 보이면 안 된다.
    if len(available) > 1:
        effect = {t: _TOOL_EFFECT[t] for t in available if t in _TOOL_EFFECT}
        if effect:
            tools["effect"] = effect

    return {
        "module_id": module_id,
        "kind": spec.kind,
        "purpose": spec.purpose,
        "requires": list(spec.requires),
        "produces": list(spec.produces),
        # produces가 비어 있으면(리프) 같은 계획에 여러 번 배치해도 이름표 충돌이 없다(§3.4-2).
        "repeatable": not spec.produces,
        "params": params,
        "tools": tools,
        "model_tier": spec.model_tier,
    }


def _step_json(step_id: str, preset: dict, modules: dict) -> dict:
    modules_out = []
    for m in preset["default_modules"]:
        mid = m["module_id"]
        spec = modules[mid]
        # 스펙 기본값 위에 프리셋이 지정한 값을 얹은 실제 적용값(chat_options.
        # default_steps_for_scenario와 같은 원칙 — 빈 채로 두지 않는다).
        params = {name: field.get("default") for name, field in spec.params.items()}
        params.update(m.get("params") or {})
        tool = m.get("tools", [None])[0] if m.get("tools") else spec.tools.get("default")
        modules_out.append({"module_id": mid, "params": params, "tool": tool})
    return {"step_id": step_id, "title": preset["title"], "default_modules": modules_out}


def build_catalog(source_id: str = DEFAULT_SOURCE_ID) -> dict:
    """카탈로그 전체를 하나의 JSON으로 직렬화한다 — "무엇을 고를 수 있는지" 전체 목록.

    UI 화면 없이도 이 응답 하나가 곧 옵션_카탈로그.md의 코드판이다.
    """
    schema = Schema(build_meta_columns(source_id))
    modules = get_module_registry()
    steps = get_step_registry()

    return {
        "version": "2026-07-24",
        "datasource": {
            "id": source_id,
            "dimensions": schema.dimensions,
            "measures": schema.measures,
            "key_measure": schema.key_measure,
            "roles": {role: schema.column(role) for role in _ALL_ROLES if schema.column(role)},
        },
        "scenarios": [
            {
                "scenario_id": _scenario_id(name),
                "name": name,
                "report_title": base["report_title"],
                "steps": [s["step_id"] for s in base["steps"]],
            }
            for name, base in SCENARIO_REGISTRY.items()
        ],
        "steps": [_step_json(sid, preset, modules) for sid, preset in steps.items()],
        "modules": [_module_json(mid, spec) for mid, spec in modules.items()],
        "tools": get_tool_registry(),
    }
