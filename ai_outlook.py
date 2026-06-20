"""Claude API 기반 시장 전망 분석."""

import json
import os
import re
from typing import Literal

from anthropic import Anthropic

from env_config import get_anthropic_api_key, require_anthropic_api_key

MarketType = Literal["us", "kr"]

US_INDICATOR_KEYS = [
    "FEDFUNDS",
    "CPIAUCSL",
    "UNRATE",
    "PPIACO",
    "DGS10",
    "DGS2",
    "T10Y2Y",
    "PAYEMS",
    "DTWEXBGS",
    "VIXCLS",
    "NASDAQCOM",
    "GOLD",
    "DCOILWTICO",
]

KR_INDICATOR_KEYS = [
    "KOSPI",
    "DEXKOUS",
    "FEDFUNDS",
    "DGS10",
    "T10Y2Y",
    "DTWEXBGS",
    "VIXCLS",
    "NASDAQCOM",
    "DCOILWTICO",
    "CPIAUCSL",
]

STOCK_SIGNAL_MACRO_KEYS = [
    "FEDFUNDS",
    "DGS10",
    "DGS2",
    "T10Y2Y",
    "VIXCLS",
    "NASDAQCOM",
    "CPIAUCSL",
    "KOSPI",
    "DEXKOUS",
    "DTWEXBGS",
    "DCOILWTICO",
]

VALID_SIGNALS = {"매수 고려", "중립", "매도 고려"}

DEFAULT_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")


def get_api_key() -> str | None:
    return get_anthropic_api_key()


def create_anthropic_client() -> Anthropic:
    key = require_anthropic_api_key()
    return Anthropic(api_key=key)


def pick_indicators(snapshot: dict, keys: list[str]) -> dict:
    return {key: snapshot[key] for key in keys if key in snapshot}


def _build_prompt(market: MarketType, indicators: dict) -> str:
    market_name = "미국 주식시장(미장)" if market == "us" else "한국 주식시장(국장)"
    lines = [
        f"- {item['label']}: {item['value']} (기준일 {item['date']})"
        for item in indicators.values()
    ]
    indicator_text = "\n".join(lines)

    focus = (
        "미국 거시지표, 시장심리, 원자재 데이터를 종합해 S&P500·나스닥 중심으로 분석하세요."
        if market == "us"
        else "코스피·원달러 환율을 중심으로, 미국 금리·달러·유가 등 외부 변수의 영향도 함께 분석하세요."
    )

    return f"""당신은 초보 투자자도 이해할 수 있게 설명하는 시장 애널리스트입니다.

아래는 {market_name} 분석에 사용할 최신 경제 지표입니다:
{indicator_text}

{focus}

다음 3가지 항목을 한국어로 작성하세요. 각 항목은 2~4문장, 구체적이되 단정적 예측은 피하고 "가능성", "주의" 표현을 사용하세요.
투자 권유나 매수·매도 추천은 하지 마세요.

반드시 아래 JSON 형식만 출력하세요. 다른 텍스트는 포함하지 마세요.
{{
  "summary": "현재 시장 상황 요약",
  "outlook": "주식시장 전망",
  "caution": "주의해야 할 점"
}}"""


def _parse_json_response(text: str, required_keys: tuple[str, ...]) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    result = json.loads(cleaned)
    for key in required_keys:
        if key not in result or not str(result[key]).strip():
            raise ValueError(f"AI 응답에 '{key}' 항목이 없습니다.")
    return result


def _parse_response(text: str) -> dict:
    return _parse_json_response(text, ("summary", "outlook", "caution"))


def _parse_signal_response(text: str) -> dict:
    result = _parse_json_response(text, ("signal", "reason"))
    signal = str(result["signal"]).strip()
    if signal not in VALID_SIGNALS:
        raise ValueError(f"AI 신호 형식 오류: {signal}")
    return {"signal": signal, "reason": str(result["reason"]).strip()}


def _is_korean_stock(symbol: str, currency: str) -> bool:
    return symbol.endswith(".KS") or symbol.endswith(".KQ") or currency == "KRW"


def _build_stock_signal_prompt(stock: dict, indicators: dict) -> str:
    market = "한국 상장" if stock.get("is_korean") else "미국 상장"
    macro_lines = [
        f"- {item['label']}: {item['value']} (기준일 {item['date']})"
        for item in indicators.values()
    ]
    macro_text = "\n".join(macro_lines)
    range_text = stock.get("range_52w_text") or "N/A"

    return f"""당신은 초보 투자자를 위한 주식 분석가입니다.
개별 종목 밸류에이션과 거시 환경을 함께 보고, 참고용 매매 신호를 제시하세요.
단정적 투자 권유는 금지하고, 근거를 간단히 설명하세요.

## 종목 정보 ({market})
- 종목: {stock['name']} ({stock['symbol']})
- 현재가: {stock['price_fmt']}
- 52주 최고: {stock['high_52_fmt']}
- 52주 최저: {stock['low_52_fmt']}
- 52주 구간 위치: {range_text}
- PER: {stock['per_fmt']}
- 시가총액: {stock['market_cap_fmt']}

## 거시지표
{macro_text}

위 데이터를 종합해 아래 3가지 중 하나의 신호만 선택하세요:
- "매수 고려": 밸류에이션·추세·거시 환경이 비교적 우호적
- "중립": 긍정·부정 요인이 혼재하거나 방향성 불명확
- "매도 고려": 고평가·약세·거시 리스크 등 부정 요인 우세

reason은 2~3문장, 한국어, 초보자도 이해 가능하게 작성하세요.

반드시 아래 JSON만 출력하세요:
{{
  "signal": "매수 고려 또는 중립 또는 매도 고려",
  "reason": "신호 이유 설명"
}}"""


def build_stock_context(profile: dict) -> dict:
    price = profile.get("price")
    high = profile.get("high_52")
    low = profile.get("low_52")
    range_text = "N/A"
    if price is not None and high is not None and low is not None and high > low:
        pct = (price - low) / (high - low) * 100
        range_text = f"52주 저점 대비 +{pct:.0f}% (고점 대비 {(price - high) / high * 100:+.1f}%)"

    symbol = profile["symbol"]
    currency = profile.get("currency", "USD")
    return {
        "symbol": symbol,
        "name": profile["name"],
        "price_fmt": profile["price_fmt"],
        "high_52_fmt": profile["high_52_fmt"],
        "low_52_fmt": profile["low_52_fmt"],
        "per_fmt": profile["per_fmt"],
        "market_cap_fmt": profile["market_cap_fmt"],
        "range_52w_text": range_text,
        "is_korean": _is_korean_stock(symbol, currency),
    }


def analyze_stock_signal(stock: dict, snapshot: dict) -> dict:
    indicators = pick_indicators(snapshot, STOCK_SIGNAL_MACRO_KEYS)
    if not indicators:
        raise ValueError("거시지표 데이터가 없습니다.")

    client = create_anthropic_client()
    prompt = _build_stock_signal_prompt(stock, indicators)
    message = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_signal_response(message.content[0].text)


def analyze_market(market: MarketType, snapshot: dict) -> dict:
    keys = US_INDICATOR_KEYS if market == "us" else KR_INDICATOR_KEYS
    indicators = pick_indicators(snapshot, keys)
    if not indicators:
        raise ValueError("분석할 지표 데이터가 없습니다.")

    client = create_anthropic_client()
    prompt = _build_prompt(market, indicators)
    message = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text
    return _parse_response(text)
