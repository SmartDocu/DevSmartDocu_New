"""공통 자연어→SQL 생성+실행 — d2chat/d2insight 공유.

출처: pr_d2chat/mcp_core/mcp_server.py + pr_d2insight/src/report/sql_generator.py
통합 변경:
  - INFORMATION_SCHEMA 뷰 목록 조회 제거 → table_metadata.keys() 사용
  - PostgreSQL(Supabase): schema.table_name 형식
  - force_aggregate: d2insight용 GROUP BY 집계 강제 옵션
  - log_fn: 호출자가 log_llm_call 전달 (d2shared → d2chat 역방향 의존 방지)
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional, Dict, Callable

import pandas as pd

from d2shared.db_engine import DbEngine

OPENAI_MODELS = [
    "gpt-5.1", "gpt-5-pro", "gpt-5", "gpt-5-mini", "gpt-5-nano",
    "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
    "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4",
    "gpt-3.5-turbo", "gpt-3.5-turbo-16k",
]
ANTHROPIC_MODELS = [
    "claude-fable-5", "claude-opus-4-8", "claude-opus-4-7",
    "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
    "claude-sonnet-4-20250514", "claude-3-7-sonnet-20250219",
    "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229", "claude-3-haiku-20240307",
]

_MAX_ROWS = 500


def _sql_rules(dialect: str, schema: str = "", force_aggregate: bool = False) -> str:
    """방언별 SQL 작성 규칙 문자열 반환."""
    agg = ""
    if force_aggregate:
        if "mssql" in dialect:
            agg = "\n🔥 집계 규칙: 반드시 GROUP BY 집계 사용. SELECT * 금지. TOP 100 이내."
        elif "oracle" in dialect:
            agg = "\n🔥 집계 규칙: 반드시 GROUP BY 집계 사용. SELECT * 금지. FETCH FIRST 100 ROWS ONLY."
        else:
            agg = "\n🔥 집계 규칙: 반드시 GROUP BY 집계 사용. SELECT * 금지. LIMIT 100 이내."

    if "mssql" in dialect:
        return (
            "- SQL Server 문법 사용\n"
            "- 테이블/뷰 명칭은 [dbo].[이름] 형식\n"
            "- TOP 사용 (LIMIT 금지)\n"
            "- 한글 또는 비 ASCII 문자열 비교 시 반드시 N'문자열' 사용\n"
            "- JOIN 시 명시적으로 INNER JOIN 또는 LEFT JOIN 사용\n"
            "- 메타데이터에 명시된 컬럼명만 정확히 사용\n"
            "- 숫자 컬럼에 FORMAT() 등 문자열 변환 함수 사용 금지"
            + agg
        )
    elif dialect in ("mysql", "postgresql", "sqlite"):
        schema_rule = (
            f"- 테이블/뷰는 반드시 {schema}.이름 형식 사용 (스키마 접두어 필수)\n"
            if schema else
            "- 테이블 명칭에 스키마 접두어 사용 금지\n"
        )
        return (
            "- 해당 DB 고유 문법 사용\n"
            + schema_rule +
            "- LIMIT 사용 (TOP 사용 금지)\n"
            "- 문자열 리터럴은 반드시 '문자열' 사용\n"
            "- N'문자열' 사용 금지\n"
            "- 숫자 컬럼에 FORMAT() 등 문자열 변환 함수 사용 금지"
            + agg
        )
    elif "oracle" in dialect:
        return (
            "- Oracle SQL 문법 사용\n"
            "- FETCH FIRST N ROWS ONLY 사용\n"
            "- SYSDATE 사용\n"
            "- 문자열 리터럴은 '문자열' 사용"
            + agg
        )
    return f"- {dialect} 문법 사용{agg}"


class SqlGenerator:
    """자연어 질문 → SQL 생성 + 실행.

    d2chat MCPServer / d2insight SqlGenerator 통합.
    """

    def __init__(
        self,
        connection_url: str,
        db_schema: str = "",
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self._engine = DbEngine(connection_url)
        self._dialect: str = self._engine.dialect
        self._db_schema = db_schema
        self._model = model

    @property
    def dialect(self) -> str:
        return self._dialect

    def _clean_sql(self, sql: str) -> str:
        sql = sql.replace("```sql", "").replace("```", "").strip()
        lines = [ln.strip() for ln in sql.split("\n") if not ln.strip().startswith("--")]
        return " ".join(lines)

    def _objects_str(self, object_names: list) -> str:
        """방언 + 스키마에 맞는 테이블 참조 문자열 생성."""
        if "mssql" in self._dialect:
            return ", ".join(f"[dbo].[{n}]" for n in object_names)
        if self._db_schema and self._dialect in ("postgresql", "mysql", "sqlite"):
            return ", ".join(f"{self._db_schema}.{n}" for n in object_names)
        return ", ".join(object_names)

    def generate_sql_query(
        self,
        question: str,
        table_name: Optional[str] = None,
        table_metadata: Optional[Dict] = None,
        current_date_info: Optional[Dict] = None,
        force_aggregate: bool = False,
        log_fn: Optional[Callable] = None,
        log_ctx: Optional[Dict] = None,
    ) -> str:
        """자연어 질문 → 방언별 SELECT SQL 문자열 생성."""
        meta = table_metadata or {}
        primary_meta = meta.get(table_name, {}) if table_name else {}
        dataset_query = primary_meta.get("query", "")
        is_type2 = bool(dataset_query) and not primary_meta.get("physical_name", "")

        sql_rule = _sql_rules(self._dialect, self._db_schema, force_aggregate)

        date_context = ""
        if current_date_info:
            date_context = (
                f"\n📅 현재 날짜: {current_date_info.get('current_date')}"
                f" | 어제: {current_date_info.get('yesterday')}"
                f" | 이번달 시작: {current_date_info.get('this_month_start')}"
                f" | 지난달 시작: {current_date_info.get('last_month_start')}\n"
            )

        if is_type2:
            prompt = f"""당신은 숙련된 데이터베이스 엔지니어입니다.
{date_context}
아래 미리 정의된 데이터셋을 CTE로 사용하여 쿼리를 작성하세요.

CTE 정의:
WITH {table_name} AS (
    {dataset_query}
)

메타데이터:
{json.dumps(meta, ensure_ascii=False, indent=2)}

사용자 질문:
"{question}"

요구사항:
{sql_rule}
- 반드시 위 CTE를 선언하고 FROM 절에서 {table_name}을 참조하세요
- SELECT 쿼리만 생성 (INSERT/UPDATE/DELETE 금지)
- 메타데이터에 명시된 컬럼명만 정확히 사용
- 매핑 불가한 경우: SELECT 'CANNOT_ANSWER' AS result, '해당 조건을 처리할 수 없습니다' AS reason
- 결과만 SQL로 출력 (백틱, 설명, 주석 제외)
"""
        else:
            object_names = [table_name] if table_name else list(meta.keys())
            objects_str = self._objects_str(object_names)
            prompt = f"""당신은 숙련된 데이터베이스 엔지니어입니다.
{date_context}
DB 정보:
- Dialect: {self._dialect}
- 사용 가능한 뷰/테이블: {objects_str}

메타데이터:
{json.dumps(meta, ensure_ascii=False, indent=2)}

사용자 질문:
"{question}"

요구사항:
{sql_rule}
- SELECT 쿼리만 생성 (INSERT/UPDATE/DELETE 금지)
- 메타데이터에 명시된 컬럼명만 정확히 사용
- 조건이 메타데이터와 매핑되지 않으면 억지 매핑 금지
- 매핑 불가한 경우: SELECT 'CANNOT_ANSWER' AS result, '해당 조건을 처리할 수 없습니다' AS reason
- 컬럼 선택: 사용자 요청 정보만 SELECT (정렬용 보조 컬럼은 ORDER BY에만 사용)
- 숫자 컬럼에 FORMAT() 등 문자열 변환 함수 사용 금지
- 조인 필요 시 메타데이터의 reference 정보를 참고하여 INNER JOIN 또는 LEFT JOIN 사용
- 결과만 SQL로 출력 (백틱, 설명, 주석 제외)
"""

        start = datetime.now()
        sql_text = self._call_llm(prompt)
        end = datetime.now()

        if log_fn and log_ctx:
            try:
                log_fn(
                    log_ctx=log_ctx,
                    stepnm="sql_generate",
                    steptitle="SQL 생성",
                    llmmodelnm=self._model,
                    inputtoken=0,
                    outputtoken=0,
                    startdts=start,
                    enddts=end,
                )
            except Exception:
                pass

        return sql_text

    def _call_llm(self, prompt: str) -> str:
        """모델 종류에 따라 Anthropic 또는 OpenAI API 호출."""
        from backend.app.config import settings

        if self._model in OPENAI_MODELS:
            from openai import OpenAI
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You generate SQL queries only."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                timeout=30,
            )
            return resp.choices[0].message.content.strip()
        else:
            from anthropic import Anthropic
            client = Anthropic(api_key=settings.CLAUDE_API_KEY)
            resp = client.messages.create(
                model=self._model,
                max_tokens=2048,
                temperature=0,
                system="You generate SQL queries only.",
                messages=[{"role": "user", "content": prompt}],
                timeout=30,
            )
            return resp.content[0].text.strip()

    def execute_natural_language_query(
        self,
        question: str,
        table_name: Optional[str] = None,
        table_metadata: Optional[Dict] = None,
        current_date_info: Optional[Dict] = None,
        force_aggregate: bool = False,
        max_rows: int = _MAX_ROWS,
        log_fn: Optional[Callable] = None,
        log_ctx: Optional[Dict] = None,
    ) -> Dict:
        """자연어 질문을 SQL로 변환하여 실행하고 결과를 반환한다.

        반환 형식 (d2chat 호환):
          성공: {"status": "success", "data": [...], "columns": [...], "row_count": N,
                 "truncated": bool, "message": "...", "conditions": {"generated_sql": "..."}}
          빈 결과: {"status": "no_data", ...}
          오류: {"status": "error", "data": [], "message": "...", "conditions": {...}}
        """
        try:
            sql_query = self.generate_sql_query(
                question=question,
                table_name=table_name,
                table_metadata=table_metadata,
                current_date_info=current_date_info,
                force_aggregate=force_aggregate,
                log_fn=log_fn,
                log_ctx=log_ctx,
            )
            sql_query = self._clean_sql(sql_query)

            sql_upper = sql_query.upper().strip()
            if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
                return {
                    "status": "error",
                    "data": [],
                    "message": "SELECT 쿼리만 허용됩니다",
                    "conditions": {
                        "question": question,
                        "table_name": table_name,
                        "generated_sql": sql_query,
                    },
                    "data_type": "error",
                }

            df: pd.DataFrame = self._engine.execute_query(sql_query)

            truncated = False
            if len(df) > max_rows:
                df = df.head(max_rows)
                truncated = True

            data = df.to_dict("records")
            conditions = {
                "question": question,
                "table_name": table_name,
                "generated_sql": sql_query,
            }

            if not data:
                return {
                    "status": "no_data",
                    "data": [],
                    "message": "검색 조건에 해당하는 데이터가 없습니다",
                    "conditions": conditions,
                    "data_type": "dynamic_query",
                }

            return {
                "status": "success",
                "data": data,
                "columns": list(df.columns),
                "row_count": len(data),
                "truncated": truncated,
                "message": "데이터 조회 성공",
                "conditions": conditions,
                "data_type": "dynamic_query",
            }

        except Exception as exc:
            return {
                "status": "error",
                "data": [],
                "message": str(exc),
                "conditions": {"question": question, "table_name": table_name},
                "data_type": "error",
            }
