"""Abstract base class for data sources.

Phase 1+: AzureSqlSource (매출 전용 고정 쿼리)
Phase 7+: GenericSqlSource (메타 기반 범용 SQL), CsvSource, ExcelSource

데이터 소스 종류에 관계없이 두 인터페이스를 통해 데이터를 가져온다:
  - fetch_monthly_sales(): 매출 전용 파이프라인용 (고정 컬럼 반환)
  - fetch(): 뷰/테이블 이름 기반 범용 조회 (로그·기타 데이터용)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class MonthRange:
    start: date  # inclusive, first day of the first month
    end: date    # exclusive, first day of the month AFTER the last included month


class DataSource(ABC):
    """공통 DataSource 인터페이스."""

    # 매출 파이프라인 전용 고정 컬럼
    REQUIRED_COLUMNS: tuple[str, ...] = (
        "월",
        "채널",
        "제품대분류",
        "제품중분류",
        "제품",
        "지역_Country",
        "지역_Territory",
        "매출",
    )

    @abstractmethod
    def fetch_monthly_sales(self, months: MonthRange) -> pd.DataFrame:
        """매출 전용 파이프라인용 고정 컬럼 DataFrame 반환."""
        raise NotImplementedError

    def fetch(
        self,
        view_name: str,
        start_date: date | None = None,
        end_date: date | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """범용 뷰/테이블 조회 — 서브클래스에서 필요 시 오버라이드.

        Args:
            view_name:  조회할 뷰 또는 테이블 이름.
            start_date: 시작일 (inclusive). None 이면 전체.
            end_date:   종료일 (exclusive). None 이면 전체.
            **kwargs:   소스별 추가 파라미터 (예: time_column 오버라이드).

        Returns:
            뷰 네이티브 컬럼 그대로의 DataFrame.
        """
        raise NotImplementedError(
            f"{type(self).__name__} 은(는) fetch() 를 구현하지 않습니다."
        )
