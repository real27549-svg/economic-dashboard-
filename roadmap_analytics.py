"""재테크 로드맵 지표 계산 및 차트."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import plotly.graph_objects as go

from financial_roadmap import _format_won, assess_emergency_fund, compute_savings_metrics
from roadmap_fields import (
    ANNUAL_FIELDS,
    MONTHLY_ASSET_FIELDS,
    MONTHLY_EXPENSE_FIELDS,
    MONTHLY_INCOME_FIELDS,
    RECOMMENDED_SAVINGS_RATE,
    TAX_LIMITS_MAN,
)
from roadmap_debt import compute_debt_analysis, total_debt_man

# 또래 순자산 중앙값 참고치 (만원, 통계청·한국은행 가계금융복지조사 등 간이 추정)
PEER_NET_WORTH_MEDIAN_MAN: dict[str, float] = {
    "20-24": 5_000,
    "25-29": 8_000,
    "30-34": 15_000,
    "35-39": 22_000,
    "40-44": 35_000,
    "45-49": 45_000,
    "50-54": 55_000,
    "55-59": 65_000,
    "60+": 70_000,
}


def _peer_age_band(age: int) -> str:
    if age < 25:
        return "20-24"
    if age < 30:
        return "25-29"
    if age < 35:
        return "30-34"
    if age < 40:
        return "35-39"
    if age < 45:
        return "40-44"
    if age < 50:
        return "45-49"
    if age < 55:
        return "50-54"
    if age < 60:
        return "55-59"
    return "60+"


def compute_peer_net_worth_comparison(age: int, net_assets_man: float) -> dict[str, Any]:
    band = _peer_age_band(age)
    median = PEER_NET_WORTH_MEDIAN_MAN[band]
    diff = net_assets_man - median
    ratio = (net_assets_man / median * 100) if median > 0 else None
    if diff >= median * 0.2:
        status = "또래 상위"
    elif diff >= -median * 0.2:
        status = "또래 평균 수준"
    else:
        status = "또래 대비 부족"
    return {
        "age_band": band,
        "peer_median_man": median,
        "peer_median_fmt": _format_won(median),
        "net_assets_man": net_assets_man,
        "net_assets_fmt": _format_won(net_assets_man),
        "diff_man": diff,
        "diff_fmt": _format_won(abs(diff)),
        "ratio_pct": ratio,
        "status": status,
    }


def compute_fire_estimate(
    fixed: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """4% 룰 기반 FIRE 가능 나이 간이 추정."""
    age = int(fixed.get("age") or 35)
    net = float(metrics.get("net_assets_man", 0) or 0)
    monthly_expense = float(metrics.get("total_expense_man", 0) or 0)
    monthly_savings = max(float(metrics.get("monthly_savings_man", 0) or 0), 0)
    annual_expense = monthly_expense * 12
    fire_target = annual_expense * 25 if annual_expense > 0 else 0
    gap = fire_target - net

    if fire_target <= 0:
        return {
            "status": "지출 데이터 필요",
            "fire_target_fmt": "N/A",
            "fire_age": None,
            "detail": "월 지출을 입력하면 FIRE 목표 자산을 계산할 수 있습니다.",
        }
    if net >= fire_target:
        return {
            "status": "FIRE 달성 가능",
            "fire_target_fmt": _format_won(fire_target),
            "fire_age": age,
            "detail": f"현재 순자산 {_format_won(net)} ≥ FIRE 목표 {_format_won(fire_target)}",
        }
    if monthly_savings <= 0:
        return {
            "status": "저축 필요",
            "fire_target_fmt": _format_won(fire_target),
            "fire_age": None,
            "detail": f"FIRE 목표 {_format_won(fire_target)}, 부족액 {_format_won(gap)}",
        }

    balance = net
    months = 0
    max_months = (100 - age) * 12
    r = 0.05 / 12
    while balance < fire_target and months < max_months:
        balance = balance * (1 + r) + monthly_savings
        months += 1
    fire_age = age + months / 12
    return {
        "status": f"약 {fire_age:.0f}세",
        "fire_target_fmt": _format_won(fire_target),
        "fire_age": round(fire_age, 1),
        "detail": f"월 {_format_won(monthly_savings)} 저축·연 5% 수익 가정",
    }


def compute_asset_allocation_breakdown(monthly: dict[str, Any]) -> dict[str, Any]:
    cash = float(monthly.get("cash_deposit", 0) or 0)
    domestic = float(monthly.get("domestic_stocks", 0) or 0) + float(
        monthly.get("domestic_etf_fund", 0) or 0
    )
    foreign = float(monthly.get("foreign_stocks", 0) or 0) + float(
        monthly.get("foreign_etf_fund", 0) or 0
    )
    real_estate = float(monthly.get("owned_real_estate", 0) or 0) + float(
        monthly.get("jeonse_deposit", 0) or 0
    )
    other = (
        float(monthly.get("crypto", 0) or 0)
        + float(monthly.get("gold_commodities", 0) or 0)
        + float(monthly.get("other_assets", 0) or 0)
    )
    total = cash + domestic + foreign + real_estate + other
    if total <= 0:
        return {"total_man": 0, "items": [], "largest": None}
    items = [
        ("현금·예금", cash),
        ("국내 주식·ETF", domestic),
        ("해외 주식·ETF", foreign),
        ("부동산·전세", real_estate),
        ("기타", other),
    ]
    pct_items = [
        {"label": label, "man": val, "pct": val / total * 100}
        for label, val in items
        if val > 0
    ]
    largest = max(pct_items, key=lambda x: x["pct"]) if pct_items else None
    return {
        "total_man": total,
        "total_fmt": _format_won(total),
        "items": pct_items,
        "largest": largest,
    }


def compute_monthly_performance(
    monthly_history: list[dict[str, Any]],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    points = sorted(
        [
            {"year_month": h["year_month"], "net_assets_man": float(h["net_assets_man"])}
            for h in monthly_history
            if h.get("year_month") and h.get("net_assets_man") is not None
        ],
        key=lambda x: x["year_month"],
    )
    current = float(metrics.get("net_assets_man", 0) or 0)
    savings_rate = metrics.get("savings_rate_pct")

    if len(points) >= 2:
        prev = points[-2]["net_assets_man"]
        change = current - prev if current else points[-1]["net_assets_man"] - prev
        change_pct = (change / prev * 100) if prev else None
    elif len(points) == 1:
        prev = points[0]["net_assets_man"]
        change = current - prev
        change_pct = (change / prev * 100) if prev else None
    else:
        prev = None
        change = None
        change_pct = None

    return {
        "history_count": len(points),
        "previous_net_man": prev,
        "previous_net_fmt": _format_won(prev) if prev is not None else "N/A",
        "change_man": change,
        "change_fmt": _format_won(abs(change)) if change is not None else "N/A",
        "change_direction": "증가" if (change or 0) >= 0 else "감소",
        "change_pct": change_pct,
        "current_savings_rate_pct": savings_rate,
        "current_savings_rate_fmt": metrics.get("savings_rate_fmt", "N/A"),
    }


def _sum_fields(data: dict, fields: dict[str, str]) -> float:
    return sum(float(data.get(k, 0) or 0) for k in fields)


def compute_monthly_metrics(monthly: dict[str, Any]) -> dict[str, Any]:
    total_income = _sum_fields(monthly, MONTHLY_INCOME_FIELDS)
    total_expense = _sum_fields(monthly, MONTHLY_EXPENSE_FIELDS)
    total_assets = _sum_fields(monthly, MONTHLY_ASSET_FIELDS)
    total_debt = total_debt_man(monthly)
    net_assets = total_assets - total_debt
    debt_analysis = compute_debt_analysis(monthly, total_assets)

    fixed_total = float(monthly.get("fixed_total", 0) or 0)
    variable_approx = max(total_expense - fixed_total, 0)

    savings = compute_savings_metrics(total_income, fixed_total, variable_approx)
    savings["total_income_man"] = total_income
    savings["total_expense_man"] = total_expense
    savings["total_income_fmt"] = _format_won(total_income)
    savings["total_expense_fmt"] = _format_won(total_expense)

    cash = float(monthly.get("cash_deposit", 0) or 0)
    emergency = assess_emergency_fund(cash, fixed_total, 0)

    return {
        **savings,
        "total_assets_man": total_assets,
        "total_assets_fmt": _format_won(total_assets),
        "total_debt_man": total_debt,
        "total_debt_fmt": _format_won(total_debt),
        "net_assets_man": net_assets,
        "net_assets_fmt": _format_won(net_assets),
        "emergency_fund_status": emergency["status"],
        "emergency_fund_detail": emergency["detail"],
        "emergency_fund_adequate": emergency["is_adequate"],
        "liquid_reserve_man": emergency["liquid_reserve_man"],
        "liquid_reserve_fmt": emergency["liquid_reserve_fmt"],
        "debt_analysis": debt_analysis,
        "dsr_fmt": debt_analysis["dsr_fmt"],
        "dsr_status": debt_analysis["dsr_status"],
        "debt_to_asset_fmt": debt_analysis["debt_to_asset_fmt"],
        "variable_ratio_fmt": debt_analysis["variable_ratio_fmt"],
    }


def compute_tax_deduction_room(annual: dict[str, Any]) -> dict[str, Any]:
    irp_used = float(annual.get("irp_contribution", 0) or 0)
    pension_used = float(annual.get("pension_savings", 0) or 0)
    isa_used = float(annual.get("isa_contribution", 0) or 0)
    fin_income = float(annual.get("financial_income_total", 0) or 0)

    combined_used = irp_used + pension_used
    combined_room = max(TAX_LIMITS_MAN["combined_pension_max"] - combined_used, 0)
    isa_room = max(TAX_LIMITS_MAN["isa_subscription"] - isa_used, 0)
    threshold = TAX_LIMITS_MAN["financial_income_tax_threshold"]
    fin_income_pct = (fin_income / threshold * 100) if threshold else 0

    warning = None
    if fin_income >= threshold * 0.8:
        warning = (
            f"금융소득 {_format_won(fin_income)} — "
            f"종합과세 기준 {_format_won(threshold)}의 {fin_income_pct:.0f}% 수준입니다."
        )

    return {
        "irp_used_man": irp_used,
        "pension_used_man": pension_used,
        "isa_used_man": isa_used,
        "combined_pension_room_man": combined_room,
        "combined_pension_room_fmt": _format_won(combined_room),
        "isa_room_man": isa_room,
        "isa_room_fmt": _format_won(isa_room),
        "financial_income_man": fin_income,
        "financial_income_fmt": _format_won(fin_income),
        "financial_income_warning": warning,
    }


def estimate_pension_monthly(
    fixed: dict[str, Any],
    monthly: dict[str, Any],
    annual: dict[str, Any],
) -> dict[str, str]:
    """국민연금·개인연금·IRP 월수령액 간이 추정 (만원)."""
    age = int(fixed.get("age") or 35)
    retire_age = int(fixed.get("retirement_age") or 65)
    years_to_retire = max(retire_age - age, 1)
    income = float(monthly.get("net_income", 0) or 0)
    np_years = float(annual.get("national_pension_years", 0) or 0)
    irp = float(monthly.get("domestic_etf_fund", 0) or 0) * 0  # placeholder
    irp_balance = float(annual.get("irp_contribution", 0) or 0) * max(np_years, 1)
    pension_balance = float(annual.get("pension_savings", 0) or 0) * max(np_years, 1)

    # 국민연금: 매우 단순화 (실수령의 40% × 납입년수/40)
    national_monthly = income * 0.4 * min(np_years / 40, 1.0) if np_years else income * 0.25
    personal_monthly = pension_balance / (20 * 12) if pension_balance else 0
    irp_monthly = irp_balance / (20 * 12) if irp_balance else 0
    total = national_monthly + personal_monthly + irp_monthly

    return {
        "national_fmt": _format_won(national_monthly),
        "personal_fmt": _format_won(personal_monthly),
        "irp_fmt": _format_won(irp_monthly),
        "total_fmt": _format_won(total),
        "years_to_retire": years_to_retire,
        "disclaimer": "간이 추정치이며 실제 수령액과 다를 수 있습니다.",
    }


def estimate_home_timeline(
    fixed: dict[str, Any],
    metrics: dict[str, Any],
) -> dict[str, str]:
    target = float(fixed.get("home_target_amount_man", 0) or 0)
    net = float(metrics.get("net_assets_man", 0) or 0)
    savings = max(float(metrics.get("monthly_savings_man", 0) or 0), 0)
    gap = target - net
    if target <= 0:
        return {"status": "목표 금액 미입력", "detail": "고정 정보에서 내집마련 목표 금액을 입력하세요."}
    if gap <= 0:
        return {"status": "목표 달성 가능", "detail": f"현재 순자산 {_format_won(net)} ≥ 목표 {_format_won(target)}"}
    if savings <= 0:
        return {
            "status": "저축 필요",
            "detail": f"부족액 {_format_won(gap)} — 월 저축액을 늘려야 합니다.",
        }
    months = gap / savings
    years = months / 12
    return {
        "status": f"약 {years:.1f}년 후",
        "detail": f"부족액 {_format_won(gap)}, 월 {_format_won(savings)} 저축 가정",
    }


def build_analysis_context(
    fixed: dict[str, Any],
    monthly: dict[str, Any],
    annual: dict[str, Any],
    annual_history: list[dict[str, Any]],
    variable_events: list[dict[str, Any]],
    monthly_history: list[dict[str, Any]],
    holdings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    metrics = compute_monthly_metrics(monthly)
    tax_room = compute_tax_deduction_room(annual)
    pension_est = estimate_pension_monthly(fixed, monthly, annual)
    home_timeline = estimate_home_timeline(fixed, metrics)
    age = int(fixed.get("age") or 35)
    net = float(metrics.get("net_assets_man", 0) or 0)

    risk = fixed.get("risk_profile", "중립형")
    recommended = RECOMMENDED_SAVINGS_RATE.get(risk, 20)
    actual_rate = metrics.get("savings_rate_pct")
    savings_comparison = {
        "recommended_pct": recommended,
        "actual_pct": actual_rate,
        "actual_fmt": metrics.get("savings_rate_fmt", "N/A"),
        "gap_pct": (recommended - actual_rate) if actual_rate is not None else None,
    }

    history_points = []
    for row in monthly_history:
        ym = row.get("year_month", "")
        nav = row.get("net_assets_man")
        if nav is None:
            nav = (row.get("data") or {}).get("_net_assets_man")
        if ym and nav is not None:
            history_points.append({"year_month": ym, "net_assets_man": float(nav)})

    if not history_points and metrics.get("net_assets_man") is not None:
        history_points.append(
            {
                "year_month": datetime.now().strftime("%Y-%m"),
                "net_assets_man": metrics["net_assets_man"],
            }
        )

    return {
        "fixed": fixed,
        "monthly": monthly,
        "annual": annual,
        "annual_history": annual_history,
        "variable_events": variable_events,
        "monthly_history": history_points,
        "metrics": metrics,
        "tax_room": tax_room,
        "pension_estimate": pension_est,
        "home_timeline": home_timeline,
        "savings_comparison": savings_comparison,
        "debt_analysis": metrics.get("debt_analysis") or {},
        "peer_comparison": compute_peer_net_worth_comparison(age, net),
        "fire_estimate": compute_fire_estimate(fixed, metrics),
        "asset_allocation": compute_asset_allocation_breakdown(monthly),
        "monthly_performance": compute_monthly_performance(history_points, metrics),
        "holdings": holdings or [],
    }


def build_net_worth_chart(history: list[dict[str, Any]]) -> go.Figure | None:
    if len(history) < 1:
        return None
    xs = [h["year_month"] for h in history]
    ys = [h["net_assets_man"] for h in history]
    fig = go.Figure(
        data=[
            go.Scatter(
                x=xs,
                y=ys,
                mode="lines+markers",
                name="순자산",
                line=dict(color="#2563eb", width=2),
                hovertemplate="%{x}<br>순자산: %{y:,.0f}만원<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="월별 순자산 추이",
        height=360,
        margin=dict(l=40, r=20, t=50, b=40),
        yaxis_title="만원",
        xaxis_title="년월",
    )
    return fig


def build_savings_simulation_chart(
    monthly_savings_man: float,
    current_net_man: float,
    years: int = 10,
) -> go.Figure:
    """비관/중립/낙관 시나리오 (연 수익률 2%/5%/8%)."""
    months = years * 12
    scenarios = {
        "비관 (2%)": 0.02 / 12,
        "중립 (5%)": 0.05 / 12,
        "낙관 (8%)": 0.08 / 12,
    }
    fig = go.Figure()
    colors = {"비관 (2%)": "#ef4444", "중립 (5%)": "#2563eb", "낙관 (8%)": "#16a34a"}
    labels = []
    for name, r in scenarios.items():
        balance = current_net_man
        path = []
        for m in range(months + 1):
            path.append(balance)
            balance = balance * (1 + r) + monthly_savings_man
        x = list(range(months + 1))
        fig.add_trace(
            go.Scatter(
                x=x,
                y=path,
                mode="lines",
                name=name,
                line=dict(color=colors[name]),
            )
        )
        labels.append(name)
    fig.update_layout(
        title=f"월 저축 시뮬레이션 ({years}년)",
        height=380,
        margin=dict(l=40, r=20, t=50, b=40),
        yaxis_title="순자산 (만원)",
        xaxis_title="개월",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig
