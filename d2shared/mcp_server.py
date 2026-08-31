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

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from langchain_community.utilities import SQLDatabase

from d2shared.config import DEFAULT_LLM_MODEL
from d2shared.llm_logger import log_llm_call
from d2shared.amount_format import annotate_amounts


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
                                   data_type: str = "query", dataset_context: Optional[Dict] = None) -> Dict:
        if isinstance(data, dict) and 'error' in data:
            return {"status": "error", "data": data,
                    "message": data.get('error', '오류'), "conditions": conditions, "data_type": data_type}
        has_data = (
            (len(data) > 0) if isinstance(data, (list, dict)) else (data is not None)
        )
        if not has_data:
            return {"status": "no_data", "data": data,
                    "message": "검색 조건에 해당하는 데이터가 없습니다", "conditions": conditions, "data_type": data_type}
        response = {"status": "success", "data": data,
                    "message": "데이터 조회 성공", "conditions": conditions, "data_type": data_type}
        if dataset_context:
            response["dataset_context"] = dataset_context
        return response

    def _clean_sql(self, sql: str) -> str:
        """LLM 원응답에서 SQL 문 하나만 뽑아내 정제한다.

        프롬프트가 "SQL 끝에 세미콜론, 그 뒤엔 아무 것도 쓰지 말 것"을 지시하므로, 세미콜론이
        있으면 그 지점까지만 SQL로 인정하고 뒤는 버린다(2026-08-19) — LLM이 지시를 어기고
        CANNOT_ANSWER 사유 등 설명 문단을 SQL 뒤에 덧붙여도(가끔 실제로 그런다) 안전하게
        잘라낸다. 절 사이에 빈 줄을 넣는 등 SQL 자체의 줄바꿈 스타일과 무관하게 동작한다.
        세미콜론이 없으면(LLM이 지시를 어긴 경우) 빈 줄에서 끊는 보조 규칙으로 대신한다 —
        이 코드베이스의 생성 SQL은 보통 절 사이 빈 줄 없이 이어지므로, 빈 줄은 대개
        "SQL 끝, 설명 시작" 신호로 봐도 안전하다.
        """
        sql = sql.replace("```sql", "").replace("```", "").strip()

        if ';' in sql:
            sql = sql.split(';', 1)[0] + ';'
            lines = [line.strip() for line in sql.split('\n') if not line.strip().startswith('--')]
            return self._pretty_sql(' '.join(lines))

        lines = []
        started = False
        for raw_line in sql.split('\n'):
            line = raw_line.strip()
            if line.startswith('--'):
                continue
            if not line:
                if started:
                    break
                continue
            started = True
            lines.append(line)
        return self._pretty_sql(' '.join(lines))

    @staticmethod
    def _pretty_sql(sql: str) -> str:
        """실행·로그·화면 표시에 공통으로 쓸 수 있게 SQL을 절 단위로 줄바꿈해 보기 좋게 만든다.

        DB는 SQL 문의 개행을 그냥 무시하므로 실행에는 영향이 없다 — 표시용 버전을 따로 만들
        필요 없이 이 결과를 그대로 실행·저장·표시에 다 쓴다. 포맷 실패 시(예상 밖 구문 등)
        원본을 그대로 반환해 조용히 폴백한다.
        """
        try:
            import sqlparse
            return sqlparse.format(sql, reindent=True, keyword_case='upper', wrap_after=200).strip()
        except Exception:
            return sql

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
            "- SELECT/WHERE/GROUP BY/ORDER BY에 쓸 컬럼이 실제로 어느 뷰에 있는지 메타데이터에서 "
            "반드시 먼저 확인하세요. 지금 FROM 절에 쓴 뷰의 메타데이터에 그 컬럼이 없는데 다른(관련) "
            "뷰의 메타데이터에는 있다면, 그 컬럼은 그 다른 뷰에만 존재하는 것입니다 — 있는 것처럼 "
            "그냥 참조하지 말고 반드시 JOIN으로 가져오세요(예: 날짜 컬럼이 헤더 뷰에만 있고 "
            "금액 컬럼은 상세 뷰에 있는 경우, 두 뷰를 JOIN해야 함).\n"
            "- 코드값/상태값 등으로 조건절(WHERE)을 작성할 때, 메타데이터의 컬럼 설명이나 예시 쿼리에 그 값이 "
            "명시되어 있지 않다면 값을 임의로 짐작해서 비교하지 마세요. 짐작한 값으로 조건을 걸면 실제로는 "
            "존재하지 않는 값이라 결과가 0건이거나 잘못된 값으로 조용히 나올 수 있습니다.\n"
            "- 확실한 근거 없이 코드값을 짐작해야만 답변 가능한 질문이라면, 정확한 값을 확인할 수 없다는 뜻이므로 "
            "SELECT 'CANNOT_ANSWER' AS result, '조건에 사용할 정확한 코드값을 확인할 수 없습니다' AS reason 을 반환하세요.\n"
            "- 그룹별 비율/증감률 계산 시(예: 쇼핑몰별/브랜드별 감소율): 반드시 각 그룹 자신의 분자·분모로 계산할 것. "
            "상관관계 없는 서브쿼리, 전체 집계값, 다른 그룹의 값을 실수로 재사용해 여러 그룹의 결과가 우연히 "
            "동일한 값으로 나오지 않도록 GROUP BY와 집계 함수의 범위를 정확히 맞출 것.\n"
            "- 비율(%) 지표로 '상위 N개'를 뽑는 질문은, 분모(매출/거래건수 등 규모)가 아주 작은 그룹이 우연히 "
            "비율이 극단적으로 높게 나와 왜곡될 수 있으므로, 비율만 SELECT/정렬하지 말고 그 분모가 되는 규모 지표도 "
            "같이 SELECT할 것. 실제 조치(재협상/예산 재배치 등)를 결정하는 질문이면 정렬 기준을 비율이 아니라 "
            "그 비율의 절대 금액으로 ORDER BY 할 것.\n"
            "- '월별' 집계 시 '년'과 '월' 컬럼이 분리돼 있고 월 값이 연도 구분 없이 반복되면(01~12), 단순히 월로만 "
            "GROUP BY하면 서로 다른 연도의 같은 월이 합산됨. 질문에 특정 연도가 있으면 먼저 그 연도로 WHERE "
            "필터링 후 월별 집계, 연도가 명시되지 않았으면 년과 월을 함께 GROUP BY(또는 SELECT에 년 포함)할 것.\n"
            "- SQL 문 맨 끝에 반드시 세미콜론(;)을 붙일 것. 세미콜론 뒤에는 아무 것도 쓰지 말 것(설명·주석 절대 금지) "
            "— 응답 파싱이 첫 번째 세미콜론까지만 SQL로 인식하므로, 뒤에 뭘 붙여도 결과에는 반영되지 않는다."
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
            # service_code에 따라 get_llm_info가 model을 문자열이 아니라
            # {"fast":.., "balanced":.., "quality":..} 딕셔너리로 돌려줄 수 있다
            # (d2insight.engine._llm.chat()이 이미 이 경우를 처리하는 것과 같은 패턴).
            if isinstance(model, dict):
                model = model.get("balanced") or next(iter(model.values()))
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
                # NaN/Infinity(0으로 나누기 등으로 발생)는 표준 JSON으로 표현할 수 없어 응답
                # 직렬화 시 500 에러가 나므로, DB에서 나오는 시점에 None(null)으로 정리한다.
                # astype(object)로 먼저 바꾸지 않으면 float64 컬럼은 None을 다시 NaN으로 되돌린다.
                result_copy = result_copy.replace([np.inf, -np.inf], np.nan)
                result_copy = result_copy.astype(object).where(pd.notna(result_copy), None)
                data = result_copy.to_dict('records')

            # 금액성 숫자에 한글 표기(예: "6,815만원")를 미리 계산해 원본 숫자 옆에 끼워넣는다.
            # LLM이 긴 숫자를 직접 암산/타이핑하다 자릿수를 틀리는 것을 원천적으로 막기 위함.
            data = annotate_amounts(data)

            # 답변을 쓰는 에이전트가 데이터의 성격(설명/행 단위)을 보고 해석하도록 결과에 같이 실어준다.
            primary_meta = (table_metadata or {}).get(table_name, {}) if table_name else {}
            dataset_context = {
                "description": primary_meta.get("description"),
                "grain": primary_meta.get("grain"),
            }

            return self._create_standard_response(
                data=data,
                conditions={"question": question, "table_name": table_name, "generated_sql": sql_query},
                data_type="dynamic_query",
                dataset_context=dataset_context,
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
