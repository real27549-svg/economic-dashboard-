"""재테크 로드맵 부채(대출) 상세 정의 및 분석."""

from __future__ import annotations

from typing import Any

from financial_roadmap import _format_won

RATE_TYPES = ("고정", "변동")

LOAN_CATEGORIES: dict[str, dict[str, Any]] = {
    "housing": {
        "label": "주택 관련 대출",
        "loans": {
            "mortgage": "주택담보대출 (아파트/빌라/오피스텔)",
            "jeonse_loan": "전세자금대출",
            "interim_loan": "중도금 대출",
            "balance_loan": "잔금 대출",
            "subscription_collateral": "주택청약 담보대출",
        },
    },
    "credit": {
        "label": "신용 대출",
        "loans": {
            "credit_loan": "직장인 신용대출",
            "overdraft": "마이너스 통장",
            "card_loan": "카드론",
            "cash_advance": "현금서비스",
        },
    },
    "other": {
        "label": "기타 대출",
        "loans": {
            "auto_loan": "자동차 할부/오토론",
            "student_loan": "학자금 대출",
            "business_loan": "사업자 대출",
            "insurance_loan": "보험약관 대출",
            "securities_collateral": "증권담보 대출",
            "family_loan": "가족/지인 차용",
        },
    },
}

ALL_LOAN_KEYS: list[str] = [
    key for cat in LOAN_CATEGORIES.values() for key in cat["loans"]
]

DSR_CAUTION_PCT = 40.0
DSR_DANGER_PCT = 50.0
VARIABLE_RATE_CAUTION_PCT = 50.0


def empty_loan() -> dict[str, Any]:
    return {
        "active": False,
        "balance_man": 0.0,
        "rate_pct": 0.0,
        "rate_type": "고정",
        "monthly_payment_man": 0.0,
        "maturity": "",
        "bank": "",
    }


def normalize_loans(raw: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    raw = raw or {}
    loans: dict[str, dict[str, Any]] = {}
    for key in ALL_LOAN_KEYS:
        entry = raw.get(key) or {}
        if not isinstance(entry, dict):
            entry = {}
        balance = float(entry.get("balance_man", 0) or 0)
        loans[key] = {
            "active": bool(entry.get("active")) or balance > 0,
            "balance_man": balance,
            "rate_pct": float(entry.get("rate_pct", 0) or 0),
            "rate_type": entry.get("rate_type") or "고정",
            "monthly_payment_man": float(entry.get("monthly_payment_man", 0) or 0),
            "maturity": str(entry.get("maturity") or ""),
            "bank": str(entry.get("bank") or ""),
        }
    return loans


def loan_label(loan_key: str) -> str:
    for cat in LOAN_CATEGORIES.values():
        if loan_key in cat["loans"]:
            return cat["loans"][loan_key]
    return loan_key


def total_debt_man(monthly: dict[str, Any]) -> float:
    loans = normalize_loans(monthly.get("loans"))
    total = sum(l["balance_man"] for l in loans.values() if l["active"] and l["balance_man"] > 0)
    if total <= 0:
        return float(monthly.get("debt_total", 0) or 0)
    return total


def total_monthly_debt_payment_man(monthly: dict[str, Any]) -> float:
    loans = normalize_loans(monthly.get("loans"))
    pay = sum(
        l["monthly_payment_man"]
        for l in loans.values()
        if l["active"] and l["monthly_payment_man"] > 0
    )
    if pay <= 0:
        return float(monthly.get("loan_payment", 0) or 0)
    return pay


def compute_debt_analysis(
    monthly: dict[str, Any],
    total_assets_man: float,
) -> dict[str, Any]:
    loans = normalize_loans(monthly.get("loans"))
    active = [
        {**l, "key": k, "label": loan_label(k)}
        for k, l in loans.items()
        if l["active"] and (l["balance_man"] > 0 or l["monthly_payment_man"] > 0)
    ]

    total_debt = sum(l["balance_man"] for l in active)
    if total_debt <= 0:
        total_debt = float(monthly.get("debt_total", 0) or 0)

    total_payment = sum(l["monthly_payment_man"] for l in active)
    if total_payment <= 0:
        total_payment = float(monthly.get("loan_payment", 0) or 0)

    income = float(monthly.get("net_income", 0) or 0)
    dsr_pct = (total_payment / income * 100) if income > 0 else None

    debt_to_asset_pct = (total_debt / total_assets_man * 100) if total_assets_man > 0 else None

    variable_balance = sum(
        l["balance_man"] for l in active if l.get("rate_type") == "변동"
    )
    variable_ratio_pct = (
        (variable_balance / total_debt * 100) if total_debt > 0 else 0.0
    )

    if dsr_pct is None:
        dsr_status = "판단 불가 (소득 미입력)"
    elif dsr_pct >= DSR_DANGER_PCT:
        dsr_status = f"위험 ({DSR_DANGER_PCT}% 이상)"
    elif dsr_pct >= DSR_CAUTION_PCT:
        dsr_status = f"주의 ({DSR_CAUTION_PCT}~{DSR_DANGER_PCT}%)"
    else:
        dsr_status = "양호"

    variable_warning = None
    if total_debt > 0 and variable_ratio_pct >= VARIABLE_RATE_CAUTION_PCT:
        variable_warning = (
            f"변동금리 대출 비중 {variable_ratio_pct:.1f}% — "
            "금리 인상 시 상환 부담 증가에 유의하세요."
        )

    priority = sorted(
        [l for l in active if l["balance_man"] > 0],
        key=lambda x: (-x["rate_pct"], -x["balance_man"]),
    )
    priority_lines = [
        f"{i + 1}. {p['label']} — 금리 {p['rate_pct']:.2f}%, "
        f"잔액 {_format_won(p['balance_man'])}, "
        f"월 {_format_won(p['monthly_payment_man'])} ({p.get('rate_type', '')})"
        for i, p in enumerate(priority)
    ]

    return {
        "loans": loans,
        "active_count": len(active),
        "total_debt_man": total_debt,
        "total_debt_fmt": _format_won(total_debt),
        "total_monthly_payment_man": total_payment,
        "total_monthly_payment_fmt": _format_won(total_payment),
        "dsr_pct": dsr_pct,
        "dsr_fmt": f"{dsr_pct:.1f}%" if dsr_pct is not None else "N/A",
        "dsr_status": dsr_status,
        "debt_to_asset_pct": debt_to_asset_pct,
        "debt_to_asset_fmt": (
            f"{debt_to_asset_pct:.1f}%" if debt_to_asset_pct is not None else "N/A"
        ),
        "variable_balance_man": variable_balance,
        "variable_ratio_pct": variable_ratio_pct,
        "variable_ratio_fmt": f"{variable_ratio_pct:.1f}%",
        "variable_rate_warning": variable_warning,
        "repayment_priority": priority_lines or ["(활성 대출 없음)"],
        "repayment_priority_detail": priority,
    }


def format_debt_block_for_ai(debt: dict[str, Any]) -> str:
    lines = [
        f"- 부채 합계: {debt['total_debt_fmt']}",
        f"- 월 원리금 상환 합계: {debt['total_monthly_payment_fmt']}",
        f"- DSR(총부채원리금상환비율): {debt['dsr_fmt']} ({debt['dsr_status']})",
        f"- 부채/자산 비율: {debt['debt_to_asset_fmt']}",
        f"- 변동금리 비중: {debt['variable_ratio_fmt']}",
    ]
    if debt.get("variable_rate_warning"):
        lines.append(f"- 변동금리 경고: {debt['variable_rate_warning']}")
    lines.append("- 상환 우선순위(금리 높은 순, 시스템 추천):")
    for p in debt.get("repayment_priority") or []:
        lines.append(f"  {p}")

    loans = debt.get("loans") or {}
    detail_lines: list[str] = []
    for key in ALL_LOAN_KEYS:
        l = loans.get(key) or {}
        if not l.get("active") or l.get("balance_man", 0) <= 0:
            continue
        detail_lines.append(
            f"  - {loan_label(key)}: 잔액 {_format_won(l['balance_man'])}, "
            f"금리 {l['rate_pct']:.2f}% ({l['rate_type']}), "
            f"월 {_format_won(l['monthly_payment_man'])}, "
            f"만기 {l.get('maturity') or '미입력'}, {l.get('bank') or '금융기관 미입력'}"
        )
    if detail_lines:
        lines.append("- 대출 상세:")
        lines.extend(detail_lines)
    return "\n".join(lines)
