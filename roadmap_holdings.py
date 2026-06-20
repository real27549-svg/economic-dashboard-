"""종목별 보유 주식 평가·집계 (yfinance)."""

from __future__ import annotations

import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import yfinance as yf
from yfinance.exceptions import YFRateLimitError

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

QUOTE_CACHE_TTL_SEC = 600 if os.environ.get("STREAMLIT_RUNTIME_ENV") == "cloud" else 120
_MAX_QUOTE_RETRIES = 3
_RETRY_BACKOFF_SEC = (0.5, 1.5, 3.0)
_RATE_LIMIT_WARNING = (
    "Yahoo Finance 요청이 일시적으로 제한되었습니다. "
    "종목 추가·저장은 가능하며, 잠시 후 **현재가 반영**으로 다시 시도하세요."
)
_usdkrw_cache: tuple[float, float] | None = None
_quote_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_rate_limit_warnings: list[str] = []


def clear_quote_cache() -> None:
    """현재가 강제 갱신 시 호출."""
    global _usdkrw_cache
    _usdkrw_cache = None
    _quote_cache.clear()


def pop_rate_limit_warnings() -> list[str]:
    """UI에 표시할 rate limit 경고를 꺼내고 비웁니다."""
    global _rate_limit_warnings
    warnings = _rate_limit_warnings[:]
    _rate_limit_warnings.clear()
    return warnings


def _note_rate_limit(symbol: str) -> None:
    global _rate_limit_warnings
    if _RATE_LIMIT_WARNING not in _rate_limit_warnings:
        _rate_limit_warnings.append(_RATE_LIMIT_WARNING)


def _is_fetch_error(exc: BaseException) -> bool:
    if isinstance(exc, (YFRateLimitError, ConnectionError, TimeoutError, OSError)):
        return True
    msg = str(exc).lower()
    return "rate limit" in msg or "too many requests" in msg or "429" in msg


def _max_quote_workers(count: int) -> int:
    if os.environ.get("STREAMLIT_RUNTIME_ENV") == "cloud":
        return min(2, count)
    return min(8, count)


def is_domestic_ticker(ticker: str) -> bool:
    return ticker.upper().endswith(".KS") or ticker.upper().endswith(".KQ")


def _cache_get(ticker: str, *, allow_stale: bool = False) -> dict[str, Any] | None:
    entry = _quote_cache.get(ticker.upper())
    if not entry:
        return None
    ts, data = entry
    age = time.time() - ts
    if age <= QUOTE_CACHE_TTL_SEC:
        return data
    if allow_stale:
        return {**data, "stale": True}
    return None


def _cache_set(ticker: str, data: dict[str, Any]) -> None:
    _quote_cache[ticker.upper()] = (time.time(), data)


def fetch_usdkrw() -> float:
    global _usdkrw_cache
    now = time.time()
    if _usdkrw_cache and now - _usdkrw_cache[0] <= QUOTE_CACHE_TTL_SEC:
        return _usdkrw_cache[1]

    stale_rate = _usdkrw_cache[1] if _usdkrw_cache else None
    rate_limit_hit = False
    for attempt in range(_MAX_QUOTE_RETRIES):
        rate_limit_hit = False
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
                except Exception as exc:
                    if _is_fetch_error(exc):
                        rate_limit_hit = True
                        break
                hist = ticker.history(period="5d")
                if not hist.empty:
                    rate = float(hist["Close"].iloc[-1])
                    _usdkrw_cache = (now, rate)
                    return rate
            except Exception as exc:
                if _is_fetch_error(exc):
                    rate_limit_hit = True
                    break
        if rate_limit_hit and attempt < _MAX_QUOTE_RETRIES - 1:
            time.sleep(_RETRY_BACKOFF_SEC[attempt])
            continue
        break

    if stale_rate is not None:
        _note_rate_limit("USDKRW")
        return stale_rate
    if rate_limit_hit:
        _note_rate_limit("USDKRW")
    raise ValueError("USD/KRW 환율을 가져오지 못했습니다.")


def _partial_quote(
    symbol: str,
    price: float,
    *,
    rate_limited: bool = False,
    name: str | None = None,
) -> dict[str, Any]:
    currency = "KRW" if is_domestic_ticker(symbol) else "USD"
    return {
        "ticker": symbol,
        "name": name or symbol,
        "currency": currency,
        "price": float(price),
        "rate_limited": rate_limited,
    }


def _fetch_quote_once(symbol: str) -> dict[str, Any]:
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

    return {
        "ticker": symbol,
        "name": name or symbol,
        "currency": currency,
        "price": float(price),
    }


def fetch_quote(
    ticker: str,
    *,
    fallback_price: float | None = None,
    fallback_name: str | None = None,
) -> dict[str, Any]:
    symbol = ticker.upper()
    cached = _cache_get(symbol)
    if cached:
        return cached

    last_exc: BaseException | None = None
    for attempt in range(_MAX_QUOTE_RETRIES):
        try:
            result = _fetch_quote_once(symbol)
            _cache_set(symbol, result)
            return result
        except Exception as exc:
            last_exc = exc
            if _is_fetch_error(exc) and attempt < _MAX_QUOTE_RETRIES - 1:
                time.sleep(_RETRY_BACKOFF_SEC[attempt])
                continue
            break

    stale = _cache_get(symbol, allow_stale=True)
    if stale:
        _note_rate_limit(symbol)
        return stale

    if last_exc and _is_fetch_error(last_exc):
        _note_rate_limit(symbol)
        price = float(fallback_price) if fallback_price and fallback_price > 0 else 0.0
        name = fallback_name or symbol
        return _partial_quote(symbol, price, rate_limited=True, name=name)

    if last_exc:
        raise ValueError(f"현재가를 가져오지 못했습니다: {symbol}") from last_exc
    raise ValueError(f"현재가를 가져오지 못했습니다: {symbol}")


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
        workers = _max_quote_workers(len(missing))
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
        "current_price": price if price > 0 else None,
        "currency": quote["currency"],
        "value_man": _to_man(value_krw),
        "return_pct": return_pct,
        "quote_rate_limited": quote.get("rate_limited", False),
        "quote_stale": quote.get("stale", False),
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
    quote = fetch_quote(ticker, fallback_name=matched or text)
    market = "domestic" if is_domestic_ticker(ticker) else "foreign"
    name = quote["name"]
    if quote.get("rate_limited") and name == ticker.upper():
        name = matched or text
    return {
        **holding,
        "ticker": ticker,
        "name": name,
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
    quote = fetch_quote(
        ticker,
        fallback_price=avg_price,
        fallback_name=matched or query.strip(),
    )
    market = "domestic" if is_domestic_ticker(ticker) else "foreign"
    name = quote["name"]
    if quote.get("rate_limited") and name == ticker.upper():
        name = matched or query.strip()
    return {
        "id": str(uuid.uuid4()),
        "ticker": ticker,
        "name": name,
        "query": matched or query.strip(),
        "quantity": float(quantity),
        "avg_price": float(avg_price),
        "market": market,
        "account_type": account_type,
    }
