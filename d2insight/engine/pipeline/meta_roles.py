"""등록된 메타에서 컬럼 역할(Semantic_Type)을 판정한다.

메타에는 표시명·별칭·데이터타입·값 목록·용도가 이미 들어 있다. 그것을 그대로 LLM에게 보여
판정하게 한다 — 업로드 파일 경로(upload_meta.py)와 같은 방식이라 두 경로가 어긋나지 않는다.

판정 결과는 메타 내용으로 만든 서명(signature)에 걸어 캐시한다. 메타를 고치면 서명이 달라져
저절로 다시 판정한다.
"""
from __future__ import annotations

import hashlib
import json
import threading

from d2insight.engine.schema import ALL_ROLES, ROLE_GUIDE

ROLE_EXCLUDE = "exclude"

_SYSTEM = """당신은 등록된 데이터 메타를 읽고, 각 컬럼이 분석에서 어떤 역할을 하는지 판정한다.
JSON만 출력한다.

역할 후보 — 해당 없으면 빈 문자열로 둔다:
""" + ROLE_GUIDE + """

판정 근거는 주어진 메타(표시명·별칭·값 목록·용도·데이터타입)다. 이름 몇 글자만 보고 짐작하지
말고 표시명과 값 목록을 함께 본다.

규칙
1. 역할이 없는 컬럼이 많은 것은 정상이다. 억지로 채우지 마라 — 애매하면 빈 문자열이다.
2. 같은 역할을 여러 컬럼에 주지 마라. 가장 대표적인 컬럼 하나에만 준다.
   (예: 총액과 공급가액이 같이 있으면 대표 매출 하나에만 amount)
3. 여러 행에 걸쳐 그대로 더하면 의미가 없어지는 숫자 컬럼(단가·평균·비율·마진율·점수 등)에는
   역할 대신 "exclude"를 준다 — 이 컬럼은 합계 대상에서 빠진다. 위에 나열한 것 외에도, 합산에
   적절하지 않다고 판단되는 숫자 컬럼은 "exclude"다.
   단, 더해서 의미가 있는 값에는 exclude를 주지 마라. 금액 성격의 값(공급가액·세금·배송비·
   할인액·총액처럼 행마다 더하면 전체 합계가 되는 것)과 수량은 역할이 없더라도 exclude가
   아니다 — 그런 컬럼은 그냥 빈 문자열로 둔다. exclude는 "더하면 틀린 값이 되는 경우"에만
   쓴다. 숫자가 아닌 컬럼(이름·코드·날짜)에는 exclude를 주지 마라.
4. 식별자(ID)에는 역할을 주지 마라.
5. 지역·국가·권역이 여러 단계로 있으면 분석의 기준이 되는 하나에만 region을 준다.

출력 형식(설명 없이 JSON 객체만):
{"테이블명.컬럼명": "역할 또는 exclude 또는 빈 문자열", ...}"""


_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def _digest(sources: list[dict]) -> str:
    payload = json.dumps(_prompt_payload(sources), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _prompt_payload(sources: list[dict]) -> list[dict]:
    """LLM에게 보여줄 메타 — 등록된 값 그대로. 값 목록은 앞의 몇 개만 추린다."""
    out = []
    for src in sources:
        cols = []
        for col in src.get("columns") or []:
            colnm = col["querycolnm"]
            colmeta = (src.get("columns_meta") or {}).get(colnm) or {}
            entry = {
                "column": colnm,
                "logical_name": colmeta.get("logical_name") or col.get("dispcolnm") or "",
                "data_type": (col.get("datatypecd") or "").lower(),
            }
            if colmeta.get("aliases"):
                entry["aliases"] = colmeta["aliases"]
            values = colmeta.get("values") or {}
            if values:
                entry["value_examples"] = [
                    {"value": v, "logical_name": (meta or {}).get("logical_name", "")}
                    for v, meta in list(values.items())[:8]
                ]
            cols.append(entry)
        out.append({
            "table": src.get("physical_name") or src.get("datanm") or "",
            "logical_name": src.get("logical_name") or src.get("datanm") or "",
            "description": src.get("description") or "",
            "purpose": src.get("purpose") or [],
            "default_time_column": src.get("default_time_column") or "",
            "columns": cols,
        })
    return out


def infer_roles(sources: list[dict], provider: str | None = None) -> dict[tuple[str, str], str]:
    """소스 묶음 → {(테이블, 컬럼): 역할}. 판정하지 못하면 빈 dict."""
    if not sources:
        return {}

    key = _digest(sources)
    with _cache_lock:
        hit = _cache.get(key)
    if hit is not None:
        return hit

    payload = _prompt_payload(sources)
    prompt = (
        "다음은 등록된 데이터 메타다.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n\n각 컬럼의 역할을 판정하라."
    )

    roles: dict[tuple[str, str], str] = {}
    try:
        from d2insight.engine._llm import chat

        raw = chat(
            [{"role": "user", "content": prompt}],
            grade="balanced", system=_SYSTEM, max_tokens=2000,
            label="등록 메타 역할 판정", stepnm="meta_roles", steptitle="역할 판정",
            provider=provider,
        ).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").split("\n", 1)[-1]
        start, end = raw.find("{"), raw.rfind("}")
        parsed = json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
        for ref, role in (parsed or {}).items():
            # "exclude" = 합산하면 의미 없는 숫자 컬럼(단가 등) — db_meta가 측정값에서 뺀다.
            if not role or (role not in ALL_ROLES and role != ROLE_EXCLUDE):
                continue
            table, _, colnm = str(ref).rpartition(".")
            roles[(table, colnm)] = role
    except Exception as e:
        print(f"[meta_roles] 역할 판정 실패, 역할 없이 진행: {type(e).__name__}: {e}")
        return {}

    with _cache_lock:
        _cache[key] = roles
    return roles
