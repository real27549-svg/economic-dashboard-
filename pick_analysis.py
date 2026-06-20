"""AI 종목 추천 카드용 심화 분석 (yfinance + AI 추정)."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any, Literal

import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

from ai_outlook import DEFAULT_MODEL, create_anthropic_client

MarketType = Literal["us", "kr"]

_POSITIVE_WORDS = (
    "surge", "gain", "rise", "beat", "record", "growth", "profit", "upgrade",
    "strong", "bull", "상승", "호실적", "증가", "흑자", "긍정", "돌파",
)
_NEGATIVE_WORDS = (
    "fall", "drop", "loss", "miss", "cut", "downgrade", "weak", "bear", "lawsuit",
    "decline", "하락", "적자", "감소", "우려", "리스크", "부진",
)


def _fmt_num(value: float | None, digits: int = 2, suffix: str = "") -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    return f"{value:.{digits}f}{suffix}"


def _fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "N/A"
    return f"{value * 100:.{digits}f}%" if abs(value) <= 1 else f"{value:.{digits}f}%"


def _today() -> date:
    return datetime.now().date()


def _parse_to_date(raw: Any) -> date | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(raw, tz=timezone.utc).date()
        return pd.to_datetime(raw).date()
    except Exception:
        return None


def _fmt_amount_kr(value: float) -> str:
    """스케일된 값(조 단위) → '23.5조원' 형식."""
    if value >= 1:
        return f"{value:.1f}조원"
    if value >= 0.01:
        return f"{value * 10000:.0f}억원"
    return f"{value * 1e12:,.0f}원"


def _fmt_amount_us(value: float) -> str:
    """스케일된 값(10억 달러 단위) → '$23.5B' 형식."""
    return f"${value:.1f}B"


def _fmt_amount(value: float, symbol: str) -> str:
    if symbol.endswith((".KS", ".KQ")):
        return _fmt_amount_kr(value)
    return _fmt_amount_us(value)


def _yaxis_unit(symbol: str) -> str:
    return "조원" if symbol.endswith((".KS", ".KQ")) else "B USD"


def _find_row(df: pd.DataFrame, labels: list[str]) -> pd.Series | None:
    for label in labels:
        if label in df.index:
            return df.loc[label]
    for idx in df.index:
        idx_str = str(idx).lower()
        for label in labels:
            if label.lower() in idx_str:
                return df.loc[idx]
    return None


def _scale_quarterly(value: float, symbol: str) -> float:
    if symbol.endswith((".KS", ".KQ")):
        return value / 1e12
    return value / 1e9


def _quarter_label(col: Any) -> str:
    if hasattr(col, "year") and hasattr(col, "month"):
        q = (col.month - 1) // 3 + 1
        return f"{col.year}Q{q}"
    text = str(col)
    return text[:7] if len(text) >= 7 else text


def _fetch_quarterly_financials(symbol: str) -> dict | None:
    stock = yf.Ticker(symbol)
    income = stock.quarterly_income_stmt
    if income is None or income.empty:
        income = stock.quarterly_financials
    if income is None or income.empty:
        return None

    revenue_row = _find_row(
        income,
        ["Total Revenue", "Revenue", "Operating Revenue", "Net Revenue"],
    )
    if revenue_row is None:
        return None

    op_row = _find_row(
        income,
        ["Operating Income", "EBIT", "Total Operating Income As Reported"],
    )

    cols = sorted(revenue_row.index, key=lambda x: str(x))[-8:]
    periods: list[str] = []
    revenues: list[float] = []
    op_incomes: list[float | None] = []
    for col in cols:
        rev = revenue_row.get(col)
        if rev is None or pd.isna(rev):
            continue
        periods.append(_quarter_label(col))
        revenues.append(_scale_quarterly(float(rev), symbol))
        op_val = op_row.get(col) if op_row is not None else None
        op_incomes.append(
            _scale_quarterly(float(op_val), symbol)
            if op_val is not None and not pd.isna(op_val)
            else None
        )

    if not periods:
        return None

    unit = "조 KRW" if symbol.endswith((".KS", ".KQ")) else "B USD"
    return {
        "symbol": symbol,
        "periods": periods,
        "revenues": revenues,
        "op_incomes": op_incomes,
        "unit": unit,
        "source": "yfinance",
    }


def _collect_future_earnings_dates(stock: yf.Ticker, info: dict) -> list[date]:
    """yfinance에서 수집한 실적 발표 후보 중 오늘 이후 날짜만."""
    today = _today()
    found: list[date] = []

    for key in ("earningsTimestamp", "nextEarningsDate"):
        parsed = _parse_to_date(info.get(key))
        if parsed and parsed > today:
            found.append(parsed)

    try:
        cal = stock.calendar
        if isinstance(cal, dict) and cal.get("Earnings Date"):
            val = cal["Earnings Date"]
            items = val if isinstance(val, list) else [val]
            for item in items:
                parsed = _parse_to_date(item)
                if parsed and parsed > today:
                    found.append(parsed)
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            for idx in cal.index:
                parsed = _parse_to_date(idx)
                if parsed and parsed > today:
                    found.append(parsed)
    except Exception:
        pass

    try:
        dates_df = stock.earnings_dates
        if dates_df is not None and not dates_df.empty:
            for idx in dates_df.index:
                parsed = _parse_to_date(idx)
                if parsed and parsed > today:
                    found.append(parsed)
    except Exception:
        pass

    return sorted(set(found))


def _fetch_earnings_date(stock: yf.Ticker, info: dict) -> dict:
    future_dates = _collect_future_earnings_dates(stock, info)
    disclaimer = "※ 참고용, 실제와 다를 수 있음"

    if future_dates:
        next_date = future_dates[0]
        date_str = next_date.strftime("%Y-%m-%d")
        return {
            "date": date_str,
            "fmt": date_str,
            "source": "yfinance",
            "disclaimer": disclaimer,
        }

    return {
        "date": None,
        "fmt": "미정",
        "source": "yfinance",
        "disclaimer": disclaimer,
    }


def _fetch_earnings_surprise(stock: yf.Ticker) -> dict:
    result = {
        "has_data": False,
        "beat": None,
        "estimate": None,
        "actual": None,
        "surprise_pct": None,
        "fmt": "N/A",
        "source": "AI 추정",
    }
    try:
        history = stock.get_earnings_history()
        if history is not None and not history.empty:
            row = history.iloc[0]
            est = row.get("epsEstimate") or row.get("Estimate")
            act = row.get("epsActual") or row.get("Reported EPS") or row.get("Actual")
            if est is not None and act is not None and not pd.isna(est) and not pd.isna(act):
                est_f, act_f = float(est), float(act)
                surprise = ((act_f - est_f) / abs(est_f) * 100) if est_f != 0 else None
                beat = act_f >= est_f
                result.update(
                    {
                        "has_data": True,
                        "beat": beat,
                        "estimate": est_f,
                        "actual": act_f,
                        "surprise_pct": surprise,
                        "fmt": (
                            f"{'서프라이즈(↑)' if beat else '미스(↓)'} · "
                            f"예상 EPS {est_f:.2f} → 실제 {act_f:.2f}"
                            + (f" ({surprise:+.1f}%)" if surprise is not None else "")
                        ),
                        "source": "yfinance",
                    }
                )
                return result
    except Exception:
        pass

    try:
        dates = stock.earnings_dates
        if dates is not None and not dates.empty:
            for _, row in dates.iterrows():
                est = row.get("EPS Estimate")
                act = row.get("Reported EPS")
                if est is not None and act is not None and not pd.isna(est) and not pd.isna(act):
                    est_f, act_f = float(est), float(act)
                    surprise = ((act_f - est_f) / abs(est_f) * 100) if est_f != 0 else None
                    beat = act_f >= est_f
                    result.update(
                        {
                            "has_data": True,
                            "beat": beat,
                            "estimate": est_f,
                            "actual": act_f,
                            "surprise_pct": surprise,
                            "fmt": (
                                f"{'서프라이즈(↑)' if beat else '미스(↓)'} · "
                                f"예상 EPS {est_f:.2f} → 실제 {act_f:.2f}"
                                + (f" ({surprise:+.1f}%)" if surprise is not None else "")
                            ),
                            "source": "yfinance",
                        }
                    )
                    return result
    except Exception:
        pass

    return result


def _fetch_ratios(info: dict, stock: yf.Ticker) -> dict:
    pbr = info.get("priceToBook")
    roe = info.get("returnOnEquity")
    per = info.get("trailingPE") or info.get("forwardPE")
    debt_to_equity = info.get("debtToEquity")

    if debt_to_equity is None:
        try:
            bs = stock.balance_sheet
            if bs is not None and not bs.empty:
                debt_row = _find_row(bs, ["Total Debt", "Long Term Debt And Capital Lease Obligation"])
                equity_row = _find_row(bs, ["Stockholders Equity", "Total Equity Gross Minority Interest"])
                if debt_row is not None and equity_row is not None:
                    debt = debt_row.iloc[0]
                    equity = equity_row.iloc[0]
                    if equity and not pd.isna(equity) and float(equity) != 0:
                        debt_to_equity = float(debt) / float(equity) * 100
        except Exception:
            pass

    return {
        "pbr": {
            "value": float(pbr) if pbr is not None and not pd.isna(pbr) else None,
            "fmt": _fmt_num(float(pbr) if pbr is not None else None),
            "source": "yfinance" if pbr is not None else "AI 추정",
        },
        "roe": {
            "value": float(roe) if roe is not None and not pd.isna(roe) else None,
            "fmt": _fmt_pct(float(roe) if roe is not None else None),
            "source": "yfinance" if roe is not None else "AI 추정",
        },
        "per": {
            "value": float(per) if per is not None and not pd.isna(per) else None,
            "fmt": _fmt_num(float(per) if per is not None else None),
            "source": "yfinance" if per is not None else "AI 추정",
        },
        "debt_ratio": {
            "value": float(debt_to_equity) if debt_to_equity is not None else None,
            "fmt": (
                _fmt_num(float(debt_to_equity), 1, "%")
                if debt_to_equity is not None
                else "N/A"
            ),
            "source": "yfinance" if debt_to_equity is not None else "AI 추정",
        },
    }


def _fetch_52w_position(info: dict, price: float | None) -> dict:
    high = info.get("fiftyTwoWeekHigh")
    low = info.get("fiftyTwoWeekLow")
    if price is None:
        price = info.get("regularMarketPrice") or info.get("currentPrice")
    position_pct = None
    if (
        price is not None
        and high is not None
        and low is not None
        and not pd.isna(high)
        and not pd.isna(low)
        and float(high) > float(low)
    ):
        position_pct = (float(price) - float(low)) / (float(high) - float(low)) * 100

    currency = info.get("currency") or "USD"
    return {
        "price": float(price) if price is not None else None,
        "high": float(high) if high is not None else None,
        "low": float(low) if low is not None else None,
        "position_pct": position_pct,
        "currency": currency,
        "source": "yfinance" if position_pct is not None else "AI 추정",
    }


def _fetch_target_price(info: dict, symbol: str) -> dict:
    mean = info.get("targetMeanPrice")
    currency = info.get("currency") or ("KRW" if symbol.endswith((".KS", ".KQ")) else "USD")

    if mean is not None and not pd.isna(mean):
        mean_f = float(mean)
        if currency == "KRW":
            fmt = f"{mean_f:,.0f}원"
        else:
            fmt = f"${mean_f:,.2f}"
        return {
            "mean": mean_f,
            "fmt": fmt,
            "source": "yfinance",
        }

    return {
        "mean": None,
        "fmt": "데이터 없음",
        "source": "yfinance",
    }


def _fetch_dividend(stock: yf.Ticker, info: dict, symbol: str) -> dict:
    div_yield = info.get("dividendYield") or info.get("trailingAnnualDividendYield")
    history_rows: list[dict] = []
    try:
        divs = stock.dividends
        if divs is not None and not divs.empty:
            divs = divs.copy()
            divs.index = pd.to_datetime(divs.index)
            if divs.index.tz is not None:
                divs.index = divs.index.tz_localize(None)
            yearly = divs.groupby(divs.index.year).sum().tail(3)
            for year, amount in yearly.items():
                history_rows.append({"year": int(year), "amount": float(amount)})
    except Exception:
        pass

    yield_pct = None
    if div_yield is not None and not pd.isna(div_yield):
        yield_pct = float(div_yield) * 100 if float(div_yield) <= 1 else float(div_yield)

    currency = "원" if symbol.endswith((".KS", ".KQ")) else "$"
    return {
        "yield_pct": yield_pct,
        "yield_fmt": _fmt_num(yield_pct, 2, "%") if yield_pct is not None else "N/A",
        "history": history_rows,
        "history_fmt": ", ".join(
            f"{row['year']}: {row['amount']:.2f}{currency}" for row in history_rows
        )
        if history_rows
        else "N/A",
        "source": "yfinance" if yield_pct is not None or history_rows else "AI 추정",
    }


def _keyword_sentiment(titles: list[str]) -> dict | None:
    if not titles:
        return None
    pos = neg = neu = 0
    for title in titles:
        lower = title.lower()
        p = sum(1 for w in _POSITIVE_WORDS if w in lower)
        n = sum(1 for w in _NEGATIVE_WORDS if w in lower)
        if p > n:
            pos += 1
        elif n > p:
            neg += 1
        else:
            neu += 1
    total = pos + neg + neu
    if total == 0:
        return None
    return {
        "positive": round(pos / total * 100),
        "negative": round(neg / total * 100),
        "neutral": round(neu / total * 100),
        "source": "뉴스 키워드 분석",
        "summary": f"최근 {total}건 뉴스 헤드라인 기준",
    }


def _fetch_news_titles(stock: yf.Ticker) -> list[str]:
    titles: list[str] = []
    try:
        for item in (stock.news or [])[:10]:
            content = item.get("content", item)
            title = content.get("title")
            if title:
                titles.append(str(title))
    except Exception:
        pass
    return titles


def _fetch_peer_metrics(symbol: str, info: dict) -> list[dict]:
    peers: list[str] = []
    rec = info.get("recommendedSymbols") or info.get("competitors")
    if isinstance(rec, list):
        peers = [str(s) for s in rec[:3]]
    elif isinstance(rec, str):
        peers = [s.strip() for s in rec.split(",")[:3]]

    rows: list[dict] = []
    for peer in peers:
        try:
            p_info = yf.Ticker(peer).info or {}
            rows.append(
                {
                    "symbol": peer,
                    "name": p_info.get("shortName") or peer,
                    "per": p_info.get("trailingPE") or p_info.get("forwardPE"),
                    "pbr": p_info.get("priceToBook"),
                    "roe": p_info.get("returnOnEquity"),
                    "source": "yfinance",
                }
            )
        except Exception:
            continue
    return rows


def _missing_fields(analysis: dict) -> list[str]:
    missing: list[str] = []
    if not analysis.get("quarterly"):
        missing.append("quarterly")
    if not analysis["earnings_surprise"].get("has_data"):
        missing.append("earnings_surprise")
    for key in ("pbr", "roe", "debt_ratio"):
        if analysis["ratios"][key].get("value") is None:
            missing.append(key)
    if analysis["price_position_52w"].get("position_pct") is None:
        missing.append("price_position_52w")
    if analysis["dividend"].get("yield_pct") is None and not analysis["dividend"].get("history"):
        missing.append("dividend")
    if not analysis["news_sentiment"]:
        missing.append("news_sentiment")
    if len(analysis["peer_comparison"]) < 2:
        missing.append("peer_comparison")
    return missing


def _fill_gaps_with_ai(
    symbol: str,
    name: str,
    market: MarketType,
    analysis: dict,
    news_titles: list[str],
    missing: list[str],
) -> dict:
    if not missing:
        return analysis

    context = {
        "symbol": symbol,
        "name": name,
        "market": market,
        "sector": analysis.get("sector"),
        "industry": analysis.get("industry"),
        "news_titles": news_titles[:8],
        "known": {
            "per": analysis["ratios"]["per"].get("value"),
            "pbr": analysis["ratios"]["pbr"].get("value"),
            "roe": analysis["ratios"]["roe"].get("value"),
            "price": analysis["price_position_52w"].get("price"),
        },
    }
    prompt = f"""주식 애널리스트로서 아래 종목의 부족한 분석 항목을 합리적으로 추정하세요.
단정적 투자 권유는 금지. 숫자는 업종·규모에 맞게 현실적으로.

종목: {name} ({symbol})
컨텍스트: {json.dumps(context, ensure_ascii=False)}

채워야 할 항목: {", ".join(missing)}

반드시 JSON만 출력:
{{
  "earnings_surprise": {{"beat": true/false, "estimate": 0, "actual": 0, "surprise_pct": 0, "note": "한국어 설명"}},
  "pbr": 0,
  "roe": 0.0,
  "debt_ratio": 0.0,
  "price_position_52w_pct": 0,
  "dividend": {{"yield_pct": 0, "history": [{{"year": 2023, "amount": 0}}]}},
  "news_sentiment": {{"positive": 0, "negative": 0, "neutral": 100, "summary": "한국어"}},
  "peer_comparison": [
    {{"symbol": "티커", "name": "회사명", "per": 0, "pbr": 0, "roe": 0.0}}
  ],
  "quarterly": {{
    "periods": ["2024Q1","2024Q2"],
    "revenues": [0,0],
    "op_incomes": [0,0],
    "unit": "B USD 또는 조 KRW"
  }}
}}"""

    try:
        client = create_anthropic_client()
        message = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=1800,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        ai = json.loads(text)
    except Exception:
        return analysis

    if "earnings_surprise" in missing and ai.get("earnings_surprise"):
        es = ai["earnings_surprise"]
        analysis["earnings_surprise"] = {
            "has_data": True,
            "beat": es.get("beat"),
            "estimate": es.get("estimate"),
            "actual": es.get("actual"),
            "surprise_pct": es.get("surprise_pct"),
            "fmt": es.get("note") or "AI 추정",
            "source": "AI 추정",
        }

    for key, ai_key in (("pbr", "pbr"), ("roe", "roe"), ("debt_ratio", "debt_ratio")):
        if key in missing and ai.get(ai_key) is not None:
            val = float(ai[ai_key])
            fmt = _fmt_pct(val) if key == "roe" else _fmt_num(val, 1, "%" if key == "debt_ratio" else "")
            analysis["ratios"][key] = {"value": val, "fmt": fmt, "source": "AI 추정"}

    if "price_position_52w" in missing and ai.get("price_position_52w_pct") is not None:
        analysis["price_position_52w"]["position_pct"] = float(ai["price_position_52w_pct"])
        analysis["price_position_52w"]["source"] = "AI 추정"

    if "dividend" in missing and ai.get("dividend"):
        d = ai["dividend"]
        history = d.get("history") or []
        analysis["dividend"] = {
            "yield_pct": d.get("yield_pct"),
            "yield_fmt": _fmt_num(d.get("yield_pct"), 2, "%"),
            "history": history,
            "history_fmt": ", ".join(f"{h.get('year')}: {h.get('amount')}" for h in history),
            "source": "AI 추정",
        }

    if "news_sentiment" in missing and ai.get("news_sentiment"):
        ns = ai["news_sentiment"]
        analysis["news_sentiment"] = {
            "positive": ns.get("positive", 33),
            "negative": ns.get("negative", 33),
            "neutral": ns.get("neutral", 34),
            "source": "AI 추정",
            "summary": ns.get("summary", ""),
        }

    if "peer_comparison" in missing and ai.get("peer_comparison"):
        analysis["peer_comparison"] = [
            {
                "symbol": row.get("symbol", ""),
                "name": row.get("name", ""),
                "per": row.get("per"),
                "pbr": row.get("pbr"),
                "roe": row.get("roe"),
                "source": "AI 추정",
            }
            for row in ai["peer_comparison"][:4]
        ]

    if "quarterly" in missing and ai.get("quarterly"):
        q = ai["quarterly"]
        if q.get("periods") and q.get("revenues"):
            analysis["quarterly"] = {
                "symbol": symbol,
                "periods": q["periods"][-8:],
                "revenues": q["revenues"][-8:],
                "op_incomes": (q.get("op_incomes") or [None] * len(q["periods"]))[-8:],
                "unit": q.get("unit") or ("조 KRW" if market == "kr" else "B USD"),
                "source": "AI 추정",
            }

    return analysis


def build_pick_analysis(symbol: str, market: MarketType, name: str) -> dict:
    stock = yf.Ticker(symbol)
    info = stock.info or {}
    price = info.get("regularMarketPrice") or info.get("currentPrice")

    news_titles = _fetch_news_titles(stock)
    sentiment = _keyword_sentiment(news_titles)

    analysis: dict[str, Any] = {
        "symbol": symbol,
        "sector": info.get("sector") or info.get("industry"),
        "industry": info.get("industry"),
        "quarterly": _fetch_quarterly_financials(symbol),
        "earnings_date": _fetch_earnings_date(stock, info),
        "earnings_surprise": _fetch_earnings_surprise(stock),
        "ratios": _fetch_ratios(info, stock),
        "price_position_52w": _fetch_52w_position(info, float(price) if price else None),
        "target_price": _fetch_target_price(info, symbol),
        "dividend": _fetch_dividend(stock, info, symbol),
        "news_sentiment": sentiment,
        "peer_comparison": _fetch_peer_metrics(symbol, info),
    }

    missing = _missing_fields(analysis)
    if missing:
        analysis = _fill_gaps_with_ai(symbol, name, market, analysis, news_titles, missing)

    return analysis


def build_quarterly_chart(quarterly: dict, name: str, symbol: str = "") -> go.Figure:
    fig = go.Figure()
    periods = quarterly["periods"]
    symbol = quarterly.get("symbol") or symbol
    y_unit = _yaxis_unit(symbol)
    rev_labels = [_fmt_amount(v, symbol) for v in quarterly["revenues"]]

    fig.add_trace(
        go.Bar(
            x=periods,
            y=quarterly["revenues"],
            name="매출",
            marker_color="#2563eb",
            text=rev_labels,
            textposition="outside",
            textfont=dict(size=10),
            hovertemplate="%{x}<br>매출: %{customdata}<extra></extra>",
            customdata=rev_labels,
        )
    )
    op_incomes = quarterly.get("op_incomes", [])
    if any(v is not None for v in op_incomes):
        op_values = [v if v is not None else 0 for v in op_incomes]
        op_labels = [
            _fmt_amount(v, symbol) if v is not None else "N/A"
            for v in op_incomes
        ]
        fig.add_trace(
            go.Bar(
                x=periods,
                y=op_values,
                name="영업이익",
                marker_color="#16a34a",
                text=op_labels,
                textposition="outside",
                textfont=dict(size=10),
                hovertemplate="%{x}<br>영업이익: %{customdata}<extra></extra>",
                customdata=op_labels,
            )
        )

    src = quarterly.get("source", "")
    fig.update_layout(
        title=dict(text=f"{name} — 분기별 매출·영업이익 (최근 8분기)", x=0, font=dict(size=15)),
        barmode="group",
        xaxis_title="분기",
        yaxis_title=y_unit,
        height=380,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        uniformtext_minsize=8,
        uniformtext_mode="hide",
    )
    fig.update_yaxes(ticksuffix=f" {y_unit}" if y_unit == "조원" else "")
    if src == "AI 추정":
        fig.add_annotation(
            text="※ AI 추정치 포함",
            xref="paper",
            yref="paper",
            x=1,
            y=1.08,
            showarrow=False,
            font=dict(size=10, color="#64748b"),
        )
    return fig


def build_52w_gauge(position: dict, name: str) -> go.Figure:
    pct = position.get("position_pct") or 50
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=pct,
            number={"suffix": "%", "font": {"size": 28}},
            title={"text": f"{name} — 52주 밴드 내 위치"},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#2563eb"},
                "steps": [
                    {"range": [0, 33], "color": "#fee2e2"},
                    {"range": [33, 66], "color": "#fef9c3"},
                    {"range": [66, 100], "color": "#dcfce7"},
                ],
                "threshold": {
                    "line": {"color": "#0f172a", "width": 3},
                    "thickness": 0.8,
                    "value": pct,
                },
            },
        )
    )
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=60, b=10))
    return fig
