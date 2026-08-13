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
from d2shared.amount_format import annotate_amounts

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


def extract_dataframe_facts(df: pd.DataFrame) -> Dict:
    """LLM에게 맡기지 않고 pandas로 직접 뽑아낸 사실(fact) 정보.
    메타데이터 생성 프롬프트에 근거로 주입해, LLM이 컬럼 값/통계를 지어내지 않고
    실측 데이터를 그대로 참조하게 하기 위함 (특히 컬럼 값 매핑의 환각 방지)."""
    facts: Dict = {"row_count": len(df)}

    facts["dtypes"] = {col: str(df[col].dtype) for col in df.columns}

    facts["column_values"] = {}
    for col in df.columns:
        try:
            if df[col].nunique() <= 30:
                facts["column_values"][col] = df[col].dropna().unique().tolist()
        except Exception:
            continue

    try:
        facts["null_ratio"] = (df.isnull().sum() / len(df)).round(3).to_dict() if len(df) else {}
    except Exception:
        facts["null_ratio"] = {}

    try:
        num_cols = df.select_dtypes(include="number").columns.tolist()
        facts["numeric_stats"] = df[num_cols].agg(["min", "max", "mean"]).round(2).to_dict() if num_cols else {}
    except Exception:
        facts["numeric_stats"] = {}

    return facts


def _generate_dataset_metadata(llm, df: pd.DataFrame, dataset_key: str, log_ctx: Optional[Dict] = None) -> Dict:
    """실측 사실(facts)을 pandas로 먼저 뽑아 프롬프트에 근거로 주입하고, LLM은 그 사실을 바탕으로
    DB TableMeta와 동일한 수준(grain/primary_key/컬럼 값 매핑 등)의 메타데이터를 추론해 생성한다.
    DB 메타에 없는 항목(분석 패턴, 파생 지표 계산식 등)은 LLM의 판단 폭을 좁히므로 넣지 않는다."""
    columns = list(df.columns.astype(str))
    facts = extract_dataframe_facts(df)
    sample = df.head(5).to_dict(orient="records")

    prompt = f"""다음은 사용자가 업로드한 데이터셋 "{dataset_key}"의 실측 정보입니다.

[실측 정보]
- 총 행 수: {facts['row_count']}
- 컬럼 목록: {columns}
- 컬럼별 dtype: {json.dumps(facts['dtypes'], ensure_ascii=False, default=str)}
- 고유값 목록 (30개 이하 컬럼만): {json.dumps(facts['column_values'], ensure_ascii=False, default=str)}
- 숫자 컬럼 통계(min/max/mean): {json.dumps(facts['numeric_stats'], ensure_ascii=False, default=str)}
- 결측치 비율: {json.dumps(facts['null_ratio'], ensure_ascii=False, default=str)}
- 상위 5행 샘플: {json.dumps(sample, ensure_ascii=False, default=str)}

위 실측 정보를 분석하여 아래 JSON 형식으로 메타데이터를 생성하세요.
실측 정보에 없는 내용은 추론하되, 불확실하면 null로 남기세요. 절대 사실과 다른 값을 지어내지 마세요.
설명 없이 JSON만 출력하세요.

{{
  "description": "이 데이터셋이 무엇인지 한 문장 설명",
  "grain": "1행이 무엇을 의미하는지. 예: 쇼핑몰×브랜드×년×월당 1행",
  "primary_key": ["행을 유일하게 식별하는 컬럼 목록 (추정)"],
  "default_time_column": "시간 기준 컬럼명. 없으면 null",
  "purpose": ["이 데이터로 답할 수 있는 분석 목적 3~5개"],
  "query_examples": ["사용자가 실제로 할 법한 질문 5개"],
  "columns": {{
    "컬럼명": {{
      "logical_name": "사람이 읽기 쉬운 이름",
      "data_type": "identifier | number | currency | string | date | ratio | boolean",
      "aliases": ["사용자가 다르게 부를 수 있는 이름 목록. 없으면 생략"],
      "values": {{
        "실제저장값": {{"logical_name": "사람이 읽기 쉬운 이름", "aliases": ["필요한 경우만"]}}
      }}
    }}
  }},
  "reference": []
}}

[values 작성 규칙 - 중요]
- "고유값 목록"에 있는 컬럼만 values를 채우세요. 그 목록에 없는 값을 추가하지 마세요.
- 실제 저장값과 사용자가 부를 법한 이름이 다를 때만 항목을 작성하세요. 저장값과 사용자 호칭이 동일하면 그 값은 values에 넣지 마세요.
  예) 저장값 "2025" -> 사용자도 그대로 "2025년"이라고 부를 것이므로 values에 넣지 않음
  예) 저장값 "G마켓" -> 사용자가 "지마켓"이라고 부를 수 있으므로 aliases에 추가
  예) 저장값 "01월" -> 사용자가 "1월"이라고 부를 수 있으므로 aliases에 추가
- 고유값이 30개를 초과하는 컬럼(예: 브랜드명이 100개인 경우)이나, 모든 값이 저장값=사용자 호칭인 컬럼은 values를 {{}}로 남기세요.
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
    metadata.setdefault("grain", None)
    metadata.setdefault("primary_key", [])
    metadata.setdefault("default_time_column", None)
    metadata.setdefault("purpose", ["업로드된 데이터 조회"])
    metadata.setdefault("query_examples", [])
    metadata.pop("analysis_patterns", None)
    metadata.setdefault(
        "columns",
        {c: {"logical_name": c, "data_type": "string", "aliases": [], "values": {}} for c in columns},
    )

    # LLM이 놓치거나 지어낼 수 있는 저카디널리티 컬럼의 실제값을, 코드로 직접 계산한 결정론적
    # 목록으로 별도 저장해둔다 (excel_code_engine._build_prompt의 category_text에 사용 —
    # 컬럼별 columns[col].values와는 별개의 안전망).
    try:
        nunique = {col: int(df[col].nunique()) for col in df.columns}
    except Exception:
        nunique = {}
    metadata["category_values"] = _extract_category_values(df, nunique)
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

    def _response(
        self, status: str, data, message: str, question: str, dataset_key: Optional[str],
        code: Optional[str] = None, dataset_context: Optional[Dict] = None,
    ) -> Dict:
        response = {
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
        if dataset_context:
            response["dataset_context"] = dataset_context
        return response

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
        # grain/primary_key 등 컬럼 단위를 넘어서는 메타데이터는 별도로 모아
        # run_pandas_code의 프롬프트에 함께 전달한다 (조인/집계 시 중복 집계 방지).
        meta_by_dataset = {
            k: {
                "grain": datasets[k]["metadata"].get("grain"),
                "primary_key": datasets[k]["metadata"].get("primary_key"),
            }
            for k in selected_keys
        }
        relations = self._collect_relations(selected_keys, datasets)

        result = run_pandas_code(
            llm, dfs, question, columns_by_dataset, current_date_info,
            relations=relations, category_values_by_dataset=category_values_by_dataset,
            meta_by_dataset=meta_by_dataset, log_ctx=log_ctx,
        )

        # 답변을 쓰는 메인 에이전트도 데이터의 성격(설명/행 단위)을 보고 해석하도록 결과에 같이 실어준다.
        primary_meta = datasets[primary_key]["metadata"]
        dataset_context = {
            "description": primary_meta.get("description"),
            "grain": primary_meta.get("grain"),
        }

        # 금액성 숫자에 한글 표기(예: "6,815만원")를 미리 계산해 원본 숫자 옆에 끼워넣는다.
        # LLM이 긴 숫자를 직접 암산/타이핑하다 자릿수를 틀리는 것을 원천적으로 막기 위함.
        annotated_data = annotate_amounts(result.get("data"))

        return self._response(
            result["status"], annotated_data, result.get("message"),
            question, ",".join(selected_keys), code=result.get("code"),
            dataset_context=dataset_context,
        )
