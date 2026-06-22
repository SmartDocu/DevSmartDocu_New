"""Azure SQL adapter for AdventureWorks (dbo schema)."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from d2insight.data_source.base import DataSource, MonthRange


_SQL = """
SELECT
    FORMAT(soh.OrderDate, 'yyyy-MM')                      AS [월],
    CASE soh.OnlineOrderFlag
         WHEN 1 THEN N'온라인' ELSE N'오프라인' END        AS [채널],
    ISNULL(pc.Name,  N'미분류')                           AS [제품대분류],
    ISNULL(psc.Name, N'미분류')                           AS [제품중분류],
    p.Name                                                AS [제품],
    st.CountryRegionCode                                  AS [지역_Country],
    st.Name                                               AS [지역_Territory],
    SUM(sod.LineTotal)                                    AS [매출]
FROM dbo.SalesOrderHeader        AS soh
JOIN dbo.SalesOrderDetail        AS sod ON soh.SalesOrderID = sod.SalesOrderID
JOIN dbo.Product                 AS p   ON sod.ProductID    = p.ProductID
LEFT JOIN dbo.ProductSubcategory AS psc ON p.ProductSubcategoryID = psc.ProductSubcategoryID
LEFT JOIN dbo.ProductCategory    AS pc  ON psc.ProductCategoryID  = pc.ProductCategoryID
JOIN dbo.SalesTerritory          AS st  ON soh.TerritoryID  = st.TerritoryID
WHERE soh.OrderDate >= :start_date
  AND soh.OrderDate <  :end_date
GROUP BY
    FORMAT(soh.OrderDate, 'yyyy-MM'),
    soh.OnlineOrderFlag,
    pc.Name, psc.Name, p.Name,
    st.CountryRegionCode, st.Name
ORDER BY [월]
"""


def _build_engine() -> Engine:
    from d2shared import meta_loader
    url = meta_loader.get_connection_url()
    if not url:
        raise RuntimeError("Supabase에서 DB 연결 URL을 가져오지 못했습니다.")
    return create_engine(url, pool_pre_ping=True)


class AzureSqlSource(DataSource):
    def __init__(self) -> None:
        self._engine: Engine = _build_engine()

    def fetch_monthly_sales(self, months: MonthRange) -> pd.DataFrame:
        with self._engine.connect() as conn:
            df = pd.read_sql_query(
                sql=text(_SQL),
                con=conn,
                params={"start_date": months.start, "end_date": months.end},
            )
        missing = set(self.REQUIRED_COLUMNS) - set(df.columns)
        if missing:
            raise RuntimeError(f"Missing required columns in query result: {sorted(missing)}")
        return df[list(self.REQUIRED_COLUMNS)]

    def ping(self) -> str:
        """Quick connectivity check returning the SQL Server version."""
        with self._engine.connect() as conn:
            row = conn.execute(text("SELECT @@VERSION")).fetchone()
        return row[0] if row else ""
