"""보고서 에이전트 툴 모음 — LangChain @tool 데코레이터 기반."""
from d2insight.report.tools.query_tool import execute_query
from d2insight.report.tools.chart_tool import create_chart
from d2insight.report.tools.analysis_tools import run_stats, run_trend, run_outlier, ALL_ANALYSIS_TOOLS
from d2insight.report.tools.module_tools import (
    run_variance_impact, run_sales_bridge, run_pnl_waterfall, ALL_MODULE_TOOLS,
)

ALL_TOOLS = [execute_query, create_chart] + ALL_ANALYSIS_TOOLS + ALL_MODULE_TOOLS

__all__ = [
    "execute_query",
    "create_chart",
    "run_stats",
    "run_trend",
    "run_outlier",
    "ALL_ANALYSIS_TOOLS",
    "run_variance_impact",
    "run_sales_bridge",
    "run_pnl_waterfall",
    "ALL_MODULE_TOOLS",
    "ALL_TOOLS",
]
