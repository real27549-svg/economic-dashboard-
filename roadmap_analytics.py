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
) -> dict[str, Any]:
    metrics = compute_monthly_metrics(monthly)
    tax_room = compute_tax_deduction_room(annual)
    pension_est = estimate_pension_monthly(fixed, monthly, annual)
    home_timeline = estimate_home_timeline(fixed, metrics)

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
