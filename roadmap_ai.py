"""Claude 종합 재테크 로드맵 생성 및 재무 상담 채팅."""

from __future__ import annotations

from typing import Any

from ai_json_parse import parse_ai_json_object
from ai_outlook import DEFAULT_MODEL, create_anthropic_client
from financial_roadmap import _format_macro_block, _format_won
from roadmap_debt import format_debt_block_for_ai

AI_SECTION_KEYS = (
    "section_1_diagnosis",
    "section_2_tax",
    "section_3_goals",
    "section_4_risks",
    "section_5_action_plan",
    "section_6_monthly_report",
)

CHAT_EXAMPLE_QUESTIONS = (
    "IRP·연금저축 추가납입으로 절세할 수 있는 금액과 시기를 알려주세요.",
    "올해 성과급을 어떻게 활용하면 좋을까요?",
    "지금 상황에서 전세와 매매 중 어떤 선택이 유리한가요?",
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


def _format_holdings_lines(holdings: list[dict]) -> str:
    if not holdings:
        return "  - (종목별 보유 없음)"
    lines = []
    for h in holdings[:30]:
        lines.append(
            f"  - {h.get('name', h.get('ticker', '?'))} ({h.get('ticker', '')}): "
            f"{h.get('quantity', 0)}주, 평단 {h.get('avg_price', 0)}, "
            f"평가 {h.get('market_value_man', h.get('valuation_man', 'N/A'))}만원, "
            f"{h.get('account_type', 'direct')}"
        )
    return "\n".join(lines)


def _format_allocation_lines(allocation: dict) -> str:
    items = allocation.get("items") or []
    if not items:
        return "  - (자산 배분 데이터 없음)"
    return "\n".join(
        f"  - {i['label']}: {_format_won(i['man'])} ({i['pct']:.1f}%)"
        for i in items
    )


def format_context_for_chat(context: dict, macro: dict) -> str:
    """채팅용 재무 데이터 텍스트."""
    fixed = context.get("fixed") or {}
    monthly = context.get("monthly") or {}
    annual = context.get("annual") or {}
    metrics = context.get("metrics") or {}
    tax_room = context.get("tax_room") or {}
    debt = context.get("debt_analysis") or {}
    peer = context.get("peer_comparison") or {}
    fire = context.get("fire_estimate") or {}
    perf = context.get("monthly_performance") or {}
    goals = fixed.get("goals") or fixed.get("goal") or ["자산증식"]
    if isinstance(goals, list):
        goals = ", ".join(goals)

    return f"""## 고정 프로필
- 나이 {fixed.get('age', '미입력')}세 · 직업 {fixed.get('job_type', '미입력')} · 성향 {fixed.get('risk_profile', '미입력')}
- 목표: {goals} · 은퇴 {fixed.get('retirement_age', '미입력')}세
- 주택: {fixed.get('housing_ownership', '미입력')} · 거주 {fixed.get('residence_type', '미입력')}
- 내집마련: {fixed.get('home_target_when', '')} / {_format_won(float(fixed.get('home_target_amount_man', 0) or 0))}

## 이번 달 재무 (만원)
- 수입 {metrics.get('total_income_fmt')} · 지출 {metrics.get('total_expense_fmt')}
- 저축 {metrics.get('monthly_savings_fmt')} · 저축률 {metrics.get('savings_rate_fmt')}
- 순자산 {metrics.get('net_assets_fmt')} · DSR {metrics.get('dsr_fmt')} · 부채/자산 {metrics.get('debt_to_asset_fmt')}
- 비상금 {metrics.get('liquid_reserve_fmt')} — {metrics.get('emergency_fund_status', '')}

## 또래·FIRE 참고
- 또래({peer.get('age_band', '')}) 중앙값 {peer.get('peer_median_fmt', 'N/A')} 대비 {peer.get('status', '')}
- FIRE 추정: {fire.get('status', '')} — {fire.get('detail', '')}

## 절세·연간
- IRP {annual.get('irp_contribution', 0)} · 연금저축 {annual.get('pension_savings', 0)} · ISA {annual.get('isa_contribution', 0)}만원
- 절세 잔여 — 연금/IRP {tax_room.get('combined_pension_room_fmt')} · ISA {tax_room.get('isa_room_fmt')}
- 금융소득 {tax_room.get('financial_income_fmt')}

## 부채
{format_debt_block_for_ai(debt) if debt else '  - 없음'}

## 자산 배분
{_format_allocation_lines(context.get('asset_allocation') or {})}

## 보유종목
{_format_holdings_lines(context.get('holdings') or [])}

## 월별 이력
{_format_history_lines(context.get('monthly_history') or [])}

## 지난달 대비
- 순자산 {perf.get('change_direction', '')} {perf.get('change_fmt', 'N/A')}

## 거시환경
{_format_macro_block(macro)}"""


def _build_comprehensive_prompt(context: dict, macro: dict) -> str:
    fixed = context.get("fixed") or {}
    monthly = context.get("monthly") or {}
    annual = context.get("annual") or {}
    metrics = context.get("metrics") or {}
    tax_room = context.get("tax_room") or {}
    pension = context.get("pension_estimate") or {}
    home = context.get("home_timeline") or {}
    savings_cmp = context.get("savings_comparison") or {}
    debt = context.get("debt_analysis") or {}
    peer = context.get("peer_comparison") or {}
    fire = context.get("fire_estimate") or {}
    perf = context.get("monthly_performance") or {}
    allocation = context.get("asset_allocation") or {}
    debt_text = format_debt_block_for_ai(debt) if debt else "  - (대출 상세 없음)"
    macro_text = _format_macro_block(macro)

    goals = fixed.get("goals") or fixed.get("goal") or ["자산증식"]
    if isinstance(fixed.get("goals"), list):
        goals = ", ".join(fixed["goals"])

    return f"""당신은 한국 거주자를 위한 재테크·세금·보험·노후 설계 전문 플래너입니다.
아래 데이터를 바탕으로 **6가지 분석 섹션**을 작성하세요.

## 고정 정보
- 나이: {fixed.get('age', '미입력')}세 · 성별: {fixed.get('gender', '미입력')} · 결혼: {fixed.get('marital_status', '미입력')} · 자녀: {fixed.get('num_children', 0)}명
- 직업: {fixed.get('job_type', '미입력')} · 건강보험: {fixed.get('health_insurance', '미입력')}
- 주택: {fixed.get('housing_ownership', '미입력')} · 거주: {fixed.get('residence_type', '미입력')}
- 투자 성향: {fixed.get('risk_profile', '미입력')} · 목표: {goals}
- 은퇴 희망: {fixed.get('retirement_age', '미입력')}세 · 내집마련: {fixed.get('home_target_when', '')} / {_format_won(float(fixed.get('home_target_amount_man', 0) or 0))}

## 이번 달 재무 (만원)
- 총 수입: {metrics.get('total_income_fmt')} · 총 지출: {metrics.get('total_expense_fmt')}
- 월 저축: {metrics.get('monthly_savings_fmt')} · 저축률: {metrics.get('savings_rate_fmt')} (적정 {savings_cmp.get('recommended_pct', 20)}%)
- 순자산: {metrics.get('net_assets_fmt')} · DSR: {metrics.get('dsr_fmt')} · 부채/자산: {metrics.get('debt_to_asset_fmt')}
- 비상금: {metrics.get('liquid_reserve_fmt')} — {metrics.get('emergency_fund_status', '')}

## 또래·FIRE (시스템 계산)
- 또래({peer.get('age_band', '')}) 순자산 중앙값 {peer.get('peer_median_fmt', 'N/A')} — 현재 {peer.get('status', '')}
- FIRE 추정: {fire.get('status', '')} ({fire.get('fire_target_fmt', '')}) — {fire.get('detail', '')}

## 자산 배분 (시스템 계산)
{_format_allocation_lines(allocation)}
- 최대 비중: {(allocation.get('largest') or {}).get('label', 'N/A')} {(allocation.get('largest') or {}).get('pct', 0):.1f}%

## 부채·대출
{debt_text}

## 연간·절세 (만원)
- IRP: {annual.get('irp_contribution', 0)} · 연금저축: {annual.get('pension_savings', 0)} · ISA: {annual.get('isa_contribution', 0)}
- 절세 잔여 — 연금/IRP: {tax_room.get('combined_pension_room_fmt')}, ISA: {tax_room.get('isa_room_fmt')}
- 금융소득: {tax_room.get('financial_income_fmt')}

## 보유종목
{_format_holdings_lines(context.get('holdings') or [])}

## 월별 순자산 이력
{_format_history_lines(context.get('monthly_history') or [])}

## 지난달 대비 (시스템)
- 순자산 {perf.get('change_direction', 'N/A')} {perf.get('change_fmt', 'N/A')} (전월 {perf.get('previous_net_fmt', 'N/A')})
- 현재 저축률: {perf.get('current_savings_rate_fmt', 'N/A')}

## 변동 이벤트
{_format_events_lines(context.get('variable_events') or [])}

## 노후·내집 (간이 추정)
- 노후 월수령: 국민 {pension.get('national_fmt')} + 연금 {pension.get('personal_fmt')} + IRP {pension.get('irp_fmt')} = {pension.get('total_fmt')}
- 내집마련: {home.get('status', '')} — {home.get('detail', '')}

## 거시·시장
{macro_text}

## 작성 지침
- 각 섹션은 구체적·실행 가능하게. 단정적 수익 보장·특정 종목 매수 권유 금지.
- 금융소득 2천만원 종합과세 임박 시 section_2_tax.financial_income_tax_warning에 경고.
- 변동금리 비중 50% 이상이면 section_4_risks.variable_rate_scenario에 금리 인상 시나리오.
- section_5_action_plan은 bullet 리스트(각 2~4개).
- section_6_monthly_report.strengths/improvements는 bullet 리스트(각 2~3개).
- 해당 없으면 "해당 없음" 또는 빈 배열.
- 한국어.

반드시 아래 JSON만 출력:
{{
  "summary": "전체 요약 3~4문장",
  "macro_note": "거시환경 영향 2~3문장",
  "section_1_diagnosis": {{
    "net_worth_analysis": "순자산·또래 대비 분석",
    "savings_rate_evaluation": "저축률 평가",
    "debt_health": "DSR·부채비율·상환 부담",
    "emergency_fund": "비상금 충분 여부",
    "asset_allocation_balance": "자산 배분 균형·쏠림"
  }},
  "section_2_tax": {{
    "irp_pension_tax_saving": "IRP/연금저축 추가 납입 절세 금액",
    "isa_strategy": "ISA 활용 전략",
    "financial_income_tax_warning": "금융소득종합과세 주의 (없으면 해당 없음)",
    "health_insurance_savings": "건강보험료 절감",
    "comprehensive_income_tax_strategy": "종합소득세 절세 전략"
  }},
  "section_3_goals": {{
    "home_purchase": "내집마련 달성 시기·전략",
    "retirement": "노후준비 — 은퇴 시점 자산·월 수령액",
    "fire_age": "FIRE 가능 나이·조건",
    "children_education": "자녀교육비 준비 (없으면 해당 없음)"
  }},
  "section_4_risks": {{
    "variable_rate_scenario": "변동금리 금리 인상 시나리오",
    "income_disruption": "소득 중단 시 버틸 기간",
    "concentration_risk": "자산 쏠림 리스크",
    "insurance_gap": "보험 공백 리스크"
  }},
  "section_5_action_plan": {{
    "this_month": ["이번 달 할 일1", "할 일2"],
    "within_3_months": ["3개월 내1", "3개월 내2"],
    "within_1_year": ["1년 내1", "1년 내2"],
    "mid_long_term": ["중장기1", "중장기2"]
  }},
  "section_6_monthly_report": {{
    "net_worth_change": "지난달 대비 순자산 변화 해석",
    "savings_rate_trend": "저축률 추이·평가",
    "goal_achievement": "목표 달성률",
    "strengths": ["잘한 점1", "잘한 점2"],
    "improvements": ["개선점1", "개선점2"]
  }}
}}"""


def _parse_comprehensive_response(text: str) -> dict:
    result = parse_ai_json_object(text)
    for key in AI_SECTION_KEYS:
        if key not in result:
            raise ValueError(f"AI 응답에 {key} 항목이 없습니다.")
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


def chat_financial_advisor(
    context: dict,
    macro: dict,
    history: list[dict[str, str]],
    user_message: str,
) -> str:
    """재무 상담 채팅 — 사용자 재무 데이터 기반 맞춤 답변."""
    client = create_anthropic_client()
    system_prompt = (
        "당신은 한국 거주자를 위한 재무·세금·부동산·투자 상담 AI입니다.\n"
        "아래 사용자 재무 데이터를 기반으로 맞춤 조언을 제공하세요.\n"
        "단정적 수익 보장·특정 종목 매수 권유는 하지 마세요.\n"
        "모든 답변은 한국어로, 3~8문장 정도로 구체적이되 간결하게 작성하세요.\n\n"
        f"{format_context_for_chat(context, macro)}"
    )
    messages: list[dict[str, str]] = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    messages.append({"role": "user", "content": user_message})

    response = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=2000,
        system=system_prompt,
        messages=messages,
    )
    blocks = [b.text for b in response.content if hasattr(b, "text")]
    if not blocks:
        raise ValueError("AI가 응답을 반환하지 않았습니다.")
    return "\n".join(blocks)
