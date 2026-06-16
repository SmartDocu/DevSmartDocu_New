"""보고서 유형 레지스트리 — 고수준 카테고리 힌트 사전."""
from __future__ import annotations

REPORT_REGISTRY: dict[str, dict] = {
    "경영분석": {
        "description": "KPI 달성현황, 사업부별 성과, 전략 지표 종합 분석",
        "view_hints": [], "months_back": 3, "special": None,
        "folder_en": "management",
        "aliases": ["경영", "kpi", "사업부", "성과", "executive", "경영성과"],
    },
    "판매분석": {
        "description": "채널·제품·지역·고객별 매출 및 수주 분석 (Shapley/ABC-XYZ 스크리닝 → ReportAgent 집중 분석)",
        "view_hints": [], "months_back": 3, "special": None,
        "folder_en": "sales",
        "aliases": ["판매", "영업", "매출", "sales", "revenue", "수주", "판매분석", "매출분석"],
    },
    "생산분석": {
        "description": "생산성·가동률·공정별 분석 (생산공정분석 포함)",
        "view_hints": [], "months_back": 1, "special": None,
        "folder_en": "production",
        "aliases": ["생산", "production", "생산성", "가동률", "공정", "생산공정"],
    },
    "원가분석": {
        "description": "제조원가·판관비·변동/고정비 구조 분석",
        "view_hints": [], "months_back": 3, "special": None,
        "folder_en": "cost",
        "aliases": ["원가", "cost", "비용", "제조원가", "판관비", "원가분석"],
    },
    "품질분석": {
        "description": "불량률·반품·클레임·공정 품질 지표 분석",
        "view_hints": [], "months_back": 1, "special": None,
        "folder_en": "quality",
        "aliases": ["품질", "quality", "불량", "클레임", "반품", "qc", "qa"],
    },
    "구매조달분석": {
        "description": "구매원가 추이·공급업체 평가·납기 준수율 분석",
        "view_hints": [], "months_back": 3, "special": None,
        "folder_en": "procurement",
        "aliases": ["구매", "조달", "procurement", "구매원가", "공급업체", "납기"],
    },
    "재고물류분석": {
        "description": "재고 회전율·안전재고·배송·SCM 분석",
        "view_hints": [], "months_back": 1, "special": None,
        "folder_en": "inventory",
        "aliases": ["재고", "물류", "inventory", "logistics", "scm", "배송", "회전율"],
    },
    "고객분석": {
        "description": "CRM·고객 세분화·이탈/유입·LTV 분석",
        "view_hints": [], "months_back": 3, "special": None,
        "folder_en": "customer",
        "aliases": ["고객", "crm", "customer", "ltv", "이탈", "유입", "고객분석"],
    },
    "마케팅분석": {
        "description": "캠페인 효과·채널별 전환율·마케팅 ROI 분석",
        "view_hints": [], "months_back": 1, "special": None,
        "folder_en": "marketing",
        "aliases": ["마케팅", "marketing", "캠페인", "전환율", "roi", "광고"],
    },
    "인사분석": {
        "description": "인력 현황·이직률·인당 생산성·HR 지표 분석",
        "view_hints": [], "months_back": 3, "special": None,
        "folder_en": "hr",
        "aliases": ["인사", "hr", "human resource", "이직", "인력", "직원", "급여"],
    },
    "재무분석": {
        "description": "손익계산·현금흐름·재무비율·회계 지표 분석",
        "view_hints": [], "months_back": 3, "special": None,
        "folder_en": "finance",
        "aliases": ["재무", "회계", "finance", "accounting", "손익", "현금흐름", "재무비율"],
    },
    "기술분석": {
        "description": "서버·API·MCP 로그, 인터페이스 성능, 시스템 지표 분석",
        "view_hints": [], "months_back": 1, "special": None,
        "folder_en": "technology",
        "aliases": ["기술", "서버", "api", "mcp", "로그", "인터페이스", "시스템", "it", "tech",
                    "서버로그", "인터페이스로그", "성능분석", "로그분석"],
    },
    "리스크분석": {
        "description": "환경·컴플라이언스·리스크 모니터링·ESG 지표 분석",
        "view_hints": [], "months_back": 3, "special": None,
        "folder_en": "risk",
        "aliases": ["esg", "리스크", "risk", "컴플라이언스", "compliance", "환경", "안전"],
    },
    "기타": {
        "description": "위 카테고리에 해당하지 않는 보고서 — LLM이 메타정보 보고 자유 판단",
        "view_hints": [], "months_back": 1, "special": None,
        "folder_en": "general",
        "aliases": ["기타", "other", "일반"],
    },
}


def find_report_type(name: str) -> str | None:
    name_norm = name.lower().replace(" ", "").replace("_", "").replace("/", "")
    for key, cfg in REPORT_REGISTRY.items():
        key_norm = key.lower().replace(" ", "").replace("_", "").replace("/", "")
        if name_norm in key_norm or key_norm in name_norm:
            return key
        for alias in cfg.get("aliases", []):
            alias_norm = alias.lower().replace(" ", "").replace("_", "").replace("/", "")
            if name_norm in alias_norm or alias_norm in name_norm:
                return key
    return None


def list_report_types() -> list[str]:
    return list(REPORT_REGISTRY.keys())


def get_config(report_type: str) -> dict:
    return REPORT_REGISTRY.get(report_type) or REPORT_REGISTRY["기타"]
