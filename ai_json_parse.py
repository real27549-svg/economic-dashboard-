"""Robust JSON extraction from Claude / LLM text responses."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json_text(text: str) -> str:
    """Strip markdown fences and surrounding prose from an AI response."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def repair_json_text(text: str) -> str:
    """Apply lightweight fixes for common AI JSON mistakes."""
    repaired = text
    repaired = re.sub(r"//[^\n]*", "", repaired)
    repaired = re.sub(r"/\*[\s\S]*?\*/", "", repaired)
    repaired = re.sub(r"\{\s*\.\.\.\s*\}", "{}", repaired)
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    repaired = re.sub(
        r"(?<![\w\"])'([^'\\]*(?:\\.[^'\\]*)*)'\s*:",
        lambda m: json.dumps(m.group(1), ensure_ascii=False) + ":",
        repaired,
    )
    repaired = re.sub(
        r":\s*'([^'\\]*(?:\\.[^'\\]*)*)'(\s*[,}\]])",
        lambda m: ": " + json.dumps(m.group(1), ensure_ascii=False) + m.group(2),
        repaired,
    )
    repaired = repaired.replace("True", "true").replace("False", "false").replace("None", "null")
    return repaired


def _json_candidates(text: str) -> list[str]:
    cleaned = extract_json_text(text)
    candidates: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        candidate = candidate.strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            candidates.append(candidate)

    add(cleaned)
    add(repair_json_text(cleaned))

    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end = cleaned.rfind(closer)
        if start >= 0 and end > start:
            sliced = cleaned[start : end + 1]
            add(sliced)
            add(repair_json_text(sliced))

    return candidates


def format_json_parse_error(exc: json.JSONDecodeError, raw_text: str) -> str:
    """Return a user-friendly Korean message for JSON parse failures."""
    snippet = ""
    lines = raw_text.splitlines()
    if lines:
        line_no = max(1, min(exc.lineno, len(lines)))
        snippet = lines[line_no - 1].strip()
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
    location = f"줄 {exc.lineno}, 열 {exc.colno}"
    detail = (
        "AI가 JSON 형식이 아닌 내용(예: `{ ... }` 생략, 따옴표 오류, trailing comma)을 "
        "포함해 응답했습니다."
    )
    if snippet:
        return f"AI 응답 JSON 파싱 실패 ({location}): {detail} 문제 구간: `{snippet}`"
    return f"AI 응답 JSON 파싱 실패 ({location}): {detail}"


def parse_ai_json(text: str) -> Any:
    """Parse JSON from an AI response, tolerating common formatting mistakes."""
    last_error: json.JSONDecodeError | None = None
    for candidate in _json_candidates(text):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc

    if last_error is not None:
        raise ValueError(format_json_parse_error(last_error, extract_json_text(text)))
    raise ValueError("AI 응답에서 JSON을 파싱하지 못했습니다.")


def parse_ai_json_object(text: str) -> dict[str, Any]:
    """Parse a JSON object from an AI response."""
    data = parse_ai_json(text)
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {"items": data}
    raise ValueError("AI 응답 JSON이 객체 형식이 아닙니다.")


if __name__ == "__main__":
    samples = [
        '```json\n{"summary": "ok", "plans": {"1y": {"headline": "a"}}}\n```',
        '{"summary": "ok", "plans": {"1y": {}, "3y": { ... }, "5y": {}, "10y": {},}}',
        "{'summary': 'ok', 'outlook': 'test', 'caution': 'none'}",
        'Here is the result:\n{"signal": "hold", "reason": "wait",}\nThanks.',
    ]
    for sample in samples:
        parsed = parse_ai_json(sample)
        assert isinstance(parsed, dict), sample
    print("ai_json_parse self-test passed")
