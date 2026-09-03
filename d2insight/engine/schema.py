"""스키마 해석기 — 모듈이 컬럼명 대신 **역할**로 데이터를 찾게 한다 (§7.3).

모듈이 "매출"·"수량"·"제품"·"고객" 같은 컬럼명을 코드에 박으면 그 모듈은 그 데이터셋 전용이 된다.
구매분석(구매액·발주수량·공급사)이나 생산분석(생산량·설비)에서는 깨지거나 — 더 나쁘게 — 조용히 0을 낸다.

그래서 **도메인 지식은 코드가 아니라 데이터소스 정의에 둔다.**

    datasources/<source>.json  →  meta_columns(§1)  →  이 해석기  →  모듈

역할(semantic)은 도메인 중립어다. '상품·고객'은 판매 도메인에서 item·party가 불리는 이름일 뿐이다.

    amount      금액        판매: 매출     / 구매: 구매액   / 생산: 생산액
    quantity    물량        판매: 판매수량 / 구매: 발주수량 / 생산: 생산량
    discount    할인·에누리
    cost        매출원가(COGS)
    opex        판매관리비
    inventory   재고 잔량 (기말재고)
    inbound     입고 (생산·매입)
    outbound    출고 (판매·소비)
    item        무엇을      판매: 상품     / 구매: 품목     / 생산: 제품
    party       누구와      판매: 고객     / 구매: 공급사   / 생산: 설비·라인
    item_group  무엇의 상위 분류 (대분류·모델 등)
    region      어디서      지역·국가·권역 등 지리적 구분
    period      이력 패널의 기간 컬럼

손익·재고 역할은 **대부분의 데이터소스에 없다.** 없으면 해당 모듈이 명시적으로 실패하고(§11 Step 2),
데이터소스 정의에 역할을 선언하는 순간 모듈 코드 변경 없이 동작한다.

보고서에 찍히는 이름은 `logical_name(col)`로 가져온다 → 구매분석이면 자동으로 "구매액·공급사"가 된다.

역할이 없는 컬럼도 정상이다(채널 등). 분석 차원으로는 쓰이되 역할 기반 계산에는 쓰이지 않는다.
모듈은 필요한 역할이 없으면 **명시적으로 생략**한다(예: quantity 없으면 Sales Bridge 생략, 방침 §13).
조용히 0으로 처리하지 않는다.
"""
from __future__ import annotations

import pandas as pd

# 측정(Measure) 역할
ROLE_AMOUNT = "amount"
ROLE_QUANTITY = "quantity"
ROLE_DISCOUNT = "discount"

# 손익 역할 — 선언된 데이터소스에서만 손익 분석이 가능하다.
ROLE_COST = "cost"          # 매출원가(COGS)   판매: 매출원가 / 구매: 매입원가
ROLE_OPEX = "opex"          # 판매관리비

# 재고 역할 — 재고 데이터를 담은 데이터소스에서만 재고 분석이 가능하다.
ROLE_INVENTORY = "inventory"   # 재고 잔량(기말재고 금액 또는 수량)
ROLE_INBOUND = "inbound"       # 입고(생산·매입)
ROLE_OUTBOUND = "outbound"     # 출고(판매·소비)
ROLE_SAFETY_STOCK = "safety_stock"  # 항목별 안전재고 목표치(회사 정책값, 데이터에 이미 정의된 경우)

# 차원(Dimension) 역할
ROLE_ITEM = "item"              # 무엇을 (상품·품목·제품)
ROLE_PARTY = "party"            # 누구와 (고객·공급사·설비)
ROLE_ITEM_GROUP = "item_group"  # 무엇의 상위 분류
ROLE_REGION = "region"          # 어디서 (지역·국가·권역)
ROLE_PERIOD = "period"          # 이력 패널의 기간 컬럼

# 역할을 판정하는 곳이 둘이다 — 등록된 DB 메타(pipeline/meta_roles.py)와 업로드 파일
# (upload_meta.py). 두 곳이 같은 목록·같은 설명을 쓰도록 여기 하나만 둔다. 예전에 각자
# 목록을 들고 있어 업로드 경로에만 region이 빠져 있었다(2026-09-02).
ROLE_GUIDE = """  amount        합산 가능한 거래 금액(매출·판매액 등). 단가·비율처럼 합산하면 안 되는 값은 제외
  quantity      합산 가능한 수량
  discount      할인·에누리액
  cost          매출원가·매입원가
  opex          판매관리비
  inventory     재고 잔량
  inbound       입고(생산·매입)
  outbound      출고(판매·소비)
  safety_stock  안전재고 목표치
  item          분석의 최소 단위 항목(상품·품목·설비 등)
  item_group    item의 상위 분류
  party         거래 상대(고객·거래처·공급사)
  region        지역·국가·권역
  period        기준 기간(날짜) 컬럼"""

ALL_ROLES: set[str] = {line.split()[0] for line in ROLE_GUIDE.strip().splitlines()}

# 합산할 숫자가 없는 데이터(로그·검사이력 등 행 하나가 사건 하나인 데이터)에서 쓰는 측정값.
# period_dataset이 데이터에 이 컬럼(값 1)과 meta 한 줄을 넣어주면, 모듈은 평소처럼
# groupby(...).sum()을 하면서 자연히 행을 세게 된다 — 모듈을 고치지 않는다.
COUNT_MEASURE = "_건수"
COUNT_MEASURE_LABEL = "건수"


class SchemaError(Exception):
    """meta_columns가 없거나 필수 정보가 빠진 경우."""


class Schema:
    """meta_columns 한 장을 역할 기준으로 조회한다."""

    def __init__(self, meta: pd.DataFrame) -> None:
        self._meta = meta

    # ── 기본 구성 ────────────────────────────────────────────────────────────
    @property
    def dimensions(self) -> list[str]:
        """분석에 쓰는 차원. 기간(period) 컬럼과, 값이 거의 다 달라 묶어 비교할 수 없는
        컬럼(Is_Groupable=False)은 제외한다."""
        dims = self._meta[self._meta["Field_Type"] == "Dim"]
        if "Semantic_Type" in dims.columns:
            dims = dims[dims["Semantic_Type"] != ROLE_PERIOD]
        if "Is_Groupable" in dims.columns:
            dims = dims[dims["Is_Groupable"] != False]  # noqa: E712
        return dims["Physical_Name"].tolist()

    @property
    def causal_dimensions(self) -> list[str]:
        """dimensions 중 실제 판매 축(브랜드·지역·채널 등)만 — 법인·부서 같은 관리/회계용
        구분은 매출 변화의 "원인"으로 보기엔 부적절해 인과분석(dimension_impact 등)에서 뺀다.
        현황 서술(actual_aggregate 등)은 이 필터 없이 dimensions를 그대로 쓴다."""
        dims = self.dimensions
        if "Is_Market_Axis" not in self._meta.columns:
            return dims
        admin = set(self._meta.loc[self._meta["Is_Market_Axis"] == False, "Physical_Name"])  # noqa: E712
        return [d for d in dims if d not in admin]

    @property
    def measures(self) -> list[str]:
        return self._meta.loc[self._meta["Field_Type"] == "Measure", "Physical_Name"].tolist()

    @property
    def key_measure(self) -> str:
        """분석 기준 측정값. 선언이 없으면 첫 Measure를 쓴다."""
        if "Is_Key_Measure" in self._meta.columns:
            key = self._meta.loc[self._meta["Is_Key_Measure"] == True, "Physical_Name"]  # noqa: E712
            if len(key):
                return str(key.iloc[0])
        measures = self.measures
        if not measures:
            raise SchemaError("meta_columns에 Measure가 하나도 없습니다.")
        return measures[0]

    # ── 역할 조회 ────────────────────────────────────────────────────────────
    def column(self, role: str) -> str | None:
        """역할에 해당하는 컬럼 하나. 없으면 None(생략 여부는 모듈이 판단한다)."""
        cols = self.columns(role)
        return cols[0] if cols else None

    def columns(self, role: str) -> list[str]:
        """역할에 해당하는 컬럼 전부."""
        if "Semantic_Type" not in self._meta.columns:
            return []
        return self._meta.loc[self._meta["Semantic_Type"] == role, "Physical_Name"].tolist()

    def has(self, role: str) -> bool:
        return self.column(role) is not None

    def item_fallback_columns(self) -> list[str]:
        """품목(item)이 없을 때 대신 쓸 후보(item_group/party/region) 중 실제로 있는 것 전부."""
        cols: list[str] = []
        for role in (ROLE_ITEM_GROUP, ROLE_PARTY, ROLE_REGION):
            col = self.column(role)
            if col and col not in cols:
                cols.append(col)
        return cols

    # ── 표시명 ───────────────────────────────────────────────────────────────
    def logical_name(self, physical: str) -> str:
        """보고서에 찍을 이름. 없으면 물리명 그대로."""
        hit = self._meta.loc[self._meta["Physical_Name"] == physical, "Logical_Name"]
        return str(hit.iloc[0]) if len(hit) else physical

    def role_name(self, role: str) -> str | None:
        """역할을 맡은 컬럼의 표시명 (예: party → '고객' / '공급사')."""
        col = self.column(role)
        return self.logical_name(col) if col else None


def get_schema(ctx) -> Schema:
    """공유 컨텍스트의 meta_columns로 스키마를 만든다."""
    meta = ctx.get("meta_columns")
    if meta is None or not len(meta):
        raise SchemaError("meta_columns가 없습니다. period_dataset이 먼저 실행되어야 합니다.")
    return Schema(meta)
