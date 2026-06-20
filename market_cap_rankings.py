"""시가총액 상위 종목 랭킹 (미국 S&P 500 · 한국 KOSPI)."""

from __future__ import annotations

from datetime import datetime, timedelta
from io import StringIO
from typing import Literal

import pandas as pd
import requests

MarketRegion = Literal["us", "kr"]

SP500_LIST_URL = "https://stockanalysis.com/list/sp-500-stocks/"
KRX_CACHE_URL = (
    "https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
    "refs/heads/master/data/listing/krx/{date}.csv"
)
SP500_CSV_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/"
    "master/data/constituents.csv"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _parse_market_cap_text(value: str | float | None) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).replace("$", "").replace(",", "").strip()
    if not text or text in {"-", "N/A", "nan"}:
        return None
    multipliers = {"T": 1e12, "B": 1e9, "M": 1e6, "K": 1e3}
    suffix = text[-1].upper()
    if suffix in multipliers:
        return float(text[:-1]) * multipliers[suffix]
    return float(text)


def _parse_change_pct(value: str | float | None) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).replace("%", "").replace("+", "").strip()
    if not text or text in {"-", "N/A", "nan"}:
        return None
    return float(text)


def _parse_price(value: str | float | None) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).replace("$", "").replace(",", "").replace("원", "").strip()
    if not text or text in {"-", "N/A", "nan"}:
        return None
    return float(text)


def _format_price(value: float | None, currency: str) -> str:
    if value is None:
        return "N/A"
    if currency == "KRW":
        return f"{value:,.0f}원"
    return f"${value:,.2f}"


def _format_market_cap(value: float | None, currency: str) -> str:
    if value is None:
        return "N/A"
    if currency == "KRW":
        if value >= 1e12:
            return f"{value / 1e12:,.1f}조원"
        if value >= 1e8:
            return f"{value / 1e8:,.0f}억원"
        return f"{value:,.0f}원"
    if value >= 1e12:
        return f"${value / 1e12:.2f}T"
    if value >= 1e9:
        return f"${value / 1e9:.2f}B"
    if value >= 1e6:
        return f"${value / 1e6:.2f}M"
    return f"${value:,.0f}"


def _rows_to_dataframe(rows: list[dict], top_n: int) -> pd.DataFrame:
    if not rows:
        raise ValueError("시가총액 데이터를 가져오지 못했습니다.")

    df = pd.DataFrame(rows)
    df = df.sort_values("market_cap", ascending=False).head(top_n).reset_index(drop=True)
    df.insert(0, "rank", range(1, len(df) + 1))
    return df


def _fetch_sp500_from_stockanalysis() -> list[dict]:
    response = requests.get(SP500_LIST_URL, headers=_HEADERS, timeout=30)
    response.raise_for_status()

    tables = pd.read_html(StringIO(response.text))
    if not tables:
        raise ValueError("S&P 500 목록 테이블을 찾지 못했습니다.")

    raw = tables[0]
    required = {"Symbol", "Company Name", "Market Cap", "Stock Price", "% Change"}
    if not required.issubset(set(raw.columns)):
        raise ValueError("S&P 500 목록 형식이 예상과 다릅니다.")

    rows: list[dict] = []
    for _, item in raw.iterrows():
        market_cap = _parse_market_cap_text(item["Market Cap"])
        price = _parse_price(item["Stock Price"])
        if market_cap is None or price is None:
            continue

        change_pct = _parse_change_pct(item["% Change"])
        symbol = str(item["Symbol"]).strip()
        rows.append(
            {
                "ticker": symbol,
                "name": str(item["Company Name"]).strip(),
                "price": price,
                "price_fmt": _format_price(price, "USD"),
                "market_cap": market_cap,
                "market_cap_fmt": _format_market_cap(market_cap, "USD"),
                "change_pct": change_pct,
                "change_pct_fmt": (
                    f"{change_pct:+.2f}%" if change_pct is not None else "N/A"
                ),
                "currency": "USD",
            }
        )
    return rows


def _fetch_sp500_from_constituents() -> list[dict]:
    """Fallback: S&P 500 구성종목 CSV + Wikipedia 시총 표 (stockanalysis 장애 시)."""
    response = requests.get(SP500_CSV_URL, headers=_HEADERS, timeout=25)
    response.raise_for_status()
    constituents = pd.read_csv(StringIO(response.text))
    allowed = set(
        constituents["Symbol"].astype(str).str.replace(".", "-", regex=False).str.strip()
    )

    wiki_response = requests.get(
        "https://en.wikipedia.org/wiki/List_of_public_corporations_by_market_capitalization",
        headers=_HEADERS,
        timeout=25,
    )
    wiki_response.raise_for_status()
    tables = pd.read_html(StringIO(wiki_response.text))
    rows: list[dict] = []
    for table in tables:
        cols = {str(c).lower(): c for c in table.columns}
        symbol_col = cols.get("symbol") or cols.get("ticker")
        cap_col = cols.get("market cap") or cols.get("marketcap")
        name_col = cols.get("name") or cols.get("company")
        if not symbol_col or not cap_col:
            continue
        for _, item in table.iterrows():
            symbol = str(item[symbol_col]).strip().replace(".", "-")
            if symbol not in allowed:
                continue
            market_cap = _parse_market_cap_text(item[cap_col])
            if market_cap is None:
                continue
            name = str(item[name_col]).strip() if name_col else symbol
            rows.append(
                {
                    "ticker": symbol,
                    "name": name,
                    "price": None,
                    "price_fmt": "N/A",
                    "market_cap": market_cap,
                    "market_cap_fmt": _format_market_cap(market_cap, "USD"),
                    "change_pct": None,
                    "change_pct_fmt": "N/A",
                    "currency": "USD",
                }
            )
    return rows


def fetch_sp500_rankings(top_n: int = 100) -> pd.DataFrame:
    errors: list[str] = []
    for loader in (_fetch_sp500_from_stockanalysis, _fetch_sp500_from_constituents):
        try:
            rows = loader()
            if rows:
                return _rows_to_dataframe(rows, top_n)
        except Exception as exc:
            errors.append(str(exc))
    detail = errors[-1] if errors else "알 수 없는 오류"
    raise ValueError(f"S&P 500 시가총액 데이터를 가져오지 못했습니다. ({detail})")


def _load_kospi_listing() -> pd.DataFrame:
    errors: list[str] = []
    for offset in range(14):
        date_str = (datetime.now() - timedelta(days=offset)).strftime("%Y-%m-%d")
        url = KRX_CACHE_URL.format(date=date_str)
        try:
            response = requests.get(url, headers=_HEADERS, timeout=25)
            if response.status_code != 200:
                continue
            text = response.text.lstrip("\ufeff")
            if "Code" not in text.splitlines()[0]:
                continue
            df = pd.read_csv(
                StringIO(text),
                dtype={"Code": str, "MarketId": str},
            )
            kospi = df[df["MarketId"] == "STK"].copy()
            if not kospi.empty:
                return kospi
        except Exception as exc:
            errors.append(f"{date_str}: {exc}")

    try:
        import FinanceDataReader as fdr

        df = fdr.StockListing("KOSPI")
        if not df.empty:
            return df
    except Exception as exc:
        errors.append(f"FinanceDataReader: {exc}")

    detail = errors[-1] if errors else "캐시 파일 없음"
    raise ValueError(f"KOSPI 종목 데이터를 가져오지 못했습니다. ({detail})")


def fetch_kospi_rankings(top_n: int = 100) -> pd.DataFrame:
    listing = _load_kospi_listing()
    listing = listing.sort_values("Marcap", ascending=False)

    rows: list[dict] = []
    for _, item in listing.iterrows():
        code = str(item["Code"]).zfill(6)
        price = _parse_price(item.get("Close"))
        market_cap = item.get("Marcap")
        if market_cap is None or pd.isna(market_cap):
            continue
        market_cap = float(market_cap)
        if price is None:
            continue

        change_pct = _parse_change_pct(item.get("ChagesRatio"))
        rows.append(
            {
                "ticker": f"{code}.KS",
                "name": str(item["Name"]).strip(),
                "price": price,
                "price_fmt": _format_price(price, "KRW"),
                "market_cap": market_cap,
                "market_cap_fmt": _format_market_cap(market_cap, "KRW"),
                "change_pct": change_pct,
                "change_pct_fmt": (
                    f"{change_pct:+.2f}%" if change_pct is not None else "N/A"
                ),
                "currency": "KRW",
            }
        )

    return _rows_to_dataframe(rows, top_n)


def fetch_market_cap_rankings(region: MarketRegion, top_n: int = 100) -> pd.DataFrame:
    if region == "us":
        return fetch_sp500_rankings(top_n)
    return fetch_kospi_rankings(top_n)


def style_rankings_table(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    display = df[
        ["rank", "name", "price_fmt", "market_cap_fmt", "change_pct_fmt", "ticker"]
    ].rename(
        columns={
            "rank": "순위",
            "name": "기업명",
            "price_fmt": "현재주가",
            "market_cap_fmt": "시가총액",
            "change_pct_fmt": "등락률",
            "ticker": "티커",
        }
    )

    def _color_change(row: pd.Series) -> list[str]:
        styles = [""] * len(row)
        idx = row.index.get_loc("등락률")
        raw = df.loc[row.name, "change_pct"] if row.name in df.index else None
        if raw is not None and raw > 0:
            styles[idx] = "color: #16a34a; font-weight: 600"
        elif raw is not None and raw < 0:
            styles[idx] = "color: #dc2626; font-weight: 600"
        return styles

    return display.style.apply(_color_change, axis=1)
