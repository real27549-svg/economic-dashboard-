"""Claude 기반 맞춤 재테크 로드맵."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

import plotly.graph_objects as go

from ai_outlook import DEFAULT_MODEL, create_anthropic_client, pick_indicators
from ai_stock_picks import build_macro_context

RiskProfile = Literal["안정형", "중립형", "공격형"]
GoalType = Literal["내집마련", "노후준비", "FIRE", "자녀교육", "자산증식"]
JobType = Literal["직장인", "자영업", "프리랜서"]
MaritalStatus = Literal["미혼", "기혼", "기타"]

GOAL_OPTIONS: tuple[GoalType, ...] = (
    "내집마련",
    "노후준비",
    "FIRE",
    "자녀교육",
    "자산증식",
)
JOB_TYPES: tuple[JobType, ...] = ("직장인", "자영업", "프리랜서")
MARITAL_OPTIONS: tuple[MaritalStatus, ...] = ("미혼", "기혼", "기타")
INCOME_STABILITY_OPTIONS: tuple[str, ...] = ("안정", "보통", "불안정")

ROADMAP_HORIZONS = ("1y", "3y", "5y", "10y")
HORIZON_LABELS = {
    "1y": "1년 플랜",
    "3y": "3년 플랜",
    "5y": "5년 플랜",
    "10y": "10년 플랜",
}

MACRO_KEYS = [
    "FEDFUNDS",
    "CPIAUCSL",
    "DGS10",
    "DGS2",
    "T10Y2Y",
    "UNRATE",
    "VIXCLS",
    "NASDAQCOM",
    "KOSPI",
    "DEXKOUS",
    "DTWEXBGS",
    "GOLD",
    "DCOILWTICO",
]

ALLOCATION_LABELS = {
    "cash": "현금·예금",
    "stocks": "주식·ETF",
    "bonds": "채권·금리",
    "real_estate": "부동산·REITs",
}

ALLOCATION_COLORS = {
    "cash": "#64748b",
    "stocks": "#2563eb",
    "bonds": "#16a34a",
    "real_estate": "#f59e0b",
}

ASSET_FIELDS: dict[str, str] = {
    "cash_deposit": "현금/예적금",
    "domestic_stocks": "국내주식",
    "foreign_stocks": "해외주식",
    "domestic_etf_fund": "국내ETF/펀드",
    "foreign_etf_fund": "해외ETF/펀드",
    "jeonse_deposit": "전세보증금",
    "owned_real_estate": "부동산 (자가)",
    "personal_pension": "개인연금 (연금저축펀드)",
    "irp": "IRP (개인형퇴직연금)",
    "severance_expected": "퇴직금 (예상)",
    "crypto": "암호화폐",
    "gold_commodities": "금/원자재",
    "other_assets": "기타",
}

LIABILITY_FIELDS: dict[str, str] = {
    "jeonse_loan": "전세대출",
    "mortgage": "주택담보대출",
    "credit_loan": "신용대출",
    "other_debt": "기타부채",
}

ASSET_DEFAULTS: dict[str, float] = {
    "cash_deposit": 3000,
    "domestic_stocks": 1000,
    "foreign_stocks": 500,
    "domestic_etf_fund": 300,
    "foreign_etf_fund": 200,
    "jeonse_deposit": 0,
    "owned_real_estate": 5000,
    "personal_pension": 0,
    "irp": 0,
    "severance_expected": 0,
    "crypto": 0,
    "gold_commodities": 0,
    "other_assets": 0,
}

LIABILITY_DEFAULTS: dict[str, float] = {
    "jeonse_loan": 0,
    "mortgage": 0,
    "credit_loan": 0,
    "other_debt": 0,
}


def _format_won(amount_man: float) -> str:
    """만원 단위 입력 → 표시용 문자열."""
    won = amount_man * 10_000
    if won >= 1e12:
        return f"{won / 1e12:.2f}조원"
    if won >= 1e8:
        return f"{won / 1e8:.1f}억원"
    if won >= 1e4:
        return f"{won / 1e4:.0f}만원"
    return f"{won:,.0f}원"


def _detail_block(
    fields: dict[str, str],
    values: dict[str, float],
) -> tuple[dict[str, float], list[str], dict[str, str]]:
    detail = {key: float(values.get(key, 0) or 0) for key in fields}
    lines = [
        f"  - {fields[key]}: {_format_won(amount)}"
        for key, amount in detail.items()
        if amount > 0
    ]
    fmt = {fields[key]: _format_won(amount) for key, amount in detail.items()}
    return detail, lines, fmt


def compute_savings_metrics(
    monthly_income_man: float,
    monthly_fixed_man: float,
    monthly_variable_man: float,
) -> dict[str, Any]:
    """저축 가능액·저축률 (월 실수령액 대비)."""
    monthly_income_man = float(monthly_income_man or 0)
    monthly_fixed_man = float(monthly_fixed_man or 0)
    monthly_variable_man = float(monthly_variable_man or 0)
    monthly_savings_man = (
        monthly_income_man - monthly_fixed_man - monthly_variable_man
    )

    if monthly_income_man <= 0:
        return {
            "monthly_income_man": monthly_income_man,
            "monthly_fixed_man": monthly_fixed_man,
            "monthly_variable_man": monthly_variable_man,
            "monthly_savings_man": monthly_savings_man,
            "monthly_savings_fmt": _format_won(max(monthly_savings_man, 0)),
            "savings_rate_pct": None,
            "savings_rate_fmt": "N/A (소득 미입력)",
        }

    rate = (monthly_savings_man / monthly_income_man) * 100
    return {
        "monthly_income_man": monthly_income_man,
        "monthly_fixed_man": monthly_fixed_man,
        "monthly_variable_man": monthly_variable_man,
        "monthly_savings_man": monthly_savings_man,
        "monthly_savings_fmt": _format_won(monthly_savings_man),
        "savings_rate_pct": rate,
        "savings_rate_fmt": f"{rate:.1f}%",
    }


def assess_emergency_fund(
    emergency_fund_man: float,
    monthly_fixed_man: float,
    cash_deposit_man: float = 0,
) -> dict[str, Any]:
    """비상금 vs 고정지출 3~6개월 기준."""
    emergency_fund_man = float(emergency_fund_man or 0)
    monthly_fixed_man = float(monthly_fixed_man or 0)
    liquid_man = emergency_fund_man + float(cash_deposit_man or 0)
    target_3m = monthly_fixed_man * 3
    target_6m = monthly_fixed_man * 6

    if monthly_fixed_man <= 0:
        status = "판단 불가 (고정지출 미입력)"
        detail = "월 고정지출을 입력하면 3~6개월분 기준으로 평가합니다."
    elif liquid_man >= target_6m:
        status = "충분 (6개월 이상)"
        detail = (
            f"유동성 {_format_won(liquid_man)} ≥ 권장 6개월분 {_format_won(target_6m)}"
        )
    elif liquid_man >= target_3m:
        status = "최소 충족 (3~6개월)"
        detail = (
            f"유동성 {_format_won(liquid_man)} — 6개월 목표 {_format_won(target_6m)}까지 "
            f"{_format_won(target_6m - liquid_man)} 부족"
        )
    else:
        status = "부족 (3개월 미만)"
        detail = (
            f"유동성 {_format_won(liquid_man)} — 3개월 최소 {_format_won(target_3m)}까지 "
            f"{_format_won(max(target_3m - liquid_man, 0))} 부족"
        )

    return {
        "emergency_fund_man": emergency_fund_man,
        "emergency_fund_fmt": _format_won(emergency_fund_man),
        "liquid_reserve_man": liquid_man,
        "liquid_reserve_fmt": _format_won(liquid_man),
        "target_3m_man": target_3m,
        "target_6m_man": target_6m,
        "target_3m_fmt": _format_won(target_3m),
        "target_6m_fmt": _format_won(target_6m),
        "status": status,
        "detail": detail,
        "is_adequate": liquid_man >= target_3m if monthly_fixed_man > 0 else None,
    }


def build_user_profile(
    age: int,
    marital_status: MaritalStatus,
    num_children: int,
    job_type: JobType,
    monthly_income_man: float,
    monthly_fixed_expenses_man: float,
    monthly_variable_expenses_man: float,
    risk_profile: RiskProfile,
    goals: list[GoalType],
    emergency_fund_man: float,
    assets_man: dict[str, float],
    liabilities_man: dict[str, float],
    optional: dict[str, Any] | None = None,
) -> dict[str, Any]:
    assets, asset_lines, assets_fmt = _detail_block(ASSET_FIELDS, assets_man)
    liabilities, liability_lines, liabilities_fmt = _detail_block(
        LIABILITY_FIELDS, liabilities_man
    )
    total_assets_man = sum(assets.values())
    total_liabilities_man = sum(liabilities.values())
    net_assets_man = total_assets_man - total_liabilities_man

    savings = compute_savings_metrics(
        monthly_income_man,
        monthly_fixed_expenses_man,
        monthly_variable_expenses_man,
    )
    emergency = assess_emergency_fund(
        emergency_fund_man,
        monthly_fixed_expenses_man,
        assets.get("cash_deposit", 0),
    )

    goal_list = list(goals) if goals else ["자산증식"]
    optional = optional or {}

    return {
        "age": age,
        "marital_status": marital_status,
        "num_children": int(num_children),
        "job_type": job_type,
        "monthly_income_man": savings["monthly_income_man"],
        "monthly_income_fmt": _format_won(savings["monthly_income_man"]),
        "monthly_fixed_expenses_man": savings["monthly_fixed_man"],
        "monthly_fixed_expenses_fmt": _format_won(savings["monthly_fixed_man"]),
        "monthly_variable_expenses_man": savings["monthly_variable_man"],
        "monthly_variable_expenses_fmt": _format_won(savings["monthly_variable_man"]),
        "monthly_savings_man": savings["monthly_savings_man"],
        "monthly_savings_fmt": savings["monthly_savings_fmt"],
        "savings_rate_pct": savings["savings_rate_pct"],
        "savings_rate_fmt": savings["savings_rate_fmt"],
        "emergency_fund_man": emergency["emergency_fund_man"],
        "emergency_fund_fmt": emergency["emergency_fund_fmt"],
        "emergency_fund_status": emergency["status"],
        "emergency_fund_detail": emergency["detail"],
        "emergency_fund_adequate": emergency["is_adequate"],
        "liquid_reserve_man": emergency["liquid_reserve_man"],
        "liquid_reserve_fmt": emergency["liquid_reserve_fmt"],
        "assets": assets,
        "assets_fmt": assets_fmt,
        "asset_breakdown_lines": asset_lines or ["  - (입력 없음)"],
        "liabilities": liabilities,
        "liabilities_fmt": liabilities_fmt,
        "liability_breakdown_lines": liability_lines or ["  - (입력 없음)"],
        "total_assets_man": total_assets_man,
        "total_assets_fmt": _format_won(total_assets_man),
        "total_liabilities_man": total_liabilities_man,
        "total_liabilities_fmt": _format_won(total_liabilities_man),
        "net_assets_man": net_assets_man,
        "net_assets_fmt": _format_won(net_assets_man),
        "risk_profile": risk_profile,
        "goals": goal_list,
        "goal": goal_list[0],
        "optional": optional,
    }


def _format_macro_block(macro: dict) -> str:
    indicators = pick_indicators(macro.get("indicators", {}), MACRO_KEYS)
    lines = [
        f"- {item['label']}: {item['value']} (기준일 {item['date']})"
        for item in indicators.values()
    ]
    indicator_text = "\n".join(lines) if lines else "(지표 없음)"

    fng = macro.get("fear_greed", {})
    fng_line = ""
    if fng.get("score") is not None:
        fng_line = (
            f"\n[CNN Fear & Greed]\n"
            f"- 점수: {fng['score']}/100 ({fng.get('label', '')})"
        )

    sector_lines = []
    for label, items in (
        ("강세 섹터 (1주)", macro.get("sectors_top", [])),
        ("약세 섹터 (1주)", macro.get("sectors_bottom", [])),
    ):
        if items:
            sector_lines.append(f"\n[{label}]")
            for item in items:
                sector_lines.append(f"- {item['sector']}: {item['return_pct']:+.2f}%")

    return f"{indicator_text}{fng_line}{''.join(sector_lines)}"


def _format_optional_block(optional: dict[str, Any]) -> str:
    if not optional:
        return "  - (추가 입력 없음)"

    lines: list[str] = []
    mapping = {
        "variable_expense_detail": "월 변동지출 상세",
        "insurance_types": "가입 보험",
        "year_end_tax_refund_man": "연말정산 환급액",
        "has_isa": "ISA 가입",
        "home_target_region": "내집마련 목표 지역",
        "home_target_budget_man": "내집마련 목표 예산",
        "retirement_age": "희망 은퇴 나이",
        "retirement_monthly_man": "목표 노후 월 생활비",
        "child_education_plan": "자녀 교육비 계획",
        "has_indemnity_insurance": "실손보험 가입",
        "income_stability": "소득 안정성",
    }
    for key, label in mapping.items():
        value = optional.get(key)
        if value is None or value == "" or value == []:
            continue
        if key.endswith("_man") and isinstance(value, (int, float)):
            lines.append(f"  - {label}: {_format_won(float(value))}")
        elif key == "has_isa" or key == "has_indemnity_insurance":
            lines.append(f"  - {label}: {'예' if value else '아니오'}")
        elif key == "insurance_types" and isinstance(value, list):
            lines.append(f"  - {label}: {', '.join(value)}")
        elif key == "variable_expense_detail" and isinstance(value, dict):
            detail_lines = [
                f"{k} {_format_won(float(v))}"
                for k, v in value.items()
                if float(v or 0) > 0
            ]
            if detail_lines:
                lines.append(f"  - {label}: {', '.join(detail_lines)}")
        else:
            lines.append(f"  - {label}: {value}")
    return "\n".join(lines) if lines else "  - (추가 입력 없음)"


def _build_roadmap_prompt(profile: dict, macro: dict) -> str:
    macro_text = _format_macro_block(macro)
    goals_text = ", ".join(profile.get("goals") or [profile.get("goal", "")])
    optional_text = _format_optional_block(profile.get("optional") or {})
    savings_rate = profile.get("savings_rate_fmt", "N/A")
    emergency_status = profile.get("emergency_fund_status", "")
    emergency_detail = profile.get("emergency_fund_detail", "")

    return f"""당신은 초보 투자자를 위한 재테크·자산관리 플래너입니다.
사용자 프로필과 현재 거시경제 환경을 반영해 1년·3년·5년·10년 맞춤 로드맵을 작성하세요.

## 사용자 프로필
- 나이: {profile['age']}세
- 결혼 여부: {profile.get('marital_status', '미입력')} · 자녀 수: {profile.get('num_children', 0)}명
- 직업 유형: {profile.get('job_type', '미입력')}
- 월 실수령액: {profile.get('monthly_income_fmt', 'N/A')}
- 월 고정지출: {profile.get('monthly_fixed_expenses_fmt', 'N/A')}
- 월 변동지출: {profile.get('monthly_variable_expenses_fmt', 'N/A')}
- 월 저축·투자 가능액: {profile.get('monthly_savings_fmt', 'N/A')}
- 저축률: {savings_rate}
- 비상금: {profile.get('emergency_fund_fmt', '0원')} ({emergency_status} — {emergency_detail})
- 유동성 합계(비상금+현금예금): {profile.get('liquid_reserve_fmt', 'N/A')}
- 자산 합계: {profile['total_assets_fmt']}
{chr(10).join(profile['asset_breakdown_lines'])}
- 부채 합계: {profile['total_liabilities_fmt']}
{chr(10).join(profile['liability_breakdown_lines'])}
- 순자산 (자산 − 부채): {profile['net_assets_fmt']}
- 투자 성향: {profile['risk_profile']}
- 재테크 목표: {goals_text}

## 추가 입력 (선택)
{optional_text}

## 현재 거시·시장 환경 (자동 반영)
{macro_text}

## 작성 지침
- 금리·인플레·환율·주가지수·VIX·섹터 흐름을 로드맵에 반영하세요.
- 위 세분화된 자산·부채 구성(국내/해외 주식·ETF, 전세보증금, 연금·IRP, 부채 종류 등)을 분석해
  현재 포트폴리오의 강점·취약점을 짚고, 리밸런싱·부채 상환 우선순위를 로드맵에 반영하세요.
- 순자산과 부채 비율, 저축률({savings_rate}), 비상금 상태를 고려해 목표 자산·현금흐름 계획을 현실적으로 작성하세요.
- 투자 성향과 목표에 맞게 자산배분 비율을 조정하세요.
- ISA·IRP·연금저축 등 선택 입력이 있으면 tax_strategy에 구체적 절세 활용법을 제시하세요.
- savings_rate_note: 저축률 수준의 적정성·개선 방향을 2~3문장으로 분석하세요.
- emergency_fund_note: 비상금 충분 여부와 보완 우선순위를 2~3문장으로 분석하세요.
- tax_strategy: IRP·연금저축·ISA 등 활용 절세 전략 3~5개 (문장 리스트).
- 목표 자산 금액(target_asset_man)은 만원 단위 숫자로, 월 저축·수익률 가정을 합리적으로 반영하세요.
- allocation 4개 항목(cash, stocks, bonds, real_estate) 합계는 반드시 100.
- 구체적 행동 가이드(actions)는 3~5개, 리스크(risks)는 2~4개.
- 단정적 수익 보장·특정 종목 매수 권유 금지. "가능성", "고려" 표현 사용.
- 모든 설명은 한국어.

반드시 아래 JSON만 출력하세요:
{{
  "summary": "전체 로드맵 한 줄 요약 (2~3문장, 저축률·비상금 핵심 포함)",
  "macro_note": "현재 거시환경이 이 로드맵에 미치는 영향 (2~3문장)",
  "savings_rate_note": "저축률 분석 (2~3문장)",
  "emergency_fund_note": "비상금 평가 및 보완 방향 (2~3문장)",
  "tax_strategy": ["절세 전략 1", "절세 전략 2"],
  "plans": {{
    "1y": {{
      "headline": "1년 플랜 제목",
      "target_asset_man": 0,
      "target_asset_fmt": "목표 자산 표시 (예: 1.2억원)",
      "allocation": {{"cash": 25, "stocks": 35, "bonds": 25, "real_estate": 15}},
      "actions": ["행동 1", "행동 2"],
      "risks": ["리스크 1", "리스크 2"]
    }},
    "3y": {{ ... }},
    "5y": {{ ... }},
    "10y": {{ ... }}
  }}
}}"""


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    result = json.loads(cleaned)
    if "plans" not in result:
        raise ValueError("AI 응답에 plans 항목이 없습니다.")
    for horizon in ROADMAP_HORIZONS:
        plan = result["plans"].get(horizon)
        if not plan:
            raise ValueError(f"AI 응답에 {horizon} 플랜이 없습니다.")
        alloc = plan.get("allocation") or {}
        total = sum(float(alloc.get(k, 0)) for k in ALLOCATION_LABELS)
        if abs(total - 100) > 5:
            for key in ALLOCATION_LABELS:
                if key not in alloc:
                    alloc[key] = 0
            plan["allocation"] = alloc
    return result


def generate_roadmap(
    profile: dict,
    macro: dict,
) -> dict:
    client = create_anthropic_client()
    prompt = _build_roadmap_prompt(profile, macro)
    message = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=5500,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json_response(message.content[0].text)


def build_allocation_pie(allocation: dict, title: str) -> go.Figure:
    labels: list[str] = []
    values: list[float] = []
    colors: list[str] = []
    for key, label in ALLOCATION_LABELS.items():
        val = float(allocation.get(key, 0) or 0)
        if val > 0:
            labels.append(label)
            values.append(val)
            colors.append(ALLOCATION_COLORS[key])

    if not values:
        labels = list(ALLOCATION_LABELS.values())
        values = [25.0, 25.0, 25.0, 25.0]
        colors = list(ALLOCATION_COLORS.values())

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.35,
                marker=dict(colors=colors),
                textinfo="label+percent",
                textposition="outside",
                hovertemplate="%{label}: %{value:.1f}%<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title=dict(text=title, x=0, font=dict(size=15)),
        height=340,
        margin=dict(l=20, r=20, t=50, b=20),
        showlegend=False,
    )
    return fig


def build_roadmap_macro(
    indicator_snapshot: dict,
    fear_greed: dict,
    sectors: list[dict],
) -> dict:
    return build_macro_context(indicator_snapshot, fear_greed, sectors)


from roadmap_ai import generate_comprehensive_roadmap  # noqa: E402, F401
