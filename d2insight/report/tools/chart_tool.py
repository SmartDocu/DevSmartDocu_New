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
    이후 스텝이 잘리는 문제를 방지하기 위해, create_chart는 base64를
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

    if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
        return {
            "error": (
                "data는 execute_query가 반환한 'data' 필드와 같은 list[dict] 형식이어야 "
                "합니다. 숫자를 손으로 재구성하지 말고, 조회 결과의 레코드를 그대로 전달하세요."
            ),
            "chart_image": None,
        }

    # 두 시점(예: 2월 vs 3월)을 비교하는 차트를 만들려고 두 번의 조회 결과를 손으로
    # 합치다가, 실제 값이 컬럼명(키) 자리에 잘못 들어가는 사고가 확인됐다(2026-08-19,
    # 기간비교 dual_axis 차트의 범례·축 라벨에 "2600218.8667" 같은 원값이 그대로 노출됨).
    # 조용히 깨진 차트를 만드는 대신 에러로 돌려줘 모델이 스스로 데이터를 바로잡게 한다.
    def _looks_numeric(s) -> bool:
        try:
            float(str(s).replace(',', ''))
            return True
        except ValueError:
            return False

    all_keys = {k for row in data for k in row.keys()}
    if all_keys and all(_looks_numeric(k) for k in all_keys):
        return {
            "error": (
                "data의 컬럼명(키)이 숫자처럼 보입니다 — 실제 값이 컬럼명 자리에 잘못 "
                "들어간 것으로 보입니다. 두 시점을 비교하는 차트라면, 각 execute_query "
                "결과의 레코드를 원래 컬럼명(키)을 유지한 채 그대로 이어붙여 전달하세요."
            ),
            "chart_image": None,
        }

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
