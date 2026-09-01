"""module_id 조합 — {measure, module_name, sub_name} ↔ 정규 문자열 (2026-09-01).

module_id는 더 이상 문자열 하나가 아니라 **세 필드의 조합**이다.

    {"measure": "amount", "module_name": "ranking", "sub_name": "brand"}
        ↕
    "amount:ranking@brand"

왜 둘 다 필요한가 — dict는 dict의 키가 될 수 없다. 그래서 각자 잘하는 자리를 나눈다.

  dict   : JSON, 편집 연산. 필드 하나만 갈아끼우기 쉽다 —
           "top_제품을 top_브랜드로"가 sub_name 교체 한 번이 된다.
  문자열 : 로그, 에러 메시지, 스텝 안 유일성 판정, produces 이름표의 조합 단위.
           짧고 사람이 읽을 수 있다.

**MODULE_REGISTRY는 module_name으로만 조회한다.** 조합마다 스펙을 따로 등록하지
않는다 — `ranking` 스펙 하나가 measure·sub_name을 받는다고 선언할 뿐이다
(ModuleSpec.sub_name_pool / accepts_measure). 그래서 데이터소스마다 차원이 달라도
카탈로그는 고정으로 남는다.

표기 규칙 (measure와 sub_name은 없을 수 있다):

    conclusion                  둘 다 없음
    ranking@item                sub_name만
    amount:ranking              measure만
    amount:ranking@Brand        둘 다
"""
from __future__ import annotations

_MEASURE_SEP = ":"
_SUB_SEP = "@"


class ModuleKeyError(ValueError):
    """module_id 조합이 형식에 맞지 않을 때 — 조용히 보정하지 않는다."""


def to_key(module: dict) -> str:
    """{measure, module_name, sub_name} → 정규 문자열.

    `module_name`은 반드시 있어야 한다. 나머지 둘은 None이면 자리를 비운다.
    """
    name = (module or {}).get("module_name")
    if not name:
        raise ModuleKeyError(f"module_name이 없습니다: {module!r}")
    measure = module.get("measure")
    sub_name = module.get("sub_name")
    key = f"{measure}{_MEASURE_SEP}{name}" if measure else str(name)
    if sub_name:
        key = f"{key}{_SUB_SEP}{sub_name}"
    return key


def from_key(key: str) -> dict:
    """정규 문자열 → {measure, module_name, sub_name}. to_key의 역이다."""
    if not key or not isinstance(key, str):
        raise ModuleKeyError(f"module_id 문자열이 아닙니다: {key!r}")
    rest, _, sub_name = key.partition(_SUB_SEP)
    measure, _, name = rest.partition(_MEASURE_SEP)
    if not name:                      # 구분자가 없었다 — rest 전체가 module_name
        measure, name = "", rest
    if not name:
        raise ModuleKeyError(f"module_name을 읽지 못했습니다: {key!r}")
    return {
        "measure": measure or None,
        "module_name": name,
        "sub_name": sub_name or None,
    }


def normalize(module: dict | str) -> dict:
    """dict든 문자열이든 받아 dict로 맞춘다.

    옛 형태(`{"module_id": "ranking", ...}`)도 받아준다 — 저장된 보고서를 다시 열거나
    LLM이 옛 형태로 답했을 때 여기서 한 번에 흡수한다.
    """
    if isinstance(module, str):
        return from_key(module)
    if not isinstance(module, dict):
        raise ModuleKeyError(f"module을 읽지 못했습니다: {module!r}")
    if module.get("module_name"):
        return {
            "measure": module.get("measure") or None,
            "module_name": module["module_name"],
            "sub_name": module.get("sub_name") or None,
        }
    legacy = module.get("module_id")
    if isinstance(legacy, dict):
        return normalize(legacy)
    if legacy:
        return from_key(legacy)
    raise ModuleKeyError(f"module_name도 module_id도 없습니다: {module!r}")


def label(module: dict | str) -> str:
    """사람이 읽을 로그·에러 메시지용 표기. normalize를 거쳐 항상 정규 문자열을 낸다."""
    return to_key(normalize(module))


def to_execution_entry(module: dict | str) -> dict:
    """조립 표현 → 실행 표현. **조립 필드는 지우지 않고 함께 남긴다.**

        {"module_name": "ranking", "sub_name": "item"}
            ↓
        {"module_name": "ranking", "sub_name": "item", "measure": None,
         "module_id": "ranking", "params": {"dimension": "item", ...}}

    왜 둘 다 남기나 — entry.py가 `applied_steps = plan["steps"]`로 두어, 사용자가 보고
    편집하는 JSON이 곧 실행 계획이다(미리보기와 실제 실행이 어긋날 수 없게 한 장치).
    조립 필드를 실행 표현으로 **대체**해 버리면 오른쪽 패널이 모듈을 이름으로 지목할 수
    없어진다. 그래서 더한다.

    두 값이 겹치지도 않는다 — `sub_name`은 역할("item")이고 `params["dimension"]`은 나중에
    실제 물리 컬럼명("ProductName")으로 해석된다. JSON에 요청한 것과 해석된 것이 같이 남아
    오히려 읽기 좋다.

    `module_id`는 `module_name`과 같은 값이다 — MODULE_REGISTRY가 module_name으로 키를
    잡으므로, 레지스트리를 조회하는 기존 코드(planner/options/runner)가 그대로 동작한다.
    """
    from d2insight.engine.catalog.modules import get_module_registry

    parts = normalize(module)
    name = parts["module_name"]
    source = module if isinstance(module, dict) else {}
    params = dict(source.get("params") or {})

    spec = get_module_registry().get(name)
    if spec is not None:
        if spec.sub_name_pool:
            if parts["sub_name"]:
                # 리스트 파라미터를 읽는 모듈(abc_classification 등)은 감싸서 넣는다.
                params[spec.sub_name_param] = (
                    [parts["sub_name"]] if spec.sub_name_param == "dimensions"
                    else parts["sub_name"]
                )
            else:
                # 대상을 비웠으면(= "알아서 골라라") 예전 값을 지운다. 안 지우면 편집으로
                # 비운 뒤에도 옛 차원이 params에 남아 그대로 실행된다.
                params.pop(spec.sub_name_param, None)
        if spec.accepts_measure:
            if parts["measure"]:
                params["measure"] = parts["measure"]
            else:
                params.pop("measure", None)

    entry = {k: v for k, v in source.items() if k not in ("module_id", "params")}
    entry.update(parts)
    entry["module_id"] = name
    entry["params"] = params
    return entry


def check_required(module: dict | str) -> str | None:
    """sub_name이 필수인데 없으면 사유 문자열을, 문제 없으면 None을 돌려준다.

    조용히 기본값으로 때우지 않는다 — 호출부가 notes에 남기거나 모듈을 건너뛴다.
    """
    from d2insight.engine.catalog.modules import get_module_registry

    parts = normalize(module)
    spec = get_module_registry().get(parts["module_name"])
    if spec is None:
        return None                       # 알 수 없는 모듈은 호출부가 따로 잡는다
    if spec.sub_name_required and not parts["sub_name"]:
        return f"모듈 '{parts['module_name']}'은 분석 대상(sub_name)을 지정해야 합니다."
    return None


def produces_label(base: str, module: dict | str) -> str:
    """produces 이름표를 **조합 단위**로 만든다.

    지금은 `within_contribution`이 이름표를 module_name 단위로 생산해서 "한 계획에
    1회만"이라는 제약이 걸려 있다(steps.py). 조합 단위로 만들면 고객별 기여도와
    제품별 기여도를 한 보고서에 같이 넣을 수 있다.

        produces_label("within_contribution", {... "sub_name": "party"})
            → "within_contribution@party"

    sub_name이 없으면 base를 그대로 쓴다 — 기존 이름표와 같아 하위호환이 유지된다.
    """
    sub_name = normalize(module).get("sub_name")
    return f"{base}{_SUB_SEP}{sub_name}" if sub_name else base
