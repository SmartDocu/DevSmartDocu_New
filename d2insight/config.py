"""d2insight 분석 파라미터 및 LLM 모델 등급.

DB/Supabase/LLM API 키 등 환경설정은 backend.app.config.settings 로 일원화되어
있으므로 여기서는 다루지 않는다 (d2chat과 동일한 컨벤션).
"""
from typing import Literal

Grade = Literal["fast", "balanced", "quality"]

# --- LLM 모델 등급 (벤더별) ---
# fast: 인텐트 파싱/분류, balanced: 보고서 본문 스텝, quality: 결론/핵심 인사이트
# 벤더는 DB에서 결정, 모델은 아래 LLM_MODELS에서 결정
# LLM_MODELS: dict[str, dict[str, str]] = {
#     "Anthropic": {
#         "fast": "claude-haiku-4-5-20251001",
#         "balanced": "claude-sonnet-4-6",
#         "quality": "claude-opus-4-8",
#     },
#     "OpenAI": {
#         "fast":     "gpt-4.1-mini",
#         "balanced": "gpt-4.1",
#         "quality":  "gpt-4.1",
#     },
#     "Google": {
#         "fast":     "gemini-2.0-flash",
#         "balanced": "gemini-2.5-pro",
#         "quality":  "gemini-2.5-pro",
#     },
# }
LLM_MODELS: dict[str, dict[str, str]] = {
    "Anthropic": {
        "fast":     "claude-haiku-4-5-20251001",
        "balanced": "claude-haiku-4-5-20251001",
        "quality":  "claude-haiku-4-5-20251001",
    },
    "OpenAI": {
        "fast":     "gpt-4.1-mini",
        "balanced": "gpt-4.1",
        "quality":  "gpt-4.1",
    },
    "Google": {
        "fast":     "gemini-2.0-flash",
        "balanced": "gemini-2.5-pro",
        "quality":  "gemini-2.5-pro",
    },
}



# --- 병렬 보고서 생성 ---
REPORT_MAX_WORKERS: int = 4  # 스텝 병렬 실행 스레드 수

# --- Data source selection ---
DATA_SOURCE = "db"  # db | csv | excel (현재 db만 지원)

# --- Output ---
# 한글 폰트 ttf 경로. 미지정 시 OS 기본 위치(Win: malgun.ttf, Linux: NanumGothic)를 자동 탐색.
REPORT_FONT_PATH = ""

# --- Analysis params ---
ABC_THRESHOLDS = (0.70, 0.90)
XYZ_THRESHOLDS = (0.20, 0.50)
ANALYSIS_TARGETS = ["AZ", "AX", "AY", "BZ"]
SHAPLEY_ITERATIONS = 500
TOP_N_MAX = 5
PARETO_THRESHOLD = 0.80
MIN_CONTRIBUTION = 0.05
DRILLDOWN_DEPTH = 2
DRILLDOWN_MIN_CELL_SHARE = 0.001  # 0.1% of total filtered revenue
DIMENSIONS = ["채널", "제품대분류", "제품중분류", "지역"]
REGION_LEVEL = "Country"  # 드릴다운에서는 Territory Name까지

# Supplementary analysis (Phase 4)
NEW_DISC_HIGH_IMPACT_RATIO = 0.30   # 신규/단종 비중 ≥ 30% → high_impact 플래그
OUTLIER_CHANGE_PCT = 0.30           # ±30% 변화 (설계서 ±50% 에서 강화)
OUTLIER_MIN_REVENUE_SHARE = 0.01    # 항목 매출이 당월 총매출의 ≥1%

# AnomalyDetector 심각도 임계값 (달성률 = 당월/전월)
ANOMALY_SURGE_CRITICAL = 2.00   # ≥200% → 데이터 오류 의심
ANOMALY_NORMAL_HIGH = 1.10      # >110% → 상승 이상치
ANOMALY_NORMAL_LOW = 0.90       # ≥90%  → 정상 하한
ANOMALY_CRITICAL = 0.70         # ≥70%  → 주의 / <70% → 심각

# dataset_builder 이상징후 기준 (±N × σ)
ANOMALY_SIGMA: float = 3.0      # 기본 ±3σ (보고서작성방안 기준)

# dataset_builder 비교 기간 기본값 ("MoM" | "YoY" | "QoQ")
COMPARE_TYPE: str = "MoM"

# --- 이력(history) 구간 — 신규/이탈 생애주기 판정과 추이 분석 (엔진 modules) ---
HISTORY_MONTHS: int = 7                    # 분석월 + 과거 6개월
LIFECYCLE_MIN_ACTIVE_MONTHS: int = 2        # 이 개월 이상 활동해야 "진성 이탈"로 판정

# --- 제품 수명주기(PLC) 단계 판정 ---
PLC_INTRO_MAX_MONTHS: int = 2
PLC_GROWTH_UP: float = 0.15
PLC_GROWTH_DOWN: float = -0.15

# --- KPI 경보 (kpi_alert 모듈) ---
KPI_ALERT_SIGMA: float = 2.0
KPI_ALERT_RATE: float = 0.20
KPI_ALERT_MIN_MONTHS: int = 3
KPI_ALERT_WINDOW: int | None = None

# --- 재고 분석 (inventory_turnover / stock_movement 모듈) ---
INVENTORY_PERIOD_DAYS: int = 30
INVENTORY_SLOW_DAYS: float = 90.0
STOCK_RECONCILE_TOLERANCE: float = 0.01

# --- 안전재고(Safety Stock) 추정 ---
SAFETY_STOCK_Z: float = 1.65
SAFETY_STOCK_MIN_MONTHS: int = 3
