"""yfinance 기반 종목 검색."""

import re
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

# 한글/영문 별칭 → yfinance 티커
NAME_TO_TICKER: dict[str, str] = {
    # 한국 — 대형주
    "삼성전자": "005930.KS",
    "삼성": "005930.KS",
    "SK하이닉스": "000660.KS",
    "하이닉스": "000660.KS",
    "LG에너지솔루션": "373220.KS",
    "LG에너지": "373220.KS",
    "에너지솔루션": "373220.KS",
    "NAVER": "035420.KS",
    "네이버": "035420.KS",
    "카카오": "035720.KS",
    "현대차": "005380.KS",
    "현대자동차": "005380.KS",
    "기아": "000270.KS",
    "기아차": "000270.KS",
    "셀트리온": "068270.KS",
    "삼성바이오로직스": "207940.KS",
    "삼바": "207940.KS",
    "POSCO홀딩스": "005490.KS",
    "포스코": "005490.KS",
    "POSCO": "005490.KS",
    "KB금융": "105560.KS",
    "신한지주": "055550.KS",
    "하나금융": "086790.KS",
    "LG화학": "051910.KS",
    "삼성SDI": "006400.KS",
    "현대모비스": "012330.KS",
    "SK이노베이션": "096770.KS",
    "SK텔레콤": "017670.KS",
    "KT": "030200.KS",
    "LG전자": "066570.KS",
    "삼성물산": "028260.KS",
    "HD현대중공업": "329180.KS",
    "현대중공업": "329180.KS",
    "두산에너빌리티": "034020.KS",
    "한화에어로스페이스": "012450.KS",
    "한화에어로": "012450.KS",
    "HMM": "011200.KS",
    "대한항공": "003490.KS",
    "카카오뱅크": "323410.KS",
    "크래프톤": "259960.KS",
    "펄어비스": "263750.KS",
    "에코프로": "086520.KQ",
    "에코프로비엠": "247540.KQ",
    "HLB": "028300.KQ",
    "알테오젠": "196170.KQ",
    "리노공업": "058470.KQ",
    # 미국 — 빅테크·주요 종목
    "애플": "AAPL",
    "Apple": "AAPL",
    "마이크로소프트": "MSFT",
    "MSFT": "MSFT",
    "구글": "GOOGL",
    "알파벳": "GOOGL",
    "Google": "GOOGL",
    "아마존": "AMZN",
    "Amazon": "AMZN",
    "엔비디아": "NVDA",
    "NVIDIA": "NVDA",
    "테슬라": "TSLA",
    "Tesla": "TSLA",
    "메타": "META",
    "Meta": "META",
    "페이스북": "META",
    "넷플릭스": "NFLX",
    "Netflix": "NFLX",
    "코스트코": "COST",
    "월마트": "WMT",
    "Walmart": "WMT",
    "존슨앤존슨": "JNJ",
    "J&J": "JNJ",
    "버크셔": "BRK-B",
    "버크셔해서웨이": "BRK-B",
    "JP모건": "JPM",
    "모건": "JPM",
    "뱅크오브아메리카": "BAC",
    "BOA": "BAC",
    "비자": "V",
    "Visa": "V",
    "마스터카드": "MA",
    "Mastercard": "MA",
    "코카콜라": "KO",
    "Coca-Cola": "KO",
    "펩시": "PEP",
    "Pepsi": "PEP",
    "디즈니": "DIS",
    "Disney": "DIS",
    "인텔": "INTC",
    "Intel": "INTC",
    "AMD": "AMD",
    "퀄컴": "QCOM",
    "Qualcomm": "QCOM",
    "IBM": "IBM",
    "오라클": "ORCL",
    "Oracle": "ORCL",
    "세일즈포스": "CRM",
    "Salesforce": "CRM",
    "어도비": "ADBE",
    "Adobe": "ADBE",
    "페이팔": "PYPL",
    "PayPal": "PYPL",
    "우버": "UBER",
    "Uber": "UBER",
    "에어비앤비": "ABNB",
    "Airbnb": "ABNB",
    "스타벅스": "SBUX",
    "Starbucks": "SBUX",
    "나이키": "NKE",
    "Nike": "NKE",
    "보잉": "BA",
    "Boeing": "BA",
    "쉐vron": "CVX",
    "셰브론": "CVX",
    "Chevron": "CVX",
    "엑슨모빌": "XOM",
    "Exxon": "XOM",
    "화이자": "PFE",
    "Pfizer": "PFE",
    "모더나": "MRNA",
    "Moderna": "MRNA",
    "코인베이스": "COIN",
    "Coinbase": "COIN",
    "팔란티어": "PLTR",
    "Palantir": "PLTR",
    "스노우플레이크": "SNOW",
    "Snowflake": "SNOW",
    # 미국 — 주요 ETF
    "S&P500": "SPY",
    "S&P 500": "SPY",
    "에스앤피500": "SPY",
    "나스닥100": "QQQ",
    "나스닥": "QQQ",
    "NASDAQ100": "QQQ",
    "VOO": "VOO",
    "VTI": "VTI",
    "IVV": "IVV",
    "DIA": "DIA",
    "다우": "DIA",
    "다우존스": "DIA",
    "ARKK": "ARKK",
    "SOXX": "SOXX",
    "XLK": "XLK",
    "XLF": "XLF",
    "XLE": "XLE",
    "GLD": "GLD",
    "SLV": "SLV",
    "TLT": "TLT",
    "IWM": "IWM",
    "EEM": "EEM",
    "VEA": "VEA",
    "VWO": "VWO",
    # 한국 — 주요 ETF (KODEX / TIGER / RISE / SOL / ACE 등)
    "KODEX 200": "069500.KS",
    "KODEX200": "069500.KS",
    "코덱스200": "069500.KS",
    "코덱스 200": "069500.KS",
    "KODEX 코스닥150": "229200.KS",
    "KODEX 코스피": "069500.KS",
    "KODEX S&P500": "379800.KS",
    "KODEX 미국S&P500": "379800.KS",
    "KODEX S&P 500": "379800.KS",
    "KODEX 나스닥100": "379810.KS",
    "KODEX 레버리지": "122630.KS",
    "KODEX 200선물인버스2X": "252670.KS",
    "TIGER 200": "102110.KS",
    "TIGER S&P500": "360750.KS",
    "TIGER S&P 500": "360750.KS",
    "TIGER 미국S&P500": "360750.KS",
    "TIGER 나스닥100": "133690.KS",
    "TIGER NASDAQ100": "133690.KS",
    "TIGER 미국나스닥100": "133690.KS",
    "TIGER 차이나전기차": "371460.KS",
    "TIGER 미국테크TOP10": "381170.KS",
    "RISE 200": "148020.KS",
    "RISE S&P500": "379780.KS",
    "SOL 200": "152100.KS",
    "SOL 미국S&P500": "433330.KS",
    "ACE 200": "105190.KS",
    "ACE S&P500": "453660.KS",
    "HANARO 200": "091160.KS",
    "PLUS 200": "152100.KS",
    "KBSTAR 200": "069660.KS",
    "ARIRANG 200": "152100.KS",
    "069500": "069500.KS",
    "360750": "360750.KS",
    "133690": "133690.KS",
    "379800": "379800.KS",
    "229200": "229200.KS",
}

_TICKER_LOOKUP: dict[str, str] = {}
for _name, _ticker in NAME_TO_TICKER.items():
    _TICKER_LOOKUP[_name] = _ticker
    _TICKER_LOOKUP[_name.replace(" ", "")] = _ticker
    if _name.isascii():
        _TICKER_LOOKUP[_name.lower()] = _ticker
        _TICKER_LOOKUP[_name.upper()] = _ticker

_TICKER_LIKE = re.compile(
    r"^(\^)?[\dA-Za-z]+([.-][A-Za-z0-9]+)?(\.(KS|KQ|US|NY|NASDAQ|L|TO|AX)?)?$"
)
_KR_STOCK_CODE = re.compile(r"^(\d{6})(\.(KS|KQ))?$")


def _normalize_query(text: str) -> str:
    return text.strip().replace(" ", "").lower()


def _pick_best_search_quote(query: str, quotes: list[dict]) -> dict | None:
    if not quotes:
        return None
    raw = query.strip()
    compact = _normalize_query(raw)
    for quote in quotes:
        for field in ("shortname", "longname", "symbol"):
            value = quote.get(field) or ""
            if _normalize_query(str(value)) == compact:
                return quote
    for quote in quotes:
        shortname = _normalize_query(quote.get("shortname") or "")
        if compact in shortname or shortname in compact:
            return quote
    etf_hints = ("etf", "kodex", "tiger", "rise", "sol", "ace", "hanaro", "plus", "kosef", "kbstar")
    if any(h in compact for h in etf_hints):
        for quote in quotes:
            if (quote.get("quoteType") or "").upper() == "ETF":
                return quote
    return quotes[0]


def _search_yfinance_ticker(query: str) -> tuple[str, str | None]:
    search = yf.Search(query, max_results=12)
    quotes = search.quotes or []
    picked = _pick_best_search_quote(query, quotes)
    if not picked or not picked.get("symbol"):
        raise ValueError(f"「{query}」에 해당하는 종목/ETF를 찾을 수 없습니다.")
    symbol = str(picked["symbol"])
    label = picked.get("shortname") or picked.get("longname") or query.strip()
    return symbol, str(label)


def _resolve_korean_code(raw: str) -> str | None:
    compact = raw.replace(" ", "")
    match = _KR_STOCK_CODE.match(compact)
    if not match:
        return None
    code, suffix = match.group(1), match.group(3)
    return f"{code}.{suffix}" if suffix else f"{code}.KS"


def resolve_ticker(query: str) -> tuple[str, str | None]:
    """
    검색어를 yfinance 티커로 변환합니다.
    Returns: (ticker, 매칭된 한글/별칭 또는 None)
    """
    raw = query.strip()
    if not raw:
        raise ValueError("검색어를 입력해 주세요.")

    compact = raw.replace(" ", "")

    for key in (raw, compact):
        if key in _TICKER_LOOKUP:
            return _TICKER_LOOKUP[key], key

    if raw.isascii():
        for key in (raw.lower(), raw.upper()):
            if key in _TICKER_LOOKUP:
                return _TICKER_LOOKUP[key], raw

    kr_ticker = _resolve_korean_code(raw)
    if kr_ticker:
        return kr_ticker, raw

    if _TICKER_LIKE.match(raw):
        return raw.upper(), None

    if compact.isascii() and 1 <= len(compact) <= 6:
        return compact.upper(), None

    try:
        return _search_yfinance_ticker(raw)
    except Exception:
        pass

    raise ValueError(
        f"「{raw}」에 해당하는 종목을 찾을 수 없습니다. "
        "티커(AAPL, 069500.KS), ETF명(KODEX 200, SPY) 또는 한글 회사명을 입력해 주세요."
    )


def _format_price(value: float | None, currency: str = "USD") -> str:
    if value is None:
        return "N/A"
    if currency == "KRW":
        return f"{value:,.0f}원"
    if currency == "USD":
        return f"${value:,.2f}"
    return f"{value:,.2f} {currency}"


def _format_market_cap(value: float | None, currency: str = "USD") -> str:
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


def _format_per(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


def _parse_news_item(item: dict) -> dict:
    content = item.get("content", item)
    provider = content.get("provider") or {}
    click_url = content.get("clickThroughUrl") or {}
    canonical = content.get("canonicalUrl") or {}
    return {
        "title": content.get("title") or "제목 없음",
        "url": click_url.get("url") or canonical.get("url") or "",
        "publisher": provider.get("displayName") or "",
        "published": content.get("pubDate") or content.get("displayTime") or "",
    }


def fetch_stock_profile(query: str) -> dict:
    symbol, matched_name = resolve_ticker(query)
    if not symbol:
        raise ValueError("티커 심볼을 입력해 주세요.")

    stock = yf.Ticker(symbol)
    info = stock.info or {}
    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        hist = stock.history(period="5d")
        if hist.empty:
            raise ValueError(f"종목을 찾을 수 없습니다: {symbol}")

    hist = stock.history(period="1y", auto_adjust=True)
    if hist.empty:
        raise ValueError(f"주가 데이터가 없습니다: {symbol}")

    currency = info.get("currency") or (
        "KRW" if symbol.upper().endswith((".KS", ".KQ")) else "USD"
    )
    quote_type = info.get("quoteType") or ""
    price = (
        info.get("regularMarketPrice")
        or info.get("currentPrice")
        or float(hist["Close"].iloc[-1])
    )
    high_52 = info.get("fiftyTwoWeekHigh")
    low_52 = info.get("fiftyTwoWeekLow")
    per = info.get("trailingPE") or info.get("forwardPE")
    market_cap = info.get("marketCap")

    news_raw = stock.news or []
    news = [_parse_news_item(item) for item in news_raw[:3]]

    chart_df = hist.reset_index()
    chart_df = chart_df.rename(columns={"Date": "date", "Close": "close"})
    chart_df["date"] = pd.to_datetime(chart_df["date"]).dt.tz_localize(None)
    chart_df = chart_df[["date", "close"]]

    return {
        "query": query.strip(),
        "matched_name": matched_name,
        "symbol": symbol,
        "name": info.get("longName") or info.get("shortName") or symbol,
        "quote_type": quote_type,
        "currency": currency,
        "price": float(price),
        "price_fmt": _format_price(price, currency),
        "high_52": high_52,
        "high_52_fmt": _format_price(high_52, currency),
        "low_52": low_52,
        "low_52_fmt": _format_price(low_52, currency),
        "per": per,
        "per_fmt": _format_per(per),
        "market_cap": market_cap,
        "market_cap_fmt": _format_market_cap(market_cap, currency),
        "news": news,
        "chart_df": chart_df,
        "as_of": datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M"),
    }
