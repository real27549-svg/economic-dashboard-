"""재테크 로드맵 입력 필드 정의."""

from __future__ import annotations

GOAL_OPTIONS = (
    "내집마련",
    "노후준비",
    "FIRE",
    "자녀교육",
    "자산증식",
)

JOB_TYPES = ("직장인", "자영업", "프리랜서", "공무원", "군인")
GENDER_OPTIONS = ("남성", "여성", "기타/미입력")
MARITAL_OPTIONS = ("미혼", "기혼", "이혼/별거", "기타")
EDUCATION_OPTIONS = ("고졸", "전문대", "대졸", "대학원", "기타")
HEALTH_INSURANCE_TYPES = ("직장", "지역")
HOUSING_OWNERSHIP = ("무주택", "1주택", "다주택")
RESIDENCE_TYPES = ("자가", "전세", "월세")
RETIREMENT_PENSION_TYPES = ("DB", "DC", "없음")
RISK_PROFILES = ("안정형", "중립형", "공격형")
YES_NO = ("예", "아니오")

STOCK_ACCOUNT_TYPES: dict[str, str] = {
    "direct": "직접투자",
    "isa": "ISA",
    "personal_pension": "개인연금",
    "irp": "IRP",
}

STOCK_MARKET_LABELS: dict[str, str] = {
    "domestic": "국내",
    "foreign": "해외",
}

UNIT_NOTE = "※ 금액 입력 단위는 **만원**입니다."

VARIABLE_EVENT_TYPES = {
    "residence_change": "거주 형태 변경",
    "marriage_birth": "결혼/출산",
    "job_change": "이직/퇴직",
    "goal_change": "재테크 목표 변경",
    "risk_change": "투자 성향 변경",
    "credit_change": "신용점수 변동",
    "insurance_change": "보험 해지/추가 가입",
    "large_expense": "큰 지출 예정",
    "inheritance_gift": "상속/증여 수령",
    "pension_start": "연금 수령 시작",
}

MONTHLY_INCOME_FIELDS: dict[str, str] = {
    "net_income": "월 실수령액 (만원)",
    "bonus": "성과급/상여금 (만원, 해당월)",
    "side_income": "부업 수입 (만원)",
    "dividend_income": "배당금 수입 (만원)",
    "rental_income": "임대 수입 (만원)",
    "other_income": "기타 수입 (만원)",
    "special_income": "이번 달 특별 수입 (만원)",
}

MONTHLY_EXPENSE_FIELDS: dict[str, str] = {
    "food": "월 식비 (만원)",
    "transport": "월 교통비 (만원)",
    "telecom": "월 통신비 (만원)",
    "fixed_total": "월 고정지출 합계 (만원)",
    "loan_payment": "월 대출 이자/원금 (만원)",
    "insurance": "월 보험료 합계 (만원)",
    "education": "월 교육비 (만원)",
    "parent_support": "월 부모님 용돈 (만원)",
    "leisure": "월 여가/취미 (만원)",
    "special_expense": "이번 달 특별 지출 (만원)",
}

MONTHLY_ASSET_FIELDS: dict[str, str] = {
    "cash_deposit": "현금/예적금 (만원)",
    "domestic_stocks": "국내주식 평가액 (만원)",
    "foreign_stocks": "해외주식 평가액 (만원)",
    "domestic_etf_fund": "국내ETF/펀드 (만원)",
    "foreign_etf_fund": "해외ETF/펀드 (만원)",
    "crypto": "암호화폐 (만원)",
    "gold_commodities": "금/원자재 (만원)",
    "other_assets": "기타 자산 (만원)",
    "jeonse_deposit": "전세보증금 (만원)",
    "owned_real_estate": "부동산 시세 (만원)",
}

MONTHLY_LIABILITY_FIELDS: dict[str, str] = {
    "debt_total": "부채 총합 (만원, 레거시·자동합산)",
}

ANNUAL_FIELDS: dict[str, str] = {
    "year_end_refund": "연말정산 환급액 (만원)",
    "annual_bonus_total": "연간 성과급/상여금 (만원)",
    "irp_contribution": "IRP 납입액 (만원)",
    "pension_savings": "연금저축 납입액 (만원)",
    "isa_contribution": "ISA 납입액 (만원)",
    "housing_subscription": "주택청약 납입액 (만원)",
    "medical_expense": "연간 의료비 (만원)",
    "donation": "연간 기부금 (만원)",
    "health_insurance_settlement": "건강보험료 정산액 (만원)",
    "comprehensive_income_tax": "종합소득세 납부액 (만원)",
    "financial_income_total": "금융소득 합계 (만원)",
    "credit_vs_check_ratio": "신용 vs 체크카드 비율 (%)",
    "national_pension_years": "국민연금 납입 기간 (년)",
    "housing_lottery_won": "주택청약 당첨 여부",
}

# 절세 한도 (만원, 2024~2025 기준 근사치)
TAX_LIMITS_MAN = {
    "irp_deduction": 900,
    "pension_savings_deduction": 600,
    "combined_pension_max": 900,
    "isa_subscription": 2000,
    "financial_income_tax_threshold": 2000,
}

RECOMMENDED_SAVINGS_RATE = {
    "안정형": 15,
    "중립형": 20,
    "공격형": 25,
}
