"""[진단-덤프] 보고서 숫자 오류 원인 확인용 임시 파일 — 끝나면 이 파일과 '진단-덤프' 주석이 붙은 줄을 지운다.

파일을 jeff_docs/diag_dump/ 에 시각순으로 저장한다(폴더가 없으면 만든다).
"""
import json
import os
from datetime import datetime

_DIR = os.path.join("jeff_docs", "diag_dump")


def _path(name, ext):
    os.makedirs(_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))[:80]
    return os.path.join(_DIR, f"{datetime.now():%Y%m%d_%H%M%S_%f}_{safe}.{ext}")


def begin_run():
    os.makedirs(_DIR, exist_ok=True)
    print(f"[진단-덤프] 기록 폴더: {os.path.abspath(_DIR)}")


def dump_df(name, df):
    if hasattr(df, "to_csv"):
        df.to_csv(_path(name, "csv"), index=False, encoding="utf-8-sig")


def dump_json(kind, name, obj):
    with open(_path(f"{kind}_{name}", "json"), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def dump_llm(label, system, messages, response):
    dump_json("llm", label or "llm", {"system": system, "messages": messages, "response": response})
