"""카탈로그 패키지 — 제공자가 통제하는 세 레지스트리 + 수동용 기본 세트 (§7).

접근은 항상 getter 경유(§7.2). 실행 엔진은 dict를 직접 import하지 않고 EngineCatalog 어댑터로만
소통하므로, 나중에 저장소를 DB로 옮겨도 엔진 코드는 불변이다.
"""
from __future__ import annotations

from d2insight.engine.types import ModuleSpec
from d2insight.engine.catalog.labels import get_label_dictionary
from d2insight.engine.catalog.tools import get_tool_registry
from d2insight.engine.catalog.modules import get_module_registry
from d2insight.engine.catalog.steps import get_step_registry
from d2insight.engine.catalog.scenarios import get_scenario
from d2insight.engine.catalog.narrator import narrate_step

__all__ = [
    "get_label_dictionary", "get_tool_registry", "get_module_registry",
    "get_step_registry", "get_scenario", "EngineCatalog", "CatalogError",
]


class CatalogError(Exception):
    """카탈로그에 없는 모듈/스텝 조회 등."""


class EngineCatalog:
    """runner의 Catalog Protocol을 만족하는 어댑터.

    실행 엔진은 이 객체의 get_module/get_step/narrate_step만 호출한다. 카탈로그 "내용물"은
    이 어댑터 뒤에 숨어 있어, 무엇이 추가되든 엔진은 불변이다(§7.3). 결론은 2026-07-28(7단계)
    부터 run_conclusion 특수 경로가 아니라 get_module("conclusion")으로 나오는 평범한 모듈이다.
    """

    def __init__(self) -> None:
        self._modules = get_module_registry()
        self._steps = get_step_registry()

    def get_module(self, module_id: str) -> ModuleSpec:
        try:
            return self._modules[module_id]
        except KeyError:
            # 최근접 추천(결정 2026-07-10)은 계획기/진입 계층의 몫이다. 엔진은 명확히 실패시킨다.
            raise CatalogError(f"등록되지 않은 모듈: '{module_id}'")

    def get_step(self, step_id: str) -> dict:
        try:
            return self._steps[step_id]
        except KeyError:
            raise CatalogError(f"등록되지 않은 스텝: '{step_id}'")

    def narrate_step(self, step_label: str, items: list[dict], ctx) -> dict:
        """스텝 본문 해설 — 스텝당 LLM 1회(§7.1, 결정 2026-07-14).

        엔진은 "해설을 붙인다"는 사실만 알고, 어떤 모델로 어떻게 쓰는지는 카탈로그 뒤에 숨는다.
        """
        return narrate_step(step_label, items, ctx)
