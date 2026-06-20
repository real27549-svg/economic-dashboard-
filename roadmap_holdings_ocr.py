"""증권 계좌 스크린샷 → 보유종목 자동 추출 (Claude Vision)."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from ai_outlook import DEFAULT_MODEL, create_anthropic_client
from stock_search import resolve_ticker

# roadmap_fields 순환 import 방지 — fallback 포함
_FALLBACK_ACCOUNT_TYPES: dict[str, str] = {
    "direct": "직접투자",
    "isa": "ISA",
    "personal_pension": "개인연금",
    "irp": "IRP",
}


def _account_types() -> dict[str, str]:
    try:
        from roadmap_fields import STOCK_ACCOUNT_TYPES

        return STOCK_ACCOUNT_TYPES
    except ImportError:
        return _FALLBACK_ACCOUNT_TYPES


def _valid_accounts() -> set[str]:
    return set(_account_types().keys())
_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


def _media_type_from_name(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    return _MEDIA_TYPES.get(ext, "image/png")


def _parse_json_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, list):
            return {"holdings": data}
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise ValueError("AI 응답에서 JSON을 파싱하지 못했습니다.")


def _normalize_account_type(raw: str | None, fallback: str) -> str:
    valid = _valid_accounts()
    if not raw:
        return fallback if fallback in valid else "direct"
    text = str(raw).strip().lower()
    mapping = {
        "isa": "isa",
        "irp": "irp",
        "direct": "direct",
        "직접": "direct",
        "직접투자": "direct",
        "personal_pension": "personal_pension",
        "pension": "personal_pension",
        "연금": "personal_pension",
        "개인연금": "personal_pension",
        "연금저축": "personal_pension",
        "퇴직연금": "personal_pension",
        "dc": "personal_pension",
    }
    if text in mapping:
        return mapping[text]
    for key, value in mapping.items():
        if key in text:
            return value
    return fallback if fallback in valid else "direct"


def _build_ocr_prompt(default_account: str) -> str:
    accounts = ", ".join(f"{k}={v}" for k, v in _account_types().items())
    return f"""이 이미지는 한국 증권사/은행 앱의 **주식 보유 계좌** 화면 스크린샷입니다.
화면에 보이는 **모든 보유 종목**을 추출하세요.

## 추출 항목
- name: 종목명 (한글/영문 그대로)
- ticker_hint: 티커·종목코드가 보이면 (예: 005930, AAPL). 없으면 null
- quantity: 보유 수량 (주/좌). 쉼표 제거한 숫자
- avg_price: 평균매입가·매입단가·평단 (숫자만)
  - 국내 상장(KRX): **원(KRW)** 단위 (예: 70000). '만원' 표기면 ×10000
  - 해외 상장: **USD** 단위 (예: 150.25)
- market_hint: "domestic"(국내) 또는 "foreign"(해외). 앱 표기·통화·티커로 판단
- account_type: 화면에 계좌명이 보이면 아래 중 하나, 없으면 null
  ({accounts})

## 기본 계좌 (화면에 없을 때): {default_account}

## 규칙
- ETF·리츠·펀드도 포함
- 현금·예수금·총평가금액만 있고 종목 목록이 없으면 holdings를 빈 배열
- 확실하지 않은 종목은 제외하지 말고 name만이라도 포함
- JSON만 출력 (설명 없음)

```json
{{
  "account_type": "isa",
  "holdings": [
    {{
      "name": "삼성전자",
      "ticker_hint": "005930",
      "quantity": 10,
      "avg_price": 72000,
      "market_hint": "domestic",
      "account_type": null
    }}
  ]
}}
```"""


def extract_holdings_from_image(
    image_bytes: bytes,
    filename: str = "screenshot.png",
    default_account: str = "direct",
) -> dict[str, Any]:
    """스크린샷에서 보유종목 raw 목록 추출."""
    if not image_bytes:
        raise ValueError("이미지 파일이 비어 있습니다.")

    client = create_anthropic_client()
    media_type = _media_type_from_name(filename)
    b64 = base64.standard_b64encode(image_bytes).decode("ascii")

    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": _build_ocr_prompt(default_account)},
                ],
            }
        ],
    )

    text_blocks = [block.text for block in response.content if hasattr(block, "text")]
    if not text_blocks:
        raise ValueError("AI가 응답을 반환하지 않았습니다.")

    parsed = _parse_json_payload("\n".join(text_blocks))
    screen_account = _normalize_account_type(parsed.get("account_type"), default_account)
    raw_holdings = parsed.get("holdings") or []
    if not isinstance(raw_holdings, list):
        raw_holdings = []

    return {
        "account_type": screen_account,
        "holdings": raw_holdings,
    }


def import_holdings_from_screenshot(
    image_bytes: bytes,
    filename: str = "screenshot.png",
    default_account: str = "direct",
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    스크린샷 → new_holding() 형식 목록 + 오류 메시지.
    Returns: (created_holdings, errors)
    """
    from roadmap_holdings import new_holding

    extracted = extract_holdings_from_image(image_bytes, filename, default_account)
    screen_account = extracted["account_type"]
    created: list[dict[str, Any]] = []
    errors: list[str] = []

    for idx, item in enumerate(extracted["holdings"], start=1):
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or item.get("ticker_hint") or "").strip()
        if not name:
            errors.append(f"{idx}번째: 종목명 없음")
            continue

        query = (item.get("ticker_hint") or name).strip()
        quantity = float(item.get("quantity") or 0)
        avg_price = float(item.get("avg_price") or 0)
        account = _normalize_account_type(item.get("account_type"), screen_account)

        if quantity <= 0:
            errors.append(f"「{name}」: 수량 0 — 건너뜀")
            continue

        try:
            holding = new_holding(query, quantity, avg_price, account)
            # OCR 종목명이 더 읽기 좋으면 유지
            ocr_name = (item.get("name") or "").strip()
            if ocr_name:
                holding["name"] = ocr_name
            created.append(holding)
        except Exception as exc:
            try:
                ticker, _ = resolve_ticker(name)
                holding = new_holding(ticker, quantity, avg_price, account)
                if name:
                    holding["name"] = name
                created.append(holding)
            except Exception:
                errors.append(f"「{name}」: {exc}")

    return created, errors


def import_holdings_from_screenshots(
    files: list[tuple[bytes, str]],
    default_account: str = "direct",
) -> tuple[list[dict[str, Any]], list[str]]:
    """여러 스크린샷을 순서대로 분석해 보유종목 목록을 합칩니다."""
    if not files:
        return [], []

    all_created: list[dict[str, Any]] = []
    all_errors: list[str] = []

    for index, (image_bytes, filename) in enumerate(files, start=1):
        label = filename or f"screenshot-{index}.png"
        try:
            created, errors = import_holdings_from_screenshot(
                image_bytes,
                label,
                default_account,
            )
            all_created.extend(created)
            for err in errors:
                all_errors.append(f"[{label}] {err}")
        except Exception as exc:
            all_errors.append(f"[{label}] 분석 실패: {exc}")

    return all_created, all_errors
