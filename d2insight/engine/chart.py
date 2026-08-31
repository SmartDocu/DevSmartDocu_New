"""차트 렌더링 — 모듈이 선언한 차트 스펙을 base64 이미지 마크다운으로 바꾼다.

모듈은 matplotlib를 모른다. '무엇을 어떤 형태로 그릴지'(스펙)만 선언하고(계산만 한다는 원칙),
실제 그림 생성은 여기 한 곳에 모은다 — 표(format.py)처럼 차트도 한 곳에서 만들어 스타일을
일관되게 유지한다. 그림 엔진 자체는 d2chat/d2insight가 이미 공유해 쓰는 d2shared/visualization.py
를 재사용한다(스냅샷 자체 visualization/ 패키지는 이식하지 않음 — 시그니처가 동일하고, 이쪽이
색상 전략·LLM 차트유형 판별 등 더 발전된 버전이다).

스펙 형식(Render.chart):
    {"data": <숫자 DataFrame: 0번 열=라벨, 1번+ 열=값>, "type": "bar|line|pie|None", "title": "..."}

data가 없거나 비면 차트를 그리지 않는다. 그림 생성이 실패해도 조용히 None을 돌려 본문을 죽이지
않는다(표·해설은 그대로 나간다). PDF 변환기(src/report/pdf.py)가 data URI 이미지를 처리하므로,
여기서 만든 `![](data:image/png;base64,...)`는 마크다운·PDF 양쪽에서 렌더된다.
"""
from __future__ import annotations

from typing import Any, Optional

from d2shared.visualization import dataframe_to_chart_image


def chart_spec(data: Any, chart_type: str | None = None, title: str = "") -> Optional[dict]:
    """모듈이 쓰는 헬퍼 — 차트 스펙 dict 하나. data가 비어 있으면 None(차트 생략)."""
    if data is None or getattr(data, "empty", True) or len(getattr(data, "columns", [])) < 2:
        return None
    return {"data": data, "type": chart_type, "title": title}


def render_chart_markdown(spec: Any) -> Optional[str]:
    """차트 스펙 → 마크다운 이미지 태그(`![title](data:image/png;base64,...)`).

    실패는 조용히 None으로 흘린다(그림 하나 때문에 보고서를 멈추지 않는다).
    """

    if not isinstance(spec, dict):
        return None                     # 스펙 계약(dict)이 아니면 조용히 생략
    data = spec.get("data")
    if data is None or getattr(data, "empty", True):
        return None
    try:
        b64, _json, err = dataframe_to_chart_image(data, spec.get("title") or "", spec.get("type"))
    except Exception as e:
        return None
    if not b64:
        return None
    alt = spec.get("title") or "차트"
    return f"![{alt}](data:image/png;base64,{b64})"


def render_chart_base64(spec: Any) -> Optional[str]:
    """차트 스펙 → 순수 base64 PNG(데이터 URI 접두어 없음).

    채팅 결과 계약의 `chart_image` 필드는 접두어 없는 base64를 기대하므로 마크다운 대신 이 함수를 쓴다.
    실패는 조용히 None으로 흘린다.
    """
    if not isinstance(spec, dict):
        return None
    data = spec.get("data")
    if data is None or getattr(data, "empty", True):
        return None
    try:
        b64, _json, _err = dataframe_to_chart_image(data, spec.get("title") or "", spec.get("type"))
    except Exception:
        return None
    return b64 or None
