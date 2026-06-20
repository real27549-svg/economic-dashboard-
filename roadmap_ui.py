"""재테크 로드맵 UI (고정/월별/연간/변동 + Supabase)."""

from __future__ import annotations

from datetime import date

import streamlit as st

from env_config import ENV_FILE, api_key_preview, get_anthropic_api_key, supabase_config_status
from financial_roadmap import (
    HORIZON_LABELS,
    ROADMAP_HORIZONS,
    build_allocation_pie,
    build_roadmap_macro,
)
from roadmap_ai import generate_comprehensive_roadmap
from roadmap_analytics import (
    build_analysis_context,
    build_net_worth_chart,
    build_savings_simulation_chart,
    compute_monthly_metrics,
    compute_tax_deduction_room,
)
from roadmap_db import (
    add_variable_event,
    get_annual_snapshot,
    get_fixed_profile,
    get_monthly_snapshot,
    is_supabase_configured,
    list_annual_history,
    list_monthly_history,
    list_variable_events,
    save_annual_snapshot,
    save_fixed_profile,
    save_monthly_snapshot,
    test_supabase_connection,
)
from roadmap_fields import (
    ANNUAL_FIELDS,
    EDUCATION_OPTIONS,
    GENDER_OPTIONS,
    GOAL_OPTIONS,
    HEALTH_INSURANCE_TYPES,
    HOUSING_OWNERSHIP,
    JOB_TYPES,
    MARITAL_OPTIONS,
    MONTHLY_ASSET_FIELDS,
    MONTHLY_EXPENSE_FIELDS,
    MONTHLY_INCOME_FIELDS,
    MONTHLY_LIABILITY_FIELDS,
    RESIDENCE_TYPES,
    RETIREMENT_PENSION_TYPES,
    RISK_PROFILES,
    VARIABLE_EVENT_TYPES,
    YES_NO,
)
from market_extras import fetch_fear_greed_index, fetch_sector_week_returns
from roadmap_local_id import ensure_local_user_id, restore_local_user_id


@st.cache_data(ttl=300, show_spinner=False)
def _load_fear_greed() -> dict:
    return fetch_fear_greed_index()


@st.cache_data(ttl=300, show_spinner=False)
def _load_sector_returns() -> list[dict]:
    return fetch_sector_week_returns()


def _resolve_api_key() -> str | None:
    return get_anthropic_api_key()


def _render_number_grid(
    fields: dict[str, str],
    data: dict,
    key_prefix: str,
    cols_per_row: int = 4,
) -> dict[str, float]:
    result: dict[str, float] = {}
    keys = list(fields.keys())
    for row_start in range(0, len(keys), cols_per_row):
        cols = st.columns(cols_per_row)
        for col, key in zip(cols, keys[row_start : row_start + cols_per_row]):
            with col:
                result[key] = float(
                    st.number_input(
                        fields[key],
                        min_value=0.0,
                        value=float(data.get(key, 0) or 0),
                        step=10.0,
                        key=f"{key_prefix}_{key}",
                    )
                )
    return result


def _render_fixed_form(local_id: str) -> dict:
    saved = get_fixed_profile(local_id)
    st.markdown("#### 고정 정보 (최초 1회 · 수정 가능)")

    c1, c2, c3 = st.columns(3)
    with c1:
        age = int(st.number_input("나이", 18, 80, int(saved.get("age", 35)), 1, key="fx_age"))
        birth_date = st.text_input(
            "생년월일 (YYYY-MM-DD)",
            saved.get("birth_date", ""),
            key="fx_birth",
        )
        gender = st.selectbox("성별", GENDER_OPTIONS, index=_idx(GENDER_OPTIONS, saved.get("gender")), key="fx_gender")
    with c2:
        marital = st.selectbox("결혼 여부", MARITAL_OPTIONS, index=_idx(MARITAL_OPTIONS, saved.get("marital_status")), key="fx_marital")
        num_children = int(st.number_input("자녀 수", 0, 10, int(saved.get("num_children", 0)), 1, key="fx_children"))
        job = st.selectbox("직업 유형", JOB_TYPES, index=_idx(JOB_TYPES, saved.get("job_type")), key="fx_job")
    with c3:
        education = st.selectbox("최종학력", EDUCATION_OPTIONS, index=_idx(EDUCATION_OPTIONS, saved.get("education")), key="fx_edu")
        health_ins = st.selectbox("건강보험 유형", HEALTH_INSURANCE_TYPES, index=_idx(HEALTH_INSURANCE_TYPES, saved.get("health_insurance")), key="fx_health")
        housing = st.selectbox("주택 소유", HOUSING_OWNERSHIP, index=_idx(HOUSING_OWNERSHIP, saved.get("housing_ownership")), key="fx_housing")

    c4, c5, c6 = st.columns(3)
    with c4:
        residence = st.selectbox("거주 형태", RESIDENCE_TYPES, index=_idx(RESIDENCE_TYPES, saved.get("residence_type")), key="fx_residence")
        pension_type = st.selectbox("퇴직연금 유형", RETIREMENT_PENSION_TYPES, index=_idx(RETIREMENT_PENSION_TYPES, saved.get("retirement_pension_type")), key="fx_pension")
        sub_points = st.text_input("청약 가점", saved.get("subscription_points", ""), key="fx_sub_pts")
    with c5:
        credit_score = st.text_input("신용점수 (대략)", saved.get("credit_score", ""), key="fx_credit")
        retire_age = int(st.number_input("은퇴 희망 나이", 40, 80, int(saved.get("retirement_age", 65)), 1, key="fx_retire"))
        dependents = int(st.number_input("부양가족 수", 0, 10, int(saved.get("dependents", 0)), 1, key="fx_dep"))
    with c6:
        risk = st.selectbox("투자 성향", RISK_PROFILES, index=_idx(RISK_PROFILES, saved.get("risk_profile", "중립형")), key="fx_risk")
        special = st.selectbox("장애인/경로우대", YES_NO, index=_idx(YES_NO, saved.get("special_benefit", "아니오")), key="fx_special")
        saved_goals = saved.get("goals") or ["자산증식"]
        goals = st.multiselect("재테크 목표 (복수)", GOAL_OPTIONS, default=[g for g in saved_goals if g in GOAL_OPTIONS], key="fx_goals")

    st.markdown("##### 생애 계획 · 내집마련")
    p1, p2, p3 = st.columns(3)
    with p1:
        marriage_planned = st.selectbox("결혼 예정", YES_NO, index=_idx(YES_NO, saved.get("marriage_planned", "아니오")), key="fx_marriage")
        marriage_when = st.text_input("결혼 예정 시기", saved.get("marriage_planned_when", ""), key="fx_marriage_when")
    with p2:
        birth_planned = st.text_input("출산 계획", saved.get("birth_planned", ""), key="fx_birth_plan")
        home_when = st.text_input("내집마련 희망 시기", saved.get("home_target_when", ""), key="fx_home_when")
    with p3:
        home_amount = float(st.number_input("내집마련 목표 금액 (만원)", 0.0, value=float(saved.get("home_target_amount_man", 0) or 0), step=500.0, key="fx_home_amt"))
        home_region = st.text_input("희망 지역", saved.get("home_target_region", ""), key="fx_home_region")

    data = {
        "age": age,
        "birth_date": birth_date,
        "gender": gender,
        "marital_status": marital,
        "num_children": num_children,
        "job_type": job,
        "education": education,
        "health_insurance": health_ins,
        "housing_ownership": housing,
        "residence_type": residence,
        "retirement_pension_type": pension_type,
        "subscription_points": sub_points,
        "credit_score": credit_score,
        "retirement_age": retire_age,
        "dependents": dependents,
        "risk_profile": risk,
        "special_benefit": special,
        "goals": goals or ["자산증식"],
        "marriage_planned": marriage_planned,
        "marriage_planned_when": marriage_when,
        "birth_planned": birth_planned,
        "home_target_when": home_when,
        "home_target_amount_man": home_amount,
        "home_target_region": home_region,
    }

    if st.button("고정 정보 저장", type="primary", key="save_fixed"):
        try:
            save_fixed_profile(local_id, data)
            st.success("고정 정보가 저장되었습니다.")
        except Exception as exc:
            st.error(f"저장 실패: {exc}")
    return data


def _idx(options: tuple | list, value) -> int:
    try:
        return list(options).index(value)
    except ValueError:
        return 0


def _render_monthly_form(local_id: str) -> dict:
    st.markdown("#### 월별 업데이트 (매달 말 입력)")
    today = date.today()
    default_ym = f"{today.year}-{today.month:02d}"
    year_month = st.text_input("대상 년월 (YYYY-MM)", default_ym, key="mo_ym")

    saved = get_monthly_snapshot(local_id, year_month.strip())

    st.markdown("##### 수입 (만원)")
    income = _render_number_grid(MONTHLY_INCOME_FIELDS, saved, "mo_inc")

    st.markdown("##### 지출 (만원)")
    expense = _render_number_grid(MONTHLY_EXPENSE_FIELDS, saved, "mo_exp")

    st.markdown("##### 자산 (만원)")
    assets = _render_number_grid(MONTHLY_ASSET_FIELDS, saved, "mo_ast")

    st.markdown("##### 부채 (만원)")
    liabilities = _render_number_grid(MONTHLY_LIABILITY_FIELDS, saved, "mo_liab", cols_per_row=2)

    monthly = {**income, **expense, **assets, **liabilities}
    metrics = compute_monthly_metrics(monthly)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("자산 합계", metrics["total_assets_fmt"])
    m2.metric("부채 합계", metrics["total_debt_fmt"])
    m3.metric("순자산", metrics["net_assets_fmt"])
    m4.metric("저축률", metrics["savings_rate_fmt"])

    if st.button("월별 데이터 저장", type="primary", key="save_monthly"):
        try:
            save_monthly_snapshot(
                local_id,
                year_month.strip(),
                monthly,
                metrics["net_assets_man"],
            )
            st.success(f"{year_month} 월별 데이터가 저장되었습니다.")
        except Exception as exc:
            st.error(f"저장 실패: {exc}")
    return monthly


def _render_annual_form(local_id: str) -> dict:
    st.markdown("#### 연간 업데이트 (1년에 한 번)")
    year = int(st.number_input("대상 연도", 2020, 2035, date.today().year, 1, key="an_year"))
    saved = get_annual_snapshot(local_id, year)

    annual: dict = {}
    keys = list(ANNUAL_FIELDS.keys())
    for row_start in range(0, len(keys), 3):
        cols = st.columns(3)
        for col, key in zip(cols, keys[row_start : row_start + 3]):
            with col:
                label = ANNUAL_FIELDS[key]
                if key == "housing_lottery_won":
                    annual[key] = st.selectbox(
                        label,
                        ["아니오", "예"],
                        index=0 if saved.get(key) != "예" else 1,
                        key=f"an_{key}",
                    )
                elif key == "credit_vs_check_ratio":
                    annual[key] = float(
                        st.number_input(
                            label,
                            0.0,
                            100.0,
                            float(saved.get(key, 50) or 50),
                            5.0,
                            key=f"an_{key}",
                        )
                    )
                else:
                    annual[key] = float(
                        st.number_input(
                            label,
                            0.0,
                            value=float(saved.get(key, 0) or 0),
                            step=10.0,
                            key=f"an_{key}",
                        )
                    )

    tax = compute_tax_deduction_room(annual)
    t1, t2, t3 = st.columns(3)
    t1.metric("연금/IRP 절세 잔여", tax["combined_pension_room_fmt"])
    t2.metric("ISA 납입 잔여", tax["isa_room_fmt"])
    t3.metric("금융소득", tax["financial_income_fmt"])
    if tax.get("financial_income_warning"):
        st.warning(tax["financial_income_warning"])

    if st.button("연간 데이터 저장", type="primary", key="save_annual"):
        try:
            save_annual_snapshot(local_id, year, annual)
            st.success(f"{year}년 연간 데이터가 저장되었습니다.")
        except Exception as exc:
            st.error(f"저장 실패: {exc}")
    return annual


def _render_variable_form(local_id: str) -> None:
    st.markdown("#### 변동 항목 (바뀔 때만 기록)")
    event_type = st.selectbox(
        "변동 유형",
        list(VARIABLE_EVENT_TYPES.keys()),
        format_func=lambda k: VARIABLE_EVENT_TYPES[k],
        key="var_type",
    )
    note = st.text_area("상세 내용", key="var_note")
    extra = st.text_input("추가 메모 (금액·시기 등)", key="var_extra")

    if st.button("변동 이벤트 기록", key="save_var"):
        try:
            add_variable_event(
                local_id,
                event_type,
                {"note": note, "extra": extra, "label": VARIABLE_EVENT_TYPES[event_type]},
            )
            st.success("변동 이벤트가 기록되었습니다.")
        except Exception as exc:
            st.error(f"기록 실패: {exc}")

    events = list_variable_events(local_id)
    if events:
        st.markdown("##### 변동 이력")
        for ev in events[:20]:
            recorded = (ev.get("recorded_at") or "")[:10]
            data = ev.get("data") or {}
            label = VARIABLE_EVENT_TYPES.get(ev.get("event_type", ""), ev.get("event_type", ""))
            st.caption(f"**{recorded}** · {label} — {data.get('note', '')} {data.get('extra', '')}")


def _render_history_charts(local_id: str, metrics: dict) -> None:
    history = list_monthly_history(local_id)
    chart = build_net_worth_chart(
        [
            {"year_month": h["year_month"], "net_assets_man": h.get("net_assets_man")}
            for h in history
            if h.get("net_assets_man") is not None
        ]
    )
    if chart:
        st.plotly_chart(chart, use_container_width=True)
    else:
        st.info("월별 데이터를 저장하면 순자산 추이 그래프가 표시됩니다.")

    savings = float(metrics.get("monthly_savings_man", 0) or 0)
    net = float(metrics.get("net_assets_man", 0) or 0)
    if savings > 0 or net > 0:
        st.plotly_chart(
            build_savings_simulation_chart(savings, net, years=10),
            use_container_width=True,
        )


def _render_ai_results(roadmap: dict) -> None:
    st.success(roadmap.get("summary", ""))
    if roadmap.get("macro_note"):
        st.info(f"**거시환경** — {roadmap['macro_note']}")

    insight_fields = [
        ("savings_rate_note", "저축률 분석"),
        ("emergency_fund_note", "비상금 평가"),
        ("tax_deduction_analysis", "절세 가능 금액 (IRP·연금저축·ISA)"),
        ("financial_income_tax_warning", "금융소득종합과세 주의"),
        ("comprehensive_income_tax_strategy", "종합소득세 절세 전략"),
        ("home_purchase_timeline", "내집마련 달성 시기"),
        ("homeless_benefits", "무주택자 혜택"),
        ("credit_score_guide", "신용점수 관리"),
        ("health_insurance_savings", "건강보험료 절감"),
        ("insurance_remodeling", "생애주기별 보험 리모델링"),
        ("savings_simulation_note", "저축 시뮬레이션"),
    ]
    for key, title in insight_fields:
        val = roadmap.get(key)
        if val and str(val).strip() and str(val).strip() != "해당 없음":
            st.markdown(f"**{title}**")
            if key == "financial_income_tax_warning":
                st.warning(val)
            else:
                st.write(val)

    pension = roadmap.get("pension_monthly_estimate") or {}
    if pension:
        st.markdown("**노후 월수령액 (추정)**")
        pc = st.columns(4)
        pc[0].metric("국민연금", pension.get("national", "N/A"))
        pc[1].metric("연금저축", pension.get("personal", "N/A"))
        pc[2].metric("IRP", pension.get("irp", "N/A"))
        pc[3].metric("합계", pension.get("total", "N/A"))
        if pension.get("note"):
            st.caption(pension["note"])

    if roadmap.get("tax_strategy"):
        st.markdown("**절세 전략**")
        for tip in roadmap["tax_strategy"]:
            st.markdown(f"- {tip}")

    if roadmap.get("global_risks"):
        st.markdown("**리스크 경고**")
        for risk in roadmap["global_risks"]:
            st.warning(risk)

    st.divider()
    plan_tabs = st.tabs([HORIZON_LABELS[h] for h in ROADMAP_HORIZONS])
    plans = roadmap.get("plans") or {}
    for tab, horizon in zip(plan_tabs, ROADMAP_HORIZONS):
        with tab:
            plan = plans.get(horizon)
            if not plan:
                st.warning(f"{HORIZON_LABELS[horizon]} 데이터 없음")
                continue
            st.markdown(f"**{plan.get('headline', HORIZON_LABELS[horizon])}**")
            st.metric("목표 자산", plan.get("target_asset_fmt", "N/A"))
            col_chart, col_guide = st.columns([1, 1])
            with col_chart:
                st.plotly_chart(
                    build_allocation_pie(plan.get("allocation") or {}, f"{HORIZON_LABELS[horizon]} 배분"),
                    use_container_width=True,
                )
            with col_guide:
                st.markdown("**실행 가이드**")
                for action in plan.get("actions") or []:
                    st.markdown(f"- {action}")
                st.markdown("**리스크**")
                for risk in plan.get("risks") or []:
                    st.warning(risk)


def render_financial_roadmap_section(indicator_snapshot: dict) -> None:
    st.markdown("### 🗺️ 재테크 로드맵")
    st.caption(
        "고정·월별·연간·변동 정보를 Supabase에 누적 저장하고 Claude가 맞춤 분석합니다. "
        "투자 참고용이며 투자 권유가 아닙니다."
    )

    if not is_supabase_configured():
        status = supabase_config_status()
        st.error(
            f"Supabase 연결이 필요합니다. `{ENV_FILE}`에 "
            "`SUPABASE_URL`과 `SUPABASE_ANON_KEY`(또는 `SUPABASE_KEY`)를 설정하세요."
        )
        st.caption(
            f"진단: env 파일 존재={status['env_file_exists']} · "
            f"URL={status['url_set']} · KEY={status['key_set']} · "
            f"발견된 키: {status['found_keys']}"
        )
        if st.button("Supabase 연결 테스트", key="supabase_test_unconfigured"):
            result = test_supabase_connection()
            if result["ok"]:
                st.success(result["message"])
                st.rerun()
            else:
                st.error(f"[{result.get('step', '?')}] {result['message']}")
        return

    with st.expander("Supabase 연결 상태", expanded=False):
        if st.button("연결 테스트 실행", key="supabase_test_btn"):
            with st.spinner("Supabase 연결 테스트 중..."):
                result = test_supabase_connection()
            if result["ok"]:
                st.success(result["message"])
                st.caption(f"URL: `{result.get('url_preview', '')}`")
                st.caption(f"테이블: {', '.join(result.get('tables', []))}")
            else:
                st.error(f"[{result.get('step', '?')}] {result['message']}")

    api_key = _resolve_api_key()
    if not api_key:
        st.warning("`.env`에 Anthropic API Key를 설정하면 AI 분석을 사용할 수 있습니다.")
        return

    local_id = ensure_local_user_id()
    with st.expander("내 데이터 ID (다른 기기에서 불러오기)", expanded=False):
        st.code(local_id, language=None)
        st.caption("URL의 `uid` 파라미터 또는 아래 입력으로 동일 데이터를 불러올 수 있습니다.")
        pasted = st.text_input("기존 ID 붙여넣기", key="restore_uid")
        if st.button("ID 복원", key="btn_restore_uid"):
            restored = restore_local_user_id(pasted)
            if restored:
                st.success("ID가 복원되었습니다. 페이지가 갱신됩니다.")
                st.rerun()
            else:
                st.error("유효하지 않은 ID입니다.")

    st.caption(f"API 키: `{api_key_preview(api_key)}` · 데이터 ID: `{local_id[:8]}…`")

    tab_fixed, tab_monthly, tab_annual, tab_variable, tab_analysis = st.tabs(
        ["📌 고정 정보", "📅 월별", "📆 연간", "🔄 변동", "🤖 AI 분석"]
    )

    fixed = get_fixed_profile(local_id)
    monthly: dict = {}
    annual: dict = {}

    with tab_fixed:
        fixed = _render_fixed_form(local_id)

    with tab_monthly:
        monthly = _render_monthly_form(local_id)

    with tab_annual:
        annual = _render_annual_form(local_id)

    with tab_variable:
        _render_variable_form(local_id)

    with tab_analysis:
        st.markdown("#### AI 종합 분석")
        if not fixed:
            st.info("먼저 「고정 정보」 탭에서 프로필을 저장하세요.")
        if not monthly.get("net_income"):
            st.info("「월별」 탭에서 이번 달 수입·지출·자산을 입력·저장하세요.")

        metrics = compute_monthly_metrics(monthly) if monthly else {}
        if metrics:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("순자산", metrics.get("net_assets_fmt", "N/A"))
            c2.metric("저축률", metrics.get("savings_rate_fmt", "N/A"))
            c3.metric("비상금", metrics.get("liquid_reserve_fmt", "N/A"))
            c4.metric("월 저축", metrics.get("monthly_savings_fmt", "N/A"))
            _render_history_charts(local_id, metrics)

        if st.button("AI 종합 분석 실행", type="primary", use_container_width=True, key="run_ai"):
            try:
                monthly_history = list_monthly_history(local_id)
                annual_history = list_annual_history(local_id)
                variable_events = list_variable_events(local_id)
                fixed_data = get_fixed_profile(local_id) or fixed
                ym = date.today().strftime("%Y-%m")
                monthly_data = get_monthly_snapshot(local_id, ym) or monthly
                annual_data = get_annual_snapshot(local_id, date.today().year) or annual

                context = build_analysis_context(
                    fixed_data,
                    monthly_data,
                    annual_data,
                    annual_history,
                    variable_events,
                    monthly_history,
                )

                with st.spinner("거시지표 반영 중..."):
                    fear_greed = _load_fear_greed()
                    sectors = _load_sector_returns()
                    macro = build_roadmap_macro(indicator_snapshot, fear_greed, sectors)
            except Exception:
                macro = {"indicators": indicator_snapshot}

            try:
                with st.spinner("Claude가 종합 로드맵을 작성하는 중..."):
                    roadmap = generate_comprehensive_roadmap(context, macro)
                st.session_state["roadmap_ai_result"] = roadmap
            except Exception as exc:
                st.error(f"AI 분석 실패: {exc}")

        if st.session_state.get("roadmap_ai_result"):
            _render_ai_results(st.session_state["roadmap_ai_result"])
