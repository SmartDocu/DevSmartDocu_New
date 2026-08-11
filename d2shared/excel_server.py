"""
excel_server.py
업로드된 엑셀/CSV/API 데이터를 세션별로 보관하고, 자연어 질문을 pandas 코드 실행으로 처리하는 서버.
d2chat·d2insight 공용 — DB 의존 없음.

MCPServer(SQL 생성/실행)와 동일한 역할을 업로드 데이터에 대해 수행한다.
데이터셋이 여러 개(다중 시트/다중 파일)인 경우 앱별로 주입되는 classifier_fn(question, llm, metadata, log_ctx)을
사용해 PRIMARY 데이터셋 하나를 고른 뒤, DB의 TableMeta.reference(child_table/parent_table)
패턴과 동일하게 그 데이터셋의 metadata["reference"](조인 힌트)에 연결된 데이터셋들을 자동으로
함께 선택한다. 실제 데이터 가공(필요시 pd.merge 포함)은 excel_code_engine.run_pandas_code()에 위임한다.
"""
import re
import json
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
from pydantic import BaseModel, Field

from d2shared.excel_code_engine import run_pandas_code
from d2shared.llm_logger import log_llm_call

MAX_JOIN_DATASETS = 3
MAX_CATEGORY_VALUES = 20  # 이 개수 이하로 고유값이 적은 컬럼만 "범주형 컬럼"으로 보고 실제값을 전부 기록


def _extract_category_values(df: pd.DataFrame, nunique: Dict[str, int]) -> Dict[str, List[str]]:
    """값 종류가 적은(저카디널리티) 모든 컬럼의 실제 고유값 목록을 뽑아낸다 (컬럼명과 무관하게 자동 판별).
    LLM이 pandas 필터링 코드를 짤 때 샘플 몇 행만 보고 상태/구분값 등을 추측하다 실제 표기와
    달라 조용히 0건이 나오는 것을 막기 위해, 업로드 시점에 1회만 계산해 메타데이터에 저장해둔다."""
    category_values: Dict[str, List[str]] = {}
    for col, n in nunique.items():
        if n == 0 or n > MAX_CATEGORY_VALUES:
            continue
        if str(df[col].dtype) not in ("object", "bool", "category"):
            continue
        try:
            values = sorted(str(v) for v in df[col].dropna().unique().tolist())
            category_values[col] = values
        except Exception:
            continue
    return category_values


def _generate_dataset_metadata(llm, df: pd.DataFrame, dataset_key: str, log_ctx: Optional[Dict] = None) -> Dict:
    """컬럼명/dtype/샘플값을 보고 LLM이 데이터셋 설명 메타데이터를 생성한다."""
    columns = list(df.columns.astype(str))
    dtypes = {col: str(dtype) for col, dtype in zip(columns, df.dtypes)}
    try:
        nunique = {col: int(df[col].nunique()) for col in df.columns}
    except Exception:
        nunique = {}
    category_values = _extract_category_values(df, nunique)
    sample = df.head(5).to_dict(orient="records")

    prompt = f"""다음은 사용자가 업로드한 데이터셋 "{dataset_key}"의 정보입니다.

컬럼: {columns}
컬럼별 데이터 타입: {dtypes}
컬럼별 고유값 개수: {nunique}
샘플 데이터(최대 5행): {json.dumps(sample, ensure_ascii=False, default=str)}

이 데이터를 보고 아래 JSON 형식으로 메타데이터를 작성하세요. 설명 없이 JSON만 출력하세요.

{{
  "description": "이 데이터셋이 무엇에 대한 데이터인지 한 문장 설명",
  "purpose": "이 데이터로 어떤 질문에 답할 수 있는지",
  "columns": {{
    "실제컬럼명1": "이 컬럼이 의미하는 것에 대한 간단한 한글 설명",
    "실제컬럼명2": "..."
  }}
}}
"""
    metadata = None
    try:
        start = datetime.now()
        response = llm.invoke(prompt)
        end = datetime.now()

        usage = getattr(response, "usage_metadata", None) or {}
        log_llm_call(
            log_ctx=log_ctx,
            stepnm="excel_metadata_generate",
            steptitle="업로드 데이터 메타데이터 생성",
            llmmodelnm=getattr(llm, "model", "unknown"),
            inputtoken=usage.get("input_tokens", 0),
            outputtoken=usage.get("output_tokens", 0),
            is_success=True,
            startdts=start,
            enddts=end,
        )

        text = response.content.strip()
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
        json_str = match.group(1) if match else text
        metadata = json.loads(json_str)
    except Exception as e:
        # print(f"[WARN] 데이터셋 메타데이터 생성 실패: {e}")
        metadata = {}

    if not isinstance(metadata, dict):
        metadata = {}
    metadata.setdefault("description", dataset_key)
    metadata.setdefault("purpose", "업로드된 데이터 조회")
    metadata.setdefault("columns", {c: c for c in columns})
    metadata["category_values"] = category_values
    return metadata


class _DatasetRelation(BaseModel):
    dataset: str = Field(description="조인 가능한 기존 데이터셋의 이름(정확히 일치)")
    left_on: str = Field(description="새 데이터셋 쪽 조인 컬럼명")
    right_on: str = Field(description="기존 데이터셋 쪽 조인 컬럼명")


class _DatasetRelations(BaseModel):
    relations: List[_DatasetRelation] = Field(default_factory=list, description="조인 가능한 관계 목록 (없으면 빈 리스트)")


def _infer_join_relationships(
    llm,
    new_key: str,
    new_df: pd.DataFrame,
    existing_datasets: Dict[str, Dict],
    log_ctx: Optional[Dict] = None,
) -> List[Dict]:
    """새로 등록되는 데이터셋과 같은 세션의 기존 데이터셋들 사이에 조인 가능한 공통 키가 있는지 LLM으로 추론한다.
    반환: [{"dataset": 기존_데이터셋_키, "left_on": 새_데이터셋_컬럼, "right_on": 기존_데이터셋_컬럼}, ...]"""
    if not existing_datasets:
        return []

    new_columns = list(new_df.columns.astype(str))
    others_desc = []
    for key, info in existing_datasets.items():
        other_df = info["df"]
        others_desc.append({
            "dataset": key,
            "columns": list(other_df.columns.astype(str)),
            "sample": other_df.head(2).to_dict(orient="records"),
        })

    prompt = f"""다음은 같은 세션에 업로드된 데이터셋들입니다.

**새로 업로드된 데이터셋 "{new_key}"**
컬럼: {new_columns}
샘플(최대 2행): {json.dumps(new_df.head(2).to_dict(orient="records"), ensure_ascii=False, default=str)}

**기존에 업로드된 데이터셋들**
{json.dumps(others_desc, ensure_ascii=False, default=str)}

새 데이터셋과 기존 데이터셋들 중, 같은 대상(예: 같은 ID/코드/이름)을 가리키는 공통 조인 컬럼이 있는지 판단하세요.
컬럼명이 다르더라도 의미가 같으면(예: "고객ID"와 "customer_id") 조인 가능하다고 판단합니다.
확실하지 않으면 포함하지 마세요. 조인 가능한 기존 데이터셋마다 하나씩 관계를 반환하세요.
"""
    try:
        structured_llm = llm.with_structured_output(_DatasetRelations, include_raw=True)
        start = datetime.now()
        raw = structured_llm.invoke(prompt)
        end = datetime.now()

        result = raw.get('parsed') if isinstance(raw, dict) else raw
        raw_msg = raw.get('raw') if isinstance(raw, dict) else None
        usage = getattr(raw_msg, 'usage_metadata', None) or {}
        log_llm_call(
            log_ctx=log_ctx,
            stepnm="excel_relation_infer",
            steptitle="업로드 데이터 조인 관계 추론",
            llmmodelnm=getattr(llm, "model", "unknown"),
            inputtoken=usage.get("input_tokens", 0),
            outputtoken=usage.get("output_tokens", 0),
            is_success=True,
            startdts=start,
            enddts=end,
        )

        if result is None:
            return []
        relations = [
            {"dataset": r.dataset, "left_on": r.left_on, "right_on": r.right_on}
            for r in result.relations
            if r.dataset in existing_datasets
        ]
        return relations
    except Exception as e:
        # print(f"[WARN] 데이터셋 조인 관계 추론 실패: {e}")
        return []


class ExcelServer:
    """업로드된 엑셀/CSV/API 데이터를 세션별로 보관/질의하는 서버"""

    def __init__(self):
        self.session_datasets: Dict[str, Dict[str, Dict]] = {}

    def register_dataset(
        self,
        session_id: str,
        dataset_key: str,
        df: pd.DataFrame,
        filename: str,
        sheet_name: Optional[str],
        llm,
        log_ctx: Optional[Dict] = None,
    ) -> Tuple[str, Dict]:
        """데이터셋을 세션에 등록하고 (최종 데이터셋 키, 생성된 메타데이터)를 반환한다.
        같은 세션에 동일 key가 이미 있으면 숫자 접미사를 붙여 누적 등록한다."""
        session_datasets = self.session_datasets.setdefault(session_id, {})

        key = dataset_key
        suffix = 2
        while key in session_datasets:
            key = f"{dataset_key}_{suffix}"
            suffix += 1

        metadata = _generate_dataset_metadata(llm, df, key, log_ctx=log_ctx)

        relations = _infer_join_relationships(llm, key, df, session_datasets, log_ctx=log_ctx)
        metadata["reference"] = relations

        # 기존 데이터셋 쪽에도 새 데이터셋으로의 역방향 조인 힌트를 추가 (양방향 탐색 가능하도록)
        for rel in relations:
            other_meta = session_datasets[rel["dataset"]]["metadata"]
            other_refs = other_meta.get("reference") or []
            other_refs.append({"dataset": key, "left_on": rel["right_on"], "right_on": rel["left_on"]})
            other_meta["reference"] = other_refs

        session_datasets[key] = {
            "df": df,
            "metadata": metadata,
            "filename": filename,
            "sheet_name": sheet_name,
        }
        return key, metadata

    def get_session_datasets(self, session_id: str) -> Dict[str, Dict]:
        """세션에 등록된 전체 데이터셋의 메타데이터 반환 (classifier_fn에 바로 사용 가능)"""
        return {k: v["metadata"] for k, v in self.session_datasets.get(session_id, {}).items()}

    def has_datasets(self, session_id: str) -> bool:
        return bool(self.session_datasets.get(session_id))

    def clear_session(self, session_id: str) -> None:
        self.session_datasets.pop(session_id, None)

    def _response(self, status: str, data, message: str, question: str, dataset_key: Optional[str], code: Optional[str] = None) -> Dict:
        return {
            "status": status,
            "data": data,
            "message": message,
            "conditions": {
                "question": question,
                "table_name": dataset_key,
                "generated_sql": code,
            },
            "data_type": "excel_query",
        }

    def _resolve_related_datasets(self, primary_key: str, datasets: Dict[str, Dict]) -> List[str]:
        """PRIMARY 데이터셋의 reference(조인 힌트)를 따라 연결된 데이터셋들을 함께 선택한다.
        DB 쪽 query_tool.py가 reference.child_table/parent_table로 관련 테이블 하나를 자동 포함하는 것과
        동일한 패턴이며, 여기서는 여러 관계를 최대 MAX_JOIN_DATASETS개까지 포함한다."""
        selected = [primary_key]
        for rel in (datasets[primary_key]["metadata"].get("reference") or []):
            other_key = rel.get("dataset")
            if other_key and other_key in datasets and other_key not in selected:
                selected.append(other_key)
                if len(selected) >= MAX_JOIN_DATASETS:
                    break
        return selected

    def _collect_relations(self, selected_keys: List[str], datasets: Dict[str, Dict]) -> List[Dict]:
        """선택된 데이터셋들 사이의 조인 힌트를 중복 없이 모아 run_pandas_code 프롬프트에 전달할 형태로 반환"""
        relations = []
        seen = set()
        for key in selected_keys:
            for rel in (datasets[key]["metadata"].get("reference") or []):
                other = rel.get("dataset")
                if other in selected_keys and other != key:
                    pair = tuple(sorted([key, other]))
                    if pair in seen:
                        continue
                    seen.add(pair)
                    relations.append({
                        "left": key, "left_on": rel.get("left_on"),
                        "right": other, "right_on": rel.get("right_on"),
                    })
        return relations

    def execute_natural_language_query(
        self,
        question: str,
        session_id: str,
        llm,
        classifier_fn: Callable,
        current_date_info: Optional[Dict] = None,
        log_ctx: Optional[Dict] = None,
    ) -> Dict:
        """자연어 질문을 pandas 코드로 변환하여 업로드된 데이터에 대해 실행.
        PRIMARY 데이터셋 하나를 고른 뒤, 그 데이터셋의 reference에 연결된 데이터셋들을 함께 선택해
        2개 이상의 DataFrame이 필요한 조인/머지 질문도 처리한다.

        classifier_fn: (question, llm, tables_metadata, log_ctx) -> dict
                       'is_answerable', 'table', 'suggestion' 키를 포함한 dict 반환 (앱별 주입)
        """
        datasets = self.session_datasets.get(session_id) or {}
        if not datasets:
            return self._response(
                "no_dataset", {"error": "업로드된 데이터가 없습니다."},
                "업로드된 데이터가 없습니다. 먼저 엑셀 또는 CSV 파일을 업로드해주세요.",
                question, None,
            )

        # 데이터셋이 1개뿐이어도 이 질문이 실제로 데이터 내용을 묻는 것인지(is_answerable) 항상 판별한다.
        # (그래프 표현 방식에 대한 피드백처럼 데이터 조회가 아닌 질문을 pandas 코드로 억지로
        #  답하려다 엉뚱한 "데이터에 없습니다" 답변이 나오는 것을 막기 위함 — 데이터셋이 여러 개일
        #  때만 판별하던 이전 로직의 공백을 메움)
        tables_metadata = {k: v["metadata"] for k, v in datasets.items()}
        classification = classifier_fn(question, llm, tables_metadata, log_ctx=log_ctx)
        if not classification.get("is_answerable"):
            return self._response(
                "not_answerable", [],
                classification.get("suggestion") or "질문에 맞는 데이터셋을 찾지 못했습니다.",
                question, None,
            )

        if len(datasets) == 1:
            primary_key = next(iter(datasets))
        else:
            primary_key = classification.get("table") or next(iter(datasets))
            if primary_key not in datasets:
                primary_key = next(iter(datasets))

        selected_keys = self._resolve_related_datasets(primary_key, datasets)
        dfs = {k: datasets[k]["df"] for k in selected_keys}
        columns_by_dataset = {
            k: (datasets[k]["metadata"].get("columns") or {c: c for c in datasets[k]["df"].columns})
            for k in selected_keys
        }
        category_values_by_dataset = {
            k: (datasets[k]["metadata"].get("category_values") or {})
            for k in selected_keys
        }
        relations = self._collect_relations(selected_keys, datasets)

        result = run_pandas_code(
            llm, dfs, question, columns_by_dataset, current_date_info,
            relations=relations, category_values_by_dataset=category_values_by_dataset, log_ctx=log_ctx,
        )

        return self._response(
            result["status"], result.get("data"), result.get("message"),
            question, ",".join(selected_keys), code=result.get("code"),
        )
