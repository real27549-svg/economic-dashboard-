"""Claude 기반 AI 종목 추천 및 재무 차트."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Literal

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

from ai_outlook import (
    DEFAULT_MODEL,
    KR_INDICATOR_KEYS,
    US_INDICATOR_KEYS,
    create_anthropic_client,
    pick_indicators,
)
from stock_search import fetch_stock_profile
from pick_analysis import build_pick_analysis

MarketType = Literal["us", "kr"]

PICK_COUNT = 5


def build_macro_context(
    snapshot: dict,
    fear_greed: dict,
    sectors: list[dict],
) -> dict:
    """거시 지표 + 공포탐욕 + 섹터 히트맵을 Claude 프롬프트용 dict로 묶습니다."""
    sorted_sectors = sorted(sectors, key=lambda item: item["return_pct"], reverse=True)
    top3 = sorted_sectors[:3]
    bottom3 = sorted_sectors[-3:] if len(sorted_sectors) >= 3 else sorted_sectors

    return {
        "indicators": snapshot,
        "fear_greed": {
            "score": fear_greed.get("score"),
            "label": fear_greed.get("label"),
            "previous_close": fear_greed.get("previous_close"),
        },
        "sectors_top": [
            {"sector": item["sector"], "return_pct": item["return_pct"]} for item in top3
        ],
        "sectors_bottom": [
            {"sector": item["sector"], "return_pct": item["return_pct"]} for item in bottom3
        ],
        "as_of": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
    }


def _format_macro_block(macro: dict, market: MarketType) -> str:
    keys = US_INDICATOR_KEYS if market == "us" else KR_INDICATOR_KEYS
    indicators = pick_indicators(macro.get("indicators", {}), keys)
    lines = [
        f"- {item['label']}: {item['value']} (기준일 {item['date']})"
        for item in indicators.values()
    ]
    indicator_text = "\n".join(lines) if lines else "(지표 없음)"

    fng = macro.get("fear_greed", {})
    fng_line = ""
    if fng.get("score") is not None:
        fng_line = (
            f"\n\n[CNN Fear & Greed Index]\n"
            f"- 점수: {fng['score']}/100 ({fng.get('label', '')})"
        )

    sector_lines = []
    for label, items in (("강세 섹터 (1주)", macro.get("sectors_top", [])), ("약세 섹터 (1주)", macro.get("sectors_bottom", []))):
        if items:
            sector_lines.append(f"\n[{label}]")
            for item in items:
                sector_lines.append(f"- {item['sector']}: {item['return_pct']:+.2f}%")
    sector_text = "\n".join(sector_lines)

    return f"{indicator_text}{fng_line}{sector_text}"


def _build_picks_prompt(market: MarketType, macro: dict) -> str:
    market_name = "미국 주식시장(미장)" if market == "us" else "한국 주식시장(국장)"
    ticker_hint = (
        "미국 상장 티커 (예: AAPL, MSFT, NVDA)"
        if market == "us"
        else "한국 상장 티커 (예: 005930.KS, 000660.KS, 035420.KS)"
    )
    unit_hint = "10억 달러(B USD)" if market == "us" else "1조 원(조 KRW, 숫자는 조 단위)"
    current_year = datetime.now().year
    y1, y2 = current_year + 1, current_year + 2

    macro_text = _format_macro_block(macro, market)

    return f"""당신은 거시경제와 개별 종목을 연결해 설명하는 주식 애널리스트입니다.

아래는 {market_name} 분석에 사용할 최신 거시·시장 데이터입니다:
{macro_text}

위 환경(금리, 인플레, VIX, 공포탐욕, 섹터 로테이션 등)을 바탕으로 주목할 만한 상장 종목 {PICK_COUNT}개를 추천하세요.
- {ticker_hint}
- 서로 다른 섹터·테마를 골라 분산하세요.
- reason에는 위 거시지표와 연결해 왜 지금 환경에 맞는지 설명하세요.
- 단정적 수익 보장·매수 권유는 금지하고, "가능성", "주의" 표현을 사용하세요.
- intro는 한국어 1~2문장, reason 2~3문장, caution 1~2문장(리스크).

매출·영업이익 전망({y1}E, {y2}E)은 {unit_hint} 단위로 합리적 추정치를 넣으세요.
(yfinance 애널리스트 추정치가 없을 때 차트에 사용됩니다)

반드시 아래 JSON만 출력하세요:
{{
  "picks": [
    {{
      "symbol": "티커",
      "name": "회사명",
      "intro": "기업 소개 (한국어)",
      "reason": "추천 이유 (거시지표 연결)",
      "caution": "투자 주의사항",
      "forecast": {{
        "years": ["{y1}E", "{y2}E"],
        "revenue": [0, 0],
        "operating_income": [0, 0]
      }}
    }}
  ]
}}"""


def _parse_claude_picks(text: str) -> list[dict]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    result = json.loads(cleaned)
    picks = result.get("picks", [])
    if not picks:
        raise ValueError("AI가 추천 종목을 반환하지 않았습니다.")
    return picks[:PICK_COUNT]


def analyze_stock_picks(market: MarketType, macro: dict) -> list[dict]:
    client = create_anthropic_client()
    prompt = _build_picks_prompt(market, macro)
    message = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=3500,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_picks = _parse_claude_picks(message.content[0].text)
    return [enrich_pick(pick, market) for pick in raw_picks]


def _is_korean_symbol(symbol: str) -> bool:
    return symbol.endswith((".KS", ".KQ"))


def _scale_amount(value: float, symbol: str) -> float:
    """원화는 조(KRW T), 달러는 10억(B USD) 단위로 통일."""
    if _is_korean_symbol(symbol):
        return value / 1e12
    return value / 1e9


def _unit_label(symbol: str) -> str:
    return "조 KRW" if _is_korean_symbol(symbol) else "B USD"


def _find_income_row(df: pd.DataFrame, labels: list[str]) -> pd.Series | None:
    for label in labels:
        if label in df.index:
            return df.loc[label]
    for idx in df.index:
        idx_str = str(idx).lower()
        for label in labels:
            if label.lower() in idx_str:
                return df.loc[idx]
    return None


def fetch_company_financials(symbol: str) -> dict | None:
    stock = yf.Ticker(symbol)
    income = stock.income_stmt
    if income is None or income.empty:
        income = stock.financials
    if income is None or income.empty:
        return None

    revenue_row = _find_income_row(
        income,
        ["Total Revenue", "Revenue", "Operating Revenue", "Net Revenue"],
    )
    op_row = _find_income_row(
        income,
        ["Operating Income", "EBIT", "Total Operating Income As Reported"],
    )
    if revenue_row is None:
        return None

    years = sorted(
        [col for col in revenue_row.index if hasattr(col, "year") or str(col)[:4].isdigit()],
        key=lambda x: str(x),
    )
    if not years:
        years = list(revenue_row.index)

    actual_years: list[str] = []
    revenues: list[float] = []
    op_incomes: list[float | None] = []
    for year_col in years[-3:]:
        year_label = str(year_col.year) if hasattr(year_col, "year") else str(year_col)[:4]
        rev = revenue_row.get(year_col)
        if rev is None or pd.isna(rev):
            continue
        actual_years.append(year_label)
        revenues.append(_scale_amount(float(rev), symbol))
        op_val = op_row.get(year_col) if op_row is not None else None
        op_incomes.append(
            _scale_amount(float(op_val), symbol)
            if op_val is not None and not pd.isna(op_val)
            else None
        )

    if not actual_years:
        return None

    forecast_years: list[str] = []
    forecast_revenues: list[float] = []
    forecast_op_incomes: list[float | None] = []
    forecast_source = "추정"

    try:
        estimates = stock.revenue_estimate
        if estimates is not None and not estimates.empty:
            for idx, row in estimates.head(2).iterrows():
                year_label = f"{idx}E"
                avg = row.get("avg") if "avg" in row else row.iloc[0]
                if avg is not None and not pd.isna(avg):
                    forecast_years.append(year_label)
                    forecast_revenues.append(_scale_amount(float(avg), symbol))
    except Exception:
        pass

    if forecast_years:
        forecast_source = "yfinance 애널리스트"

    return {
        "actual_years": actual_years,
        "revenues": revenues,
        "op_incomes": op_incomes,
        "forecast_years": forecast_years,
        "forecast_revenues": forecast_revenues,
        "forecast_op_incomes": forecast_op_incomes,
        "unit": _unit_label(symbol),
        "forecast_source": forecast_source,
    }


def _apply_claude_forecast(financials: dict | None, claude_forecast: dict | None, symbol: str) -> dict | None:
    if financials is None:
        return None
    if not claude_forecast:
        _fill_growth_forecast(financials)
        return financials

    years = claude_forecast.get("years") or []
    revs = claude_forecast.get("revenue") or []
    ops = claude_forecast.get("operating_income") or []

    if not financials.get("forecast_years") and years and revs:
        financials["forecast_years"] = [str(y) for y in years[:2]]
        financials["forecast_revenues"] = [float(v) for v in revs[:2]]
        financials["forecast_op_incomes"] = [
            float(v) if v is not None else None for v in (ops[:2] if ops else [])
        ]
        financials["forecast_source"] = "Claude AI 추정"
    elif not financials.get("forecast_op_incomes") and ops:
        financials["forecast_op_incomes"] = [
            float(v) if v is not None else None for v in ops[: len(financials.get("forecast_years", []))]
        ]

    if not financials.get("forecast_years"):
        _fill_growth_forecast(financials)
    return financials


def _fill_growth_forecast(financials: dict) -> None:
    """애널리스트·Claude 전망이 없을 때 최근 성장률로 단순 extrapolation."""
    revenues = financials.get("revenues") or []
    op_incomes = financials.get("op_incomes") or []
    actual_years = financials.get("actual_years") or []
    if financials.get("forecast_years"):
        return
    if len(revenues) < 2 or revenues[-2] == 0:
        return

    rev_growth = revenues[-1] / revenues[-2] - 1
    op_growth = None
    if len(op_incomes) >= 2 and op_incomes[-2] not in (None, 0) and op_incomes[-1] is not None:
        op_growth = op_incomes[-1] / op_incomes[-2] - 1

    last_year = int(actual_years[-1]) if actual_years else datetime.now().year
    fy: list[str] = []
    fr: list[float] = []
    fo: list[float | None] = []
    for offset in (1, 2):
        fy.append(f"{last_year + offset}E")
        fr.append(revenues[-1] * ((1 + rev_growth) ** offset))
        if op_growth is not None and op_incomes[-1] is not None:
            fo.append(op_incomes[-1] * ((1 + op_growth) ** offset))
        else:
            fo.append(None)
    financials["forecast_years"] = fy
    financials["forecast_revenues"] = fr
    financials["forecast_op_incomes"] = fo
    financials["forecast_source"] = "과거 성장률 기반 단순 추정"


def _infer_market(symbol: str) -> MarketType:
    return "kr" if symbol.endswith((".KS", ".KQ")) else "us"


def _attach_pick_market_data(
    base: dict,
    market: MarketType,
    *,
    claude_forecast: dict | None = None,
    profile: dict | None = None,
) -> dict:
    symbol = base.get("symbol", "")
    if not symbol:
        return base

    if profile:
        base.update(
            {
                "symbol": profile["symbol"],
                "name": base.get("name") or profile["name"],
                "price_fmt": profile.get("price_fmt", "N/A"),
                "per_fmt": profile.get("per_fmt", "N/A"),
                "market_cap_fmt": profile.get("market_cap_fmt", "N/A"),
            }
        )
    else:
        try:
            fetched = fetch_stock_profile(symbol)
            base.update(
                {
                    "symbol": fetched["symbol"],
                    "name": base.get("name") or fetched["name"],
                    "price_fmt": fetched["price_fmt"],
                    "per_fmt": fetched["per_fmt"],
                    "market_cap_fmt": fetched["market_cap_fmt"],
                }
            )
        except Exception:
            pass

    try:
        financials = fetch_company_financials(symbol)
        financials = _apply_claude_forecast(financials, claude_forecast, symbol)
        base["financials"] = financials
        if financials:
            src = financials.get("forecast_source", "추정")
            base["forecast_note"] = (
                f"점선 전망: {src} · 단위 {financials.get('unit', '')} · "
                "투자 참고용이며 실제 실적과 다를 수 있습니다."
            )
    except Exception:
        pass

    try:
        base["analysis"] = build_pick_analysis(
            symbol=base["symbol"],
            market=market,
            name=base["name"],
        )
    except Exception:
        pass

    return base


def enrich_pick(pick: dict, market: MarketType) -> dict:
    symbol = str(pick.get("symbol", "")).strip()
    base = {
        "symbol": symbol,
        "name": pick.get("name") or symbol,
        "intro": str(pick.get("intro", "")).strip(),
        "reason": str(pick.get("reason", "")).strip(),
        "caution": str(pick.get("caution", "")).strip(),
        "price_fmt": "N/A",
        "per_fmt": "N/A",
        "market_cap_fmt": "N/A",
        "financials": None,
        "forecast_note": "",
        "analysis": None,
    }
    if not symbol:
        return base
    return _attach_pick_market_data(
        base,
        market,
        claude_forecast=pick.get("forecast"),
    )


def build_pick_from_profile(profile: dict) -> dict:
    """종목 검색 등 profile dict → AI 추천 카드와 동일한 pick 구조."""
    symbol = profile["symbol"]
    market = _infer_market(symbol)
    base = {
        "symbol": symbol,
        "name": profile.get("name") or symbol,
        "intro": "",
        "reason": "",
        "caution": "",
        "price_fmt": profile.get("price_fmt", "N/A"),
        "per_fmt": profile.get("per_fmt", "N/A"),
        "market_cap_fmt": profile.get("market_cap_fmt", "N/A"),
        "financials": None,
        "forecast_note": "",
        "analysis": None,
    }
    return _attach_pick_market_data(base, market, profile=profile)


def build_financial_chart(pick: dict) -> go.Figure | None:
    financials = pick.get("financials")
    if not financials:
        return None
    return build_pick_financial_chart(financials, pick.get("name", pick.get("symbol", "")))


def build_pick_financial_chart(financials: dict, name: str) -> go.Figure:
    fig = go.Figure()
    years = financials["actual_years"]
    unit = financials.get("unit", "B")

    fig.add_trace(
        go.Bar(
            x=years,
            y=financials["revenues"],
            name="매출 (실적)",
            marker_color="#2563eb",
            hovertemplate="%{x}<br>매출: %{y:,.2f}<extra></extra>",
        )
    )
    if any(v is not None for v in financials["op_incomes"]):
        fig.add_trace(
            go.Bar(
                x=years,
                y=[v if v is not None else 0 for v in financials["op_incomes"]],
                name="영업이익 (실적)",
                marker_color="#16a34a",
                hovertemplate="%{x}<br>영업이익: %{y:,.2f}<extra></extra>",
            )
        )

    f_years = financials.get("forecast_years") or []
    f_revs = financials.get("forecast_revenues") or []
    f_ops = financials.get("forecast_op_incomes") or []

    if f_years and f_revs:
        bridge_x = [years[-1]] + f_years
        bridge_rev = [financials["revenues"][-1]] + f_revs
        fig.add_trace(
            go.Scatter(
                x=bridge_x,
                y=bridge_rev,
                mode="lines+markers",
                name="매출 전망",
                line=dict(color="#f59e0b", width=2, dash="dash"),
                marker=dict(size=8, symbol="diamond"),
                hovertemplate="%{x}<br>매출 전망: %{y:,.2f}<extra></extra>",
            )
        )

    if f_years and f_ops and any(v is not None for v in f_ops):
        last_op = next((v for v in reversed(financials["op_incomes"]) if v is not None), 0)
        bridge_x = [years[-1]] + f_years
        bridge_op = [last_op] + [v if v is not None else None for v in f_ops]
        fig.add_trace(
            go.Scatter(
                x=bridge_x,
                y=bridge_op,
                mode="lines+markers",
                name="영업이익 전망",
                line=dict(color="#dc2626", width=2, dash="dash"),
                marker=dict(size=8, symbol="diamond-open"),
                hovertemplate="%{x}<br>영업이익 전망: %{y:,.2f}<extra></extra>",
            )
        )

    fig.update_layout(
        title=dict(text=f"{name} — 매출·영업이익 (최근 3년 + 2년 전망)", x=0, font=dict(size=16)),
        barmode="group",
        xaxis_title="연도",
        yaxis_title=f"금액 ({unit})",
        height=340,
        margin=dict(l=40, r=20, t=50, b=40),
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig
