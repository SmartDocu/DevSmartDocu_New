"""create_chart 툴 — d2shared.visualization 재활용."""
from __future__ import annotations

import threading
from typing import Optional

import pandas as pd
from langchain_core.tools import tool

from d2shared.visualization import dataframe_to_chart_image


class _ChartStore:
    """차트 base64를 보관하고 짧은 플레이스홀더 키를 발급한다."""

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
    """
    if not data:
        return {"error": "데이터가 없습니다.", "chart_image": None}

    df = pd.DataFrame(data)
    try:
        image_b64, _ = dataframe_to_chart_image(df, question, chart_type)
    except Exception as exc:
        return {"error": str(exc), "chart_image": None}

    if image_b64:
        key = _chart_store.put(f"data:image/png;base64,{image_b64}")
        return {
            "success": True,
            "markdown_tag": f"![{question}]({key})",
            "note": "차트가 생성되었습니다. markdown_tag 값을 보고서 텍스트에 그대로 삽입하세요.",
        }
    return {"error": "차트 생성 실패", "chart_image": None}
