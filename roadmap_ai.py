"""Claude 종합 재테크 로드맵 생성."""

from __future__ import annotations

import json
import re

from ai_outlook import DEFAULT_MODEL, create_anthropic_client
from financial_roadmap import (
    ALLOCATION_LABELS,
    ROADMAP_HORIZONS,
    _format_macro_block,
    _format_won,
)


def _format_history_lines(history: list[dict]) -> str:
    if not history:
        return "  - (월별 기록 없음)"
    return "\n".join(
        f"  - {h['year_month']}: 순자산 {_format_won(h['net_assets_man'])}"
        for h in history
    )


def _format_events_lines(events: list[dict]) -> str:
    if not events:
        return "  - (변동 이벤트 없음)"
    lines = []
    for ev in events[:15]:
        et = ev.get("event_type", "")
        data = ev.get("data") or {}
        note = data.get("note") or data.get("description") or str(data)
        recorded = (ev.get("recorded_at") or "")[:10]
        lines.append(f"  - [{recorded}] {et}: {note}")
    return "\n".join(lines)


def _build_comprehensive_prompt(context: dict, macro: dict) -> str:
    fixed = context.get("fixed") or {}
    monthly = context.get("monthly") or {}
    annual = context.get("annual") or {}
    metrics = context.get("metrics") or {}
    tax_room = context.get("tax_room") or {}
    pension = context.get("pension_estimate") or {}
    home = context.get("home_timeline") or {}
    savings_cmp = context.get("savings_comparison") or {}
    macro_text = _format_macro_block(macro)

    goals = ", ".join(fixed.get("goals") or fixed.get("goal") or ["자산증식"])
    if isinstance(fixed.get("goals"), list):
        goals = ", ".join(fixed["goals"])

    return f"""당신은 한국 거주자를 위한 재테크·세금·보험·노후 설계 전문 플래너입니다.
고정 프로필, 월별·연간 재무 데이터, 변동 이력, 거시경제를 반영해 종합 로드맵을 작성하세요.

## 고정 정보
- 나이: {fixed.get('age', '미입력')}세 · 생년월일: {fixed.get('birth_date', '미입력')}
- 성별: {fixed.get('gender', '미입력')} · 결혼: {fixed.get('marital_status', '미입력')} · 자녀: {fixed.get('num_children', 0)}명
- 직업: {fixed.get('job_type', '미입력')} · 학력: {fixed.get('education', '미입력')}
- 건강보험: {fixed.get('health_insurance', '미입력')} · 주택: {fixed.get('housing_ownership', '미입력')} · 거주: {fixed.get('residence_type', '미입력')}
- 퇴직연금: {fixed.get('retirement_pension_type', '미입력')} · 청약가점: {fixed.get('subscription_points', '미입력')}
- 신용점수(대략): {fixed.get('credit_score', '미입력')} · 은퇴 희망: {fixed.get('retirement_age', '미입력')}세
- 투자 성향: {fixed.get('risk_profile', '미입력')} · 목표: {goals}
- 부양가족: {fixed.get('dependents', 0)}명 · 장애/경로우대: {fixed.get('special_benefit', '아니오')}
- 결혼 예정: {fixed.get('marriage_planned', '아니오')} {fixed.get('marriage_planned_when', '')}
- 출산 계획: {fixed.get('birth_planned', '미입력')}
- 내집마련: {fixed.get('home_target_when', '')} / {_format_won(float(fixed.get('home_target_amount_man', 0) or 0))} / {fixed.get('home_target_region', '')}

## 이번 달 재무 (만원)
- 총 수입: {metrics.get('total_income_fmt', 'N/A')} · 총 지출: {metrics.get('total_expense_fmt', 'N/A')}
- 월 저축 가능액: {metrics.get('monthly_savings_fmt', 'N/A')} · 저축률: {metrics.get('savings_rate_fmt', 'N/A')}
- 적정 저축률(성향 기준): {savings_cmp.get('recommended_pct', 20)}% (현재와 비교 분석)
- 순자산: {metrics.get('net_assets_fmt', 'N/A')} (자산 {metrics.get('total_assets_fmt')} − 부채 {metrics.get('total_debt_fmt')})
- 비상금: {metrics.get('liquid_reserve_fmt', 'N/A')} — {metrics.get('emergency_fund_status', '')}

## 연간 정보 (올해, 만원)
- IRP 납입: {_format_won(float(annual.get('irp_contribution', 0) or 0))} · 연금저축: {_format_won(float(annual.get('pension_savings', 0) or 0))}
- ISA: {_format_won(float(annual.get('isa_contribution', 0) or 0))} · 금융소득: {tax_room.get('financial_income_fmt', 'N/A')}
- 절세 잔여 한도 — 연금/IRP: {tax_room.get('combined_pension_room_fmt', 'N/A')}, ISA: {tax_room.get('isa_room_fmt', 'N/A')}

## 월별 순자산 이력
{_format_history_lines(context.get('monthly_history') or [])}

## 변동 이벤트 이력
{_format_events_lines(context.get('variable_events') or [])}

## 시스템 간이 추정 (참고)
- 노후 월수령(추정): 국민연금 {pension.get('national_fmt')} + 연금저축 {pension.get('personal_fmt')} + IRP {pension.get('irp_fmt')} = {pension.get('total_fmt')}
- 내집마련 달성: {home.get('status', '')} — {home.get('detail', '')}

## 거시·시장 환경
{macro_text}

## 작성 지침
- 순자산·저축률·비상금(3~6개월)을 구체적으로 평가하세요.
- IRP/연금저축/ISA 절세 한도 대비 납입 현황과 추가 납입 여력을 tax_deduction_analysis에 작성하세요.
- 금융소득 2천만원 종합과세 임박 시 financial_income_tax_warning에 경고하세요.
- 종합소득세·건강보험료 절감, 무주택 청약/대출 혜택, 신용점수 관리, 생애주기별 보험 리모델링을 포함하세요.
- 1/3/5/10년 plans: target_asset_man(만원), allocation(합100), actions, risks.
- savings_simulation_note: 비관/중립/낙관 시나리오 해석 2~3문장.
- 단정적 수익 보장·특정 종목 매수 권유 금지. 한국어.

반드시 아래 JSON만 출력:
{{
  "summary": "전체 요약 3~4문장",
  "macro_note": "거시환경 영향 2~3문장",
  "savings_rate_note": "저축률 vs 적정 비교",
  "emergency_fund_note": "비상금 평가",
  "tax_deduction_analysis": "IRP/연금저축/ISA 절세 가능 금액 및 활용",
  "financial_income_tax_warning": "금융소득종합과세 주의 (없으면 해당 없음)",
  "comprehensive_income_tax_strategy": "종합소득세 절세 전략",
  "pension_monthly_estimate": {{"national": "...", "personal": "...", "irp": "...", "total": "...", "note": "..."}},
  "home_purchase_timeline": "내집마련 달성 시기 및 전략",
  "homeless_benefits": "무주택자 혜택 (청약/대출)",
  "credit_score_guide": "신용점수 관리",
  "health_insurance_savings": "건강보험료 절감",
  "insurance_remodeling": "생애주기별 보험 리모델링",
  "savings_simulation_note": "저축 시뮬레이션 해석",
  "tax_strategy": ["절세 팁1", "절세 팁2"],
  "global_risks": ["리스크1", "리스크2"],
  "plans": {{
    "1y": {{"headline": "...", "target_asset_man": 0, "target_asset_fmt": "...", "allocation": {{"cash": 25, "stocks": 35, "bonds": 25, "real_estate": 15}}, "actions": ["..."], "risks": ["..."]}},
    "3y": {{ ... }},
    "5y": {{ ... }},
    "10y": {{ ... }}
  }}
}}"""


def _parse_comprehensive_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    result = json.loads(cleaned)
    if "plans" not in result:
        raise ValueError("AI 응답에 plans 항목이 없습니다.")
    for horizon in ROADMAP_HORIZONS:
        plan = result["plans"].get(horizon)
        if not plan:
            raise ValueError(f"AI 응답에 {horizon} 플랜이 없습니다.")
        alloc = plan.get("allocation") or {}
        if abs(sum(float(alloc.get(k, 0)) for k in ALLOCATION_LABELS) - 100) > 5:
            for key in ALLOCATION_LABELS:
                alloc.setdefault(key, 0)
            plan["allocation"] = alloc
    return result


def generate_comprehensive_roadmap(context: dict, macro: dict) -> dict:
    client = create_anthropic_client()
    prompt = _build_comprehensive_prompt(context, macro)
    message = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_comprehensive_response(message.content[0].text)
