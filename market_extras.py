"""CNN Fear & Greed Index 및 S&P500 섹터 데이터."""

from datetime import datetime, timezone

import pandas as pd
import requests
import yfinance as yf

CNN_FNG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://edition.cnn.com/markets/fear-and-greed",
    "Origin": "https://edition.cnn.com",
}

SP500_SECTOR_ETFS: dict[str, str] = {
    "기술": "XLK",
    "헬스케어": "XLV",
    "금융": "XLF",
    "에너지": "XLE",
    "임의소비재": "XLY",
    "필수소비재": "XLP",
    "산업재": "XLI",
    "소재": "XLB",
    "부동산": "XLRE",
    "유틸리티": "XLU",
    "커뮤니케이션": "XLC",
}


def classify_fear_greed(score: float) -> tuple[str, str]:
    value = max(0, min(100, score))
    if value <= 25:
        return "극도 공포", "#dc2626"
    if value <= 45:
        return "공포", "#ea580c"
    if value <= 55:
        return "중립", "#eab308"
    if value <= 75:
        return "탐욕", "#84cc16"
    return "극도 탐욕", "#16a34a"


def fetch_fear_greed_index() -> dict:
    response = requests.get(CNN_FNG_URL, headers=CNN_HEADERS, timeout=20)
    response.raise_for_status()
    payload = response.json()
    fng = payload.get("fear_and_greed") or {}
    score = float(fng.get("score", 0))
    label, color = classify_fear_greed(score)
    return {
        "score": round(score, 1),
        "label": label,
        "color": color,
        "rating_en": fng.get("rating", ""),
        "previous_close": fng.get("previous_close"),
        "previous_1_week": fng.get("previous_1_week"),
        "timestamp": fng.get("timestamp", ""),
        "as_of": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
    }


def _week_return_pct(close: pd.Series) -> float:
    series = close.dropna()
    if len(series) < 2:
        raise ValueError("주가 데이터 부족")
    lookback = -6 if len(series) >= 6 else 0
    start = float(series.iloc[lookback])
    end = float(series.iloc[-1])
    if start == 0:
        raise ValueError("시작 가격 0")
    return (end / start - 1) * 100


def fetch_sector_week_returns() -> list[dict]:
    tickers = list(SP500_SECTOR_ETFS.values())
    names = list(SP500_SECTOR_ETFS.keys())
    hist = yf.download(tickers, period="14d", progress=False, auto_adjust=True)

    if hist.empty:
        raise ValueError("섹터 ETF 데이터 없음")

    close = hist["Close"] if "Close" in hist.columns else hist
    results = []
    for idx, (name, ticker) in enumerate(zip(names, tickers)):
        if isinstance(close, pd.DataFrame):
            if ticker in close.columns:
                series = close[ticker]
            elif isinstance(close.columns, pd.MultiIndex):
                series = close[("Close", ticker)]
            else:
                series = close.iloc[:, idx]
        else:
            series = close
        ret = _week_return_pct(series)
        results.append({"sector": name, "ticker": ticker, "return_pct": round(ret, 2)})

    return results
