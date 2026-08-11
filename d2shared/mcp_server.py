"""
mcp_server.py — 자연어→SQL 쿼리 생성·실행 (d2chat · d2insight 공통)

- MCPServer : SQLAlchemy 엔진 + LangChain SQLDatabase
  - generate_sql_query            : 자연어 → SQL 문자열
  - execute_natural_language_query: 자연어 → SQL 실행 → 표준 응답
"""
from __future__ import annotations

import json
import os
from typing import Dict, Optional, Any, List

import pandas as pd
from sqlalchemy import create_engine, text
from langchain_community.utilities import SQLDatabase

from d2shared.config import DEFAULT_LLM_MODEL
from d2shared.llm_logger import log_llm_call


class MCPServer:
    """DB 전용 MCP 서버 — 자연어 질문을 SQL로 변환해 실행한다."""

    def __init__(self, db_connection: str, table_name: str = "view_rtims_logs"):
        self.db_connection = db_connection
        self.table_name = table_name
        try:
            self.engine = create_engine(
                db_connection,
                connect_args={"timeout": 30},
                pool_pre_ping=True,
            )
            self.langchain_db = SQLDatabase(self.engine)
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            raise Exception(f"DB 연결 실패: {str(e)}")

    # ── 내부 헬퍼 ────────────────────────────────────────────────

    def _execute_query(self, query: str, params: Optional[Dict] = None) -> pd.DataFrame:
        try:
            with self.engine.connect() as conn:
                conn = conn.execution_options(timeout=30)
                return pd.read_sql_query(text(query), conn, params=params)
        except Exception as e:
            raise Exception(f"쿼리 실행 실패: {str(e)}")

    def _create_standard_response(self, data: Any, conditions: Optional[Dict] = None,
                                   data_type: str = "query") -> Dict:
        if isinstance(data, dict) and 'error' in data:
            return {"status": "error", "data": data,
                    "message": data.get('error', '오류'), "conditions": conditions, "data_type": data_type}
        has_data = (
            (len(data) > 0) if isinstance(data, (list, dict)) else (data is not None)
        )
        if not has_data:
            return {"status": "no_data", "data": data,
                    "message": "검색 조건에 해당하는 데이터가 없습니다", "conditions": conditions, "data_type": data_type}
        return {"status": "success", "data": data,
                "message": "데이터 조회 성공", "conditions": conditions, "data_type": data_type}

    def _clean_sql(self, sql: str) -> str:
        sql = sql.replace("```sql", "").replace("```", "").strip()
        lines = [line.strip() for line in sql.split('\n') if not line.strip().startswith('--')]
        return ' '.join(lines)

    # ── SQL 생성 ──────────────────────────────────────────────────

    def generate_sql_query(
        self,
        question: str,
        model: str,
        table_name: Optional[str] = None,
        table_metadata: Optional[Dict] = None,
        current_date_info: Optional[Dict] = None,
        log_ctx: Optional[Dict] = None,
        extra_rules: str = "",
        api_key: Optional[str] = None,
        vendor_name: Optional[str] = None,
    ) -> str:
        """자연어 질문을 DB dialect에 맞는 SELECT 쿼리로 변환한다."""

        dialect = self.langchain_db.dialect
        primary_meta = (table_metadata or {}).get(table_name, {}) if table_name else {}
        dataset_query = primary_meta.get('query', '')
        is_type2 = bool(dataset_query) and not primary_meta.get('physical_name', '')

        objects_str = ""
        if not is_type2:
            # pr_d2insight 패턴: INFORMATION_SCHEMA 조회 대신 table_metadata keys 사용
            # → LLM의 참조 범위를 data_metas에 등록된 뷰로만 제한
            if table_name:
                object_names = [table_name]
            else:
                object_names = list((table_metadata or {}).keys())

            if "mssql" in dialect:
                objects_str = ", ".join(f"[dbo].[{n}]" for n in object_names)
            else:
                objects_str = ", ".join(object_names)

        if "mssql" in dialect:
            sql_rule = (
                "- SQL Server 문법 사용\n"
                "- 테이블/뷰 명칭은 반드시 [dbo].[이름] 형식만 사용 — 다른 스키마(Sales, HumanResources 등) 절대 사용 금지\n"
                "- TOP 사용\n"
                "- 한글 또는 비 ASCII 문자열 비교 시 반드시 N'문자열' 사용\n"
                "- 메타데이터에 명시된 컬럼명만 정확히 사용\n"
                "- 메타데이터에 없는 테이블/뷰 JOIN 금지 — 필요한 컬럼이 없으면 SELECT 'CANNOT_ANSWER' AS result 반환"
            )
        elif dialect in ["mysql", "postgresql", "sqlite"]:
            sql_rule = (
                "- 해당 DB 고유 문법 사용\n"
                "- LIMIT 사용 (TOP 사용 금지)\n"
                "- N'문자열' 사용 금지"
            )
        elif "oracle" in dialect:
            sql_rule = (
                "- Oracle SQL 문법 사용\n"
                "- FETCH FIRST N ROWS ONLY 사용\n"
                "- SYSDATE 사용"
            )
        else:
            sql_rule = f"- {dialect} 문법 사용"

        sql_rule = (
            f"{sql_rule}\n"
            "- 코드값/상태값 등으로 조건절(WHERE)을 작성할 때, 메타데이터의 컬럼 설명이나 예시 쿼리에 그 값이 "
            "명시되어 있지 않다면 값을 임의로 짐작해서 비교하지 마세요. 짐작한 값으로 조건을 걸면 실제로는 "
            "존재하지 않는 값이라 결과가 0건이거나 잘못된 값으로 조용히 나올 수 있습니다.\n"
            "- 확실한 근거 없이 코드값을 짐작해야만 답변 가능한 질문이라면, 정확한 값을 확인할 수 없다는 뜻이므로 "
            "SELECT 'CANNOT_ANSWER' AS result, '조건에 사용할 정확한 코드값을 확인할 수 없습니다' AS reason 을 반환하세요."
        )

        if extra_rules:
            sql_rule = f"{sql_rule}\n{extra_rules}"

        date_context = ""
        if current_date_info:
            date_context = (
                f"현재 날짜: {current_date_info.get('current_date')}, "
                f"어제: {current_date_info.get('yesterday')}, "
                f"이번달 시작: {current_date_info.get('this_month_start')}, "
                f"지난달 시작: {current_date_info.get('last_month_start')}"
            )

        if is_type2:
            prompt = f"""당신은 숙련된 데이터베이스 엔지니어입니다.
날짜 정보: {date_context}
아래 미리 정의된 데이터셋을 CTE로 사용하여 쿼리를 작성하세요.

CTE 정의:
WITH {table_name} AS ({dataset_query})

메타데이터:
{json.dumps(table_metadata, ensure_ascii=False, indent=2)}

사용자 질문: "{question}"

요구사항:
{sql_rule}
- 반드시 위 CTE를 선언하고 FROM 절에서 {table_name}을 참조하세요
- SELECT 쿼리만 생성 (INSERT/UPDATE/DELETE 금지)
- 숫자 컬럼에 FORMAT() 등 문자열 변환 함수 사용 금지
- 결과만 SQL로 출력 (백틱, 설명, 주석 제외)
"""
        else:
            prompt = f"""당신은 숙련된 데이터베이스 엔지니어입니다.
날짜 정보: {date_context}
DB 정보:
- Dialect: {dialect}
- 사용 가능한 뷰: {objects_str}

메타데이터:
{json.dumps(table_metadata, ensure_ascii=False, indent=2)}

사용자 질문: "{question}"

요구사항:
{sql_rule}
- SELECT 쿼리만 생성 (INSERT/UPDATE/DELETE 금지)
- 메타데이터에 명시된 컬럼명만 정확히 사용
- 매핑 불가한 경우: SELECT 'CANNOT_ANSWER' AS result, '해당 조건을 처리할 수 없습니다' AS reason
- 숫자 컬럼에 FORMAT() 등 문자열 변환 함수 사용 금지
- 숫자형 컬럼 정렬 시 CAST: ORDER BY CAST(컬럼 AS INT) ASC
- 결과만 SQL로 출력 (백틱, 설명, 주석 제외)
"""

        from datetime import datetime
        from langchain_core.messages import SystemMessage, HumanMessage
        from utilsPrj.ai_chain import build_langchain_llm, get_llm_info

        if not api_key or not vendor_name:
            _project_id = (log_ctx or {}).get("project_id")
            _tenant_id = (log_ctx or {}).get("tenant_id")
            _user_uid = (log_ctx or {}).get("creator")
            _account_uid = (log_ctx or {}).get("account_uid")
            _svc_code = (log_ctx or {}).get("servicecd") or None
            model, api_key, vendor_name, _is_customeraikey, _resolved_account_uid = get_llm_info(
                project_id=_project_id, tenant_id=_tenant_id,
                user_uid=_user_uid, account_uid=_account_uid, service_code=_svc_code,
            )
            if log_ctx is not None:
                log_ctx["is_customeraikey"] = _is_customeraikey
                if not log_ctx.get("account_uid"):
                    log_ctx["account_uid"] = _resolved_account_uid

        llm = build_langchain_llm(vendor_name, api_key, model)
        start = datetime.now()
        response = llm.invoke([
            SystemMessage(content="You generate SQL queries only."),
            HumanMessage(content=prompt),
        ])
        end = datetime.now()
        usage = getattr(response, "usage_metadata", None) or {}
        log_llm_call(
            log_ctx=log_ctx, stepnm="sql_generate", steptitle="SQL 생성", llmmodelnm=model,
            inputtoken=usage.get("input_tokens", 0),
            outputtoken=usage.get("output_tokens", 0),
            is_success=True,
            startdts=start, enddts=end,
        )
        content = response.content
        return (content if isinstance(content, str) else content[0].text).strip()

    # ── 자연어 쿼리 실행 ────────────────────────────────────────

    def execute_natural_language_query(
        self,
        question: str,
        table_name: Optional[str] = None,
        model: str = DEFAULT_LLM_MODEL,
        table_metadata: Optional[Dict] = None,
        current_date_info: Optional[Dict] = None,
        log_ctx: Optional[Dict] = None,
        extra_rules: str = "",
        api_key: Optional[str] = None,
        vendor_name: Optional[str] = None,
    ) -> Dict:
        """자연어 질문을 SQL로 변환하여 실행하고 표준 응답을 반환한다."""
        try:
            sql_query = self.generate_sql_query(
                question=question, model=model, table_name=table_name,
                table_metadata=table_metadata, current_date_info=current_date_info,
                log_ctx=log_ctx, extra_rules=extra_rules,
                api_key=api_key, vendor_name=vendor_name,
            )
            sql_query = self._clean_sql(sql_query)

            sql_upper = sql_query.upper().strip()
            if not sql_upper.startswith("SELECT") and not sql_upper.startswith("WITH"):
                return self._create_standard_response(
                    {"error": "SELECT 쿼리만 허용됩니다"},
                    conditions={"question": question, "table_name": table_name},
                    data_type="error",
                )

            result = self._execute_query(sql_query)
            if len(result) == 0:
                data: List = []
            else:
                result_copy = result.copy()
                for col in result_copy.columns:
                    if pd.api.types.is_datetime64_any_dtype(result_copy[col]):
                        result_copy[col] = result_copy[col].astype(str)
                    elif result_copy[col].dtype == 'object':
                        result_copy[col] = result_copy[col].apply(
                            lambda x: x.isoformat() if hasattr(x, 'isoformat') else x
                        )
                data = result_copy.to_dict('records')

            return self._create_standard_response(
                data=data,
                conditions={"question": question, "table_name": table_name, "generated_sql": sql_query},
                data_type="dynamic_query",
            )

        except Exception as e:
            # print(f"SQL 실행 오류: {str(e)}")
            import traceback
            traceback.print_exc()
            return self._create_standard_response(
                {"error": str(e)},
                conditions={"question": question, "table_name": table_name},
                data_type="error",
            )

    def reload_data(self):
        return {"status": "success", "message": "DB 모드는 항상 최신 데이터 조회"}
