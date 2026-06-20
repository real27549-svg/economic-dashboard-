"""종목별 보유 주식 평가·집계 (yfinance)."""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import yfinance as yf

from stock_search import resolve_ticker

HOLDING_KEYS = (
    "id",
    "ticker",
    "name",
    "query",
    "quantity",
    "avg_price",
    "market",
    "account_type",
)

QUOTE_CACHE_TTL_SEC = 120
_usdkrw_cache: tuple[float, float] | None = None
_quote_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_quote_cache() -> None:
    """현재가 강제 갱신 시 호출."""
    global _usdkrw_cache
    _usdkrw_cache = None
    _quote_cache.clear()


def is_domestic_ticker(ticker: str) -> bool:
    return ticker.upper().endswith(".KS") or ticker.upper().endswith(".KQ")


def _cache_get(ticker: str) -> dict[str, Any] | None:
    entry = _quote_cache.get(ticker.upper())
    if not entry:
        return None
    ts, data = entry
    if time.time() - ts > QUOTE_CACHE_TTL_SEC:
        return None
    return data


def _cache_set(ticker: str, data: dict[str, Any]) -> None:
    _quote_cache[ticker.upper()] = (time.time(), data)


def fetch_usdkrw() -> float:
    global _usdkrw_cache
    now = time.time()
    if _usdkrw_cache and now - _usdkrw_cache[0] <= QUOTE_CACHE_TTL_SEC:
        return _usdkrw_cache[1]

    for symbol in ("KRW=X", "USDKRW=X"):
        try:
            ticker = yf.Ticker(symbol)
            try:
                fast = ticker.fast_info
                price = fast.get("lastPrice") or fast.get("regularMarketPrice")
                if price:
                    rate = float(price)
                    _usdkrw_cache = (now, rate)
                    return rate
            except Exception:
                pass
            hist = ticker.history(period="5d")
            if not hist.empty:
                rate = float(hist["Close"].iloc[-1])
                _usdkrw_cache = (now, rate)
                return rate
        except Exception:
            continue
    raise ValueError("USD/KRW 환율을 가져오지 못했습니다.")


def fetch_quote(ticker: str) -> dict[str, Any]:
    symbol = ticker.upper()
    cached = _cache_get(symbol)
    if cached:
        return cached

    stock = yf.Ticker(symbol)
    currency = "KRW" if is_domestic_ticker(symbol) else "USD"
    name = symbol
    price: float | None = None

    try:
        fast = stock.fast_info
        price = fast.get("lastPrice") or fast.get("regularMarketPrice")
        currency = fast.get("currency") or currency
        name = fast.get("shortName") or fast.get("longName") or name
    except Exception:
        pass

    if price is None:
        hist = stock.history(period="5d", auto_adjust=True)
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])

    if price is None:
        info = stock.info or {}
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        currency = info.get("currency") or currency
        name = info.get("longName") or info.get("shortName") or name

    if price is None:
        raise ValueError(f"현재가를 가져오지 못했습니다: {symbol}")

    result = {
        "ticker": symbol,
        "name": name or symbol,
        "currency": currency,
        "price": float(price),
    }
    _cache_set(symbol, result)
    return result


def _fetch_quotes_parallel(tickers: list[str]) -> dict[str, dict[str, Any]]:
    unique = list(dict.fromkeys(t.upper() for t in tickers if t))
    if not unique:
        return {}

    quotes: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for symbol in unique:
        cached = _cache_get(symbol)
        if cached:
            quotes[symbol] = cached
        else:
            missing.append(symbol)

    if missing:
        workers = min(8, len(missing))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(fetch_quote, sym): sym for sym in missing}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    quotes[sym] = future.result()
                except Exception:
                    pass
    return quotes


def _to_man(value_krw: float) -> float:
    return round(value_krw / 10_000, 2)


def compute_holding_with_quote(
    holding: dict[str, Any],
    quote: dict[str, Any],
    usdkrw: float,
) -> dict[str, Any]:
    qty = float(holding.get("quantity") or 0)
    avg_price = float(holding.get("avg_price") or 0)
    price = quote["price"]
    market = holding.get("market") or (
        "domestic" if is_domestic_ticker(holding["ticker"]) else "foreign"
    )

    if market == "domestic":
        value_krw = price * qty
    else:
        value_krw = price * qty * usdkrw

    return_pct = None
    if avg_price > 0:
        return_pct = round((price - avg_price) / avg_price * 100, 2)

    return {
        **holding,
        "name": holding.get("name") or quote["name"],
        "market": market,
        "current_price": price,
        "currency": quote["currency"],
        "value_man": _to_man(value_krw),
        "return_pct": return_pct,
    }


def compute_holding(holding: dict[str, Any], usdkrw: float) -> dict[str, Any]:
    quote = fetch_quote(holding["ticker"])
    return compute_holding_with_quote(holding, quote, usdkrw)


def aggregate_holdings(
    holdings: list[dict[str, Any]],
    usdkrw: float | None = None,
) -> tuple[float, float, list[dict[str, Any]]]:
    if not holdings:
        return 0.0, 0.0, []

    if usdkrw is None:
        usdkrw = fetch_usdkrw()

    tickers = [h["ticker"] for h in holdings if h.get("ticker")]
    quotes = _fetch_quotes_parallel(tickers)

    domestic_man = 0.0
    foreign_man = 0.0
    computed: list[dict[str, Any]] = []

    for raw in holdings:
        ticker = (raw.get("ticker") or "").upper()
        quote = quotes.get(ticker)
        if not quote:
            try:
                item = compute_holding(raw, usdkrw)
            except Exception as exc:
                item = {
                    **raw,
                    "current_price": None,
                    "value_man": 0.0,
                    "return_pct": None,
                    "error": str(exc),
                }
        else:
            try:
                item = compute_holding_with_quote(raw, quote, usdkrw)
            except Exception as exc:
                item = {
                    **raw,
                    "current_price": None,
                    "value_man": 0.0,
                    "return_pct": None,
                    "error": str(exc),
                }
        computed.append(item)
        if item.get("market") == "domestic":
            domestic_man += float(item.get("value_man") or 0)
        else:
            foreign_man += float(item.get("value_man") or 0)

    return round(domestic_man, 2), round(foreign_man, 2), computed


def refresh_holding_identity(
    holding: dict[str, Any],
    name_or_query: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """종목명/티커 검색 후 심볼·상장 반영."""
    text = name_or_query.strip()
    if not text:
        raise ValueError("종목명 또는 티커를 입력하세요.")

    if not force:
        current_labels = {
            str(holding.get("name") or "").strip(),
            str(holding.get("query") or "").strip(),
            str(holding.get("ticker") or "").strip(),
        }
        current_labels.discard("")
        if text in current_labels:
            return holding

    ticker, matched = resolve_ticker(text)
    quote = fetch_quote(ticker)
    market = "domestic" if is_domestic_ticker(ticker) else "foreign"
    return {
        **holding,
        "ticker": ticker,
        "name": quote["name"],
        "query": matched or text,
        "market": market,
    }


def strip_holding_for_save(holding: dict[str, Any]) -> dict[str, Any]:
    result = {key: holding[key] for key in HOLDING_KEYS if key in holding}
    result.setdefault("account_type", "direct")
    return result


def new_holding(
    query: str,
    quantity: float,
    avg_price: float,
    account_type: str = "direct",
) -> dict[str, Any]:
    from roadmap_fields import STOCK_ACCOUNT_TYPES

    if account_type not in STOCK_ACCOUNT_TYPES:
        account_type = "direct"
    ticker, matched = resolve_ticker(query)
    quote = fetch_quote(ticker)
    market = "domestic" if is_domestic_ticker(ticker) else "foreign"
    return {
        "id": str(uuid.uuid4()),
        "ticker": ticker,
        "name": quote["name"],
        "query": matched or query.strip(),
        "quantity": float(quantity),
        "avg_price": float(avg_price),
        "market": market,
        "account_type": account_type,
    }
