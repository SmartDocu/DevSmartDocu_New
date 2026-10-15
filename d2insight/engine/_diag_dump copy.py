"""[진단-덤프] 보고서 숫자 오류의 원인 층을 가리기 위한 임시 기록 — 원인 확인 후 이 파일과 호출 줄을 삭제한다.

호출 줄은 모두 `# [진단-덤프] 확인 후 삭제` 주석이 붙어 있다(검색: "진단-덤프").

환경변수 D2I_DIAG_DUMP=1 일 때만 동작한다. 꺼져 있으면 아무것도 하지 않아 보고서 결과에 영향이 없다.
기록 위치: D2I_DIAG_DIR 또는 기본 <프로젝트>/jeff_docs/diag_dump/<시각>/ (보고서 1건 = 폴더 1개).

파일 이름은 실행 순서(001, 002 …)로 시작한다.
  NNN_df_<이름>.csv       모듈이 만든 데이터프레임 / 표
  NNN_render_<모듈>.json  모듈이 넘긴 summary·key_value (본문에 실리기 전)
  NNN_llm_<라벨>.json     LLM 호출 1건의 system·messages·응답 (프롬프트에 준 사실 포함)
  NNN_final_<모듈>.json   스텝 해설자까지 거친 뒤의 최종 narrative

보고서를 동시에 둘 이상 만들면 폴더가 섞인다 — 한 번에 하나씩 만든다.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path

_lock = threading.Lock()
_dir: Path | None = None
_seq = 0


def enabled() -> bool:
    return os.environ.get("D2I_DIAG_DUMP") == "1"


def _safe(name: str) -> str:
    return re.sub(r"[^\w가-힣.-]+", "_", str(name))[:80] or "x"


def begin_run() -> None:
    """보고서 1건의 실행이 시작될 때 새 폴더를 연다."""
    global _dir, _seq
    if not enabled():
        return
    try:
        base = os.environ.get("D2I_DIAG_DIR") or str(Path(__file__).resolve().parents[2] / "jeff_docs" / "diag_dump")
        with _lock:
            _dir = Path(base) / datetime.now().strftime("%Y%m%d_%H%M%S")
            _dir.mkdir(parents=True, exist_ok=True)
            _seq = 0
    except Exception as e:                       # 진단이 보고서를 막으면 안 된다
        print(f"[진단-덤프] 폴더 생성 실패: {e}")


def _next_path(kind: str, name: str, ext: str) -> Path | None:
    global _seq
    with _lock:
        if _dir is None:
            return None
        _seq += 1
        return _dir / f"{_seq:03d}_{kind}_{_safe(name)}.{ext}"


def dump_df(name: str, df) -> None:
    if not enabled():
        return
    try:
        import pandas as pd
        if not isinstance(df, pd.DataFrame):
            return
        p = _next_path("df", name, "csv")
        if p is not None:
            df.to_csv(p, index=False, encoding="utf-8-sig")
    except Exception as e:
        print(f"[진단-덤프] df 기록 실패 {name}: {e}")


def dump_json(kind: str, name: str, obj) -> None:
    if not enabled():
        return
    try:
        p = _next_path(kind, name, "json")
        if p is not None:
            p.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception as e:
        print(f"[진단-덤프] json 기록 실패 {name}: {e}")


def dump_llm(label: str, system, messages, response) -> None:
    dump_json("llm", label or "llm", {"system": system, "messages": messages, "response": response})
