"""create_chart 툴 — d2shared.visualization 재활용."""
from __future__ import annotations

import threading
from typing import Optional

import pandas as pd
from langchain_core.tools import tool

from d2shared.visualization import dataframe_to_chart_image


class _ChartStore:
    """차트 base64를 보관하고 짧은 플레이스홀더 키를 발급한다.

    LLM이 수십만 자의 base64를 직접 출력하면 max_tokens 한계에 걸려
    이후 섹션이 잘리는 문제를 방지하기 위해, create_chart는 base64를
    이 저장소에 보관하고 짧은 키(CHART_PLACEHOLDER_N)만 반환한다.
    agent.generate() 완료 후 키를 실제 data URI로 치환한다.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, str] = {}
        self._counter = 0

    def reset(self) -> None:
        with self._lock:
            self._data.clear()
            self._counter = 0

    def put(self, data_uri: str) -> str:
        with self._lock:
            key = f"CHART_PLACEHOLDER_{self._counter}"
            self._data[key] = data_uri
            self._counter += 1
            return key

    def get_all(self) -> dict[str, str]:
        with self._lock:
            return dict(self._data)


_chart_store = _ChartStore()


@tool
def create_chart(data: list, question: str, chart_type: Optional[str] = None) -> dict:
    """데이터를 차트로 시각화하여 Base64 PNG 이미지를 반환합니다.

    Args:
        data: 시각화할 데이터 (records 형식 list[dict]). execute_query 결과의 'data' 필드를 그대로 전달.
        question: 차트 제목. 키워드로 유형 자동 감지에 활용됨.
        chart_type: bar | line | pie | scatter | dual_axis | None(자동감지)
            - dual_axis: 두 계열의 단위/스케일이 크게 다를 때 사용 (예: 매출액 + 변화율, DVI + Shapley_Value)
            - 생략 시 스케일 차이 50배↑이면 dual_axis, 'pie/원형/점유율' 키워드면 pie로 자동 선택
    """
    if not data:
        return {"error": "데이터가 없습니다.", "chart_image": None}

    df = pd.DataFrame(data)
    try:
        image_b64, _, chart_err = dataframe_to_chart_image(df, question, chart_type)
    except Exception as exc:
        return {"error": str(exc), "chart_image": None}

    if image_b64:
        key = _chart_store.put(f"data:image/png;base64,{image_b64}")
        return {
            "success": True,
            "markdown_tag": f"![{question}]({key})",
            "note": "차트가 생성되었습니다. markdown_tag 값을 보고서 텍스트에 그대로 삽입하세요.",
        }
    return {"error": chart_err or "차트 생성 실패", "chart_image": None}
