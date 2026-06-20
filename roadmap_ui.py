"""재테크 로드맵 UI (고정/월별/자산/연간/변동 + Supabase)."""

from __future__ import annotations

import uuid
from datetime import date

import streamlit as st

from env_config import (
    ENV_FILE,
    anthropic_config_status,
    api_key_preview,
    supabase_config_status,
)
import env_config
from financial_roadmap import build_roadmap_macro
from roadmap_ai import (
    CHAT_EXAMPLE_QUESTIONS,
    chat_financial_advisor,
    generate_comprehensive_roadmap,
)
from roadmap_analytics import (
    build_analysis_context,
    build_net_worth_chart,
    build_savings_simulation_chart,
    compute_monthly_metrics,
    compute_tax_deduction_room,
)
from roadmap_debt import (
    LOAN_CATEGORIES,
    RATE_TYPES,
    empty_loan,
    normalize_loans,
)
from roadmap_db import (
    add_variable_event,
    get_annual_snapshot,
    get_fixed_profile,
    get_monthly_snapshot,
    get_stock_holdings,
    is_stock_holdings_table_available,
    is_supabase_configured,
    list_annual_history,
    list_monthly_history,
    list_variable_events,
    save_annual_snapshot,
    save_fixed_profile,
    save_monthly_snapshot,
    save_stock_holdings,
    test_supabase_connection,
)
import roadmap_holdings
from roadmap_holdings import (
    aggregate_holdings,
    clear_quote_cache,
    new_holding,
    pop_rate_limit_warnings,
    refresh_holding_identity,
    strip_holding_for_save,
)
from roadmap_holdings_ocr import import_holdings_from_screenshots
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
    RESIDENCE_TYPES,
    RETIREMENT_PENSION_TYPES,
    RISK_PROFILES,
    STOCK_ACCOUNT_TYPES,
    STOCK_MARKET_LABELS,
    UNIT_NOTE,
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
    return env_config.get_anthropic_api_key()


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
        age = int(st.number_input("나이 (세)", 18, 80, int(saved.get("age", 35)), 1, key="fx_age"))
        birth_date = st.text_input(
            "생년월일 (YYYY-MM-DD)",
            saved.get("birth_date", ""),
            key="fx_birth",
        )
        gender = st.selectbox("성별", GENDER_OPTIONS, index=_idx(GENDER_OPTIONS, saved.get("gender")), key="fx_gender")
    with c2:
        marital = st.selectbox("결혼 여부", MARITAL_OPTIONS, index=_idx(MARITAL_OPTIONS, saved.get("marital_status")), key="fx_marital")
        num_children = int(st.number_input("자녀 수 (명)", 0, 10, int(saved.get("num_children", 0)), 1, key="fx_children"))
        job = st.selectbox("직업 유형", JOB_TYPES, index=_idx(JOB_TYPES, saved.get("job_type")), key="fx_job")
    with c3:
        education = st.selectbox("최종학력", EDUCATION_OPTIONS, index=_idx(EDUCATION_OPTIONS, saved.get("education")), key="fx_edu")
        health_ins = st.selectbox("건강보험 유형", HEALTH_INSURANCE_TYPES, index=_idx(HEALTH_INSURANCE_TYPES, saved.get("health_insurance")), key="fx_health")
        housing = st.selectbox("주택 소유", HOUSING_OWNERSHIP, index=_idx(HOUSING_OWNERSHIP, saved.get("housing_ownership")), key="fx_housing")

    c4, c5, c6 = st.columns(3)
    with c4:
        residence = st.selectbox("거주 형태", RESIDENCE_TYPES, index=_idx(RESIDENCE_TYPES, saved.get("residence_type")), key="fx_residence")
        pension_type = st.selectbox("퇴직연금 유형", RETIREMENT_PENSION_TYPES, index=_idx(RETIREMENT_PENSION_TYPES, saved.get("retirement_pension_type")), key="fx_pension")
        sub_points = st.text_input("청약 가점 (점)", saved.get("subscription_points", ""), key="fx_sub_pts")
    with c5:
        credit_score = st.text_input("신용점수 (점)", saved.get("credit_score", ""), key="fx_credit")
        retire_age = int(st.number_input("은퇴 희망 나이 (세)", 40, 80, int(saved.get("retirement_age", 65)), 1, key="fx_retire"))
        dependents = int(st.number_input("부양가족 수 (명)", 0, 10, int(saved.get("dependents", 0)), 1, key="fx_dep"))
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


def _render_single_loan(
    loan_key: str,
    label: str,
    saved: dict,
    prefix: str,
) -> dict:
    entry = normalize_loans({loan_key: saved}).get(loan_key, empty_loan())
    with st.expander(label, expanded=entry["active"]):
        active = st.checkbox(
            "해당 대출 보유",
            value=entry["active"],
            key=f"{prefix}_{loan_key}_active",
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            balance = float(
                st.number_input(
                    "대출 잔액 (만원)",
                    min_value=0.0,
                    value=float(entry["balance_man"]),
                    step=100.0,
                    key=f"{prefix}_{loan_key}_bal",
                )
            )
            rate = float(
                st.number_input(
                    "금리 (%)",
                    min_value=0.0,
                    max_value=30.0,
                    value=float(entry["rate_pct"]),
                    step=0.1,
                    key=f"{prefix}_{loan_key}_rate",
                )
            )
        with c2:
            rate_type = st.selectbox(
                "금리 유형",
                RATE_TYPES,
                index=_idx(RATE_TYPES, entry["rate_type"]),
                key=f"{prefix}_{loan_key}_rtype",
            )
            monthly_pay = float(
                st.number_input(
                    "월 상환액 (만원)",
                    min_value=0.0,
                    value=float(entry["monthly_payment_man"]),
                    step=10.0,
                    key=f"{prefix}_{loan_key}_pay",
                )
            )
        with c3:
            maturity = st.text_input(
                "만기일 (YYYY-MM)",
                value=entry["maturity"],
                key=f"{prefix}_{loan_key}_mat",
            )
            bank = st.text_input(
                "금융기관명",
                value=entry["bank"],
                key=f"{prefix}_{loan_key}_bank",
            )
    return {
        "active": active or balance > 0,
        "balance_man": balance if active or balance > 0 else 0.0,
        "rate_pct": rate,
        "rate_type": rate_type,
        "monthly_payment_man": monthly_pay,
        "maturity": maturity,
        "bank": bank,
    }


_STOCK_ASSET_KEYS = ("domestic_stocks", "foreign_stocks")
_OTHER_MONTHLY_ASSET_FIELDS = {
    k: v for k, v in MONTHLY_ASSET_FIELDS.items() if k not in _STOCK_ASSET_KEYS
}


def _default_year_month() -> str:
    today = date.today()
    return f"{today.year}-{today.month:02d}"


def _active_year_month() -> str:
    return st.session_state.get("mo_ym", _default_year_month()).strip()


def _merge_monthly_partial(
    local_id: str,
    year_month: str,
    partial: dict,
) -> dict:
    saved = get_monthly_snapshot(local_id, year_month) or {}
    clean = {k: v for k, v in saved.items() if not str(k).startswith("_")}
    return {**clean, **partial}


def _holdings_session_key(local_id: str) -> str:
    return f"roadmap_holdings_{local_id}"


def _load_holdings_list(local_id: str) -> list[dict]:
    key = _holdings_session_key(local_id)
    if key not in st.session_state:
        st.session_state[key] = get_stock_holdings(local_id) if is_supabase_configured() else []
    return st.session_state[key]


def _collect_holdings_edits(holdings: list[dict]) -> list[dict]:
    updated: list[dict] = []
    for holding in holdings:
        hid = holding["id"]
        account = st.session_state.get(f"ha_{hid}", holding.get("account_type", "direct"))
        if account not in STOCK_ACCOUNT_TYPES:
            account = "direct"
        default_name = holding.get("name") or holding.get("query") or holding.get("ticker") or ""
        name_input = str(st.session_state.get(f"hn_{hid}", default_name)).strip()
        updated.append(
            {
                **holding,
                "name": name_input or default_name,
                "quantity": float(st.session_state.get(f"hq_{hid}", holding.get("quantity", 0))),
                "avg_price": float(st.session_state.get(f"hp_{hid}", holding.get("avg_price", 0))),
                "account_type": account,
            }
        )
    return updated


def _holding_base_from_session(holding: dict) -> dict:
    hid = holding["id"]
    account = st.session_state.get(f"ha_{hid}", holding.get("account_type", "direct"))
    if account not in STOCK_ACCOUNT_TYPES:
        account = "direct"
    return {
        **holding,
        "quantity": float(st.session_state.get(f"hq_{hid}", holding.get("quantity", 0))),
        "avg_price": float(st.session_state.get(f"hp_{hid}", holding.get("avg_price", 0))),
        "account_type": account,
    }


def _resolve_holding_name(holdings_key: str, holding_id: str) -> None:
    """종목명 입력 후 자동으로 티커·상장 조회."""
    query = str(st.session_state.get(f"hn_{holding_id}", "")).strip()
    holdings = st.session_state.get(holdings_key, [])
    err_key = f"holdings_name_error_{holding_id}"
    st.session_state.pop(err_key, None)

    if not query:
        return

    updated: list[dict] = []
    for holding in holdings:
        if holding["id"] != holding_id:
            updated.append(holding)
            continue
        base = _holding_base_from_session(holding)
        try:
            resolved = refresh_holding_identity(base, query, force=True)
            st.session_state[f"hn_{holding_id}"] = resolved.get("name") or query
            updated.append(resolved)
        except Exception as exc:
            st.session_state[err_key] = str(exc)
            updated.append({**base, "name": query, "query": query})
    st.session_state[holdings_key] = updated


def _make_holding_name_handler(holdings_key: str, holding_id: str):
    def _handler() -> None:
        _resolve_holding_name(holdings_key, holding_id)

    return _handler


def _delete_selected_holdings(holdings_key: str) -> int:
    holdings = st.session_state.get(holdings_key, [])
    remaining = [
        h for h in holdings if not st.session_state.get(f"hsel_{h['id']}", False)
    ]
    removed = len(holdings) - len(remaining)
    st.session_state[holdings_key] = remaining
    return removed


def _set_all_holdings_selected(holdings_key: str, selected: bool) -> None:
    for holding in st.session_state.get(holdings_key, []):
        st.session_state[f"hsel_{holding['id']}"] = selected


def _set_all_screenshots_selected(local_id: str, selected: bool) -> None:
    for item in _load_screenshot_queue(local_id):
        st.session_state[f"ss_sel_{item['id']}"] = selected


def _update_holdings_master_state(holdings_key: str, master_key: str) -> None:
    holdings = st.session_state.get(holdings_key, [])
    st.session_state[master_key] = bool(holdings) and all(
        st.session_state.get(f"hsel_{h['id']}", False) for h in holdings
    )


def _update_screenshots_master_state(local_id: str, master_key: str) -> None:
    queue = _load_screenshot_queue(local_id)
    st.session_state[master_key] = bool(queue) and all(
        st.session_state.get(f"ss_sel_{item['id']}", False) for item in queue
    )


def _make_holdings_master_handler(holdings_key: str, master_key: str):
    def _handler() -> None:
        _set_all_holdings_selected(
            holdings_key,
            bool(st.session_state.get(master_key, False)),
        )

    return _handler


def _make_screenshots_master_handler(local_id: str, master_key: str):
    def _handler() -> None:
        _set_all_screenshots_selected(
            local_id,
            bool(st.session_state.get(master_key, False)),
        )

    return _handler


def _init_holding_name_key(holding: dict) -> None:
    hid = holding["id"]
    if f"hn_{hid}" not in st.session_state:
        st.session_state[f"hn_{hid}"] = (
            holding.get("name") or holding.get("query") or holding.get("ticker") or ""
        )


def _screenshots_session_key(local_id: str) -> str:
    return f"holdings_screenshots_{local_id}"


def _screenshot_upload_widget_key(local_id: str) -> str:
    nonce = st.session_state.get(f"ss_upload_nonce_{local_id}", 0)
    return f"holdings_screenshot_upload_{local_id}_{nonce}"


def _bump_screenshot_upload_widget(local_id: str) -> None:
    key = f"ss_upload_nonce_{local_id}"
    st.session_state[key] = st.session_state.get(key, 0) + 1


def _delete_selected_screenshots(local_id: str) -> int:
    queue = _load_screenshot_queue(local_id)
    delete_ids = [
        item["id"]
        for item in queue
        if st.session_state.get(f"ss_sel_{item['id']}", False)
    ]
    if not delete_ids:
        return 0
    delete_set = set(delete_ids)
    st.session_state[_screenshots_session_key(local_id)] = [
        item for item in queue if item["id"] not in delete_set
    ]
    for sid in delete_ids:
        st.session_state.pop(f"ss_sel_{sid}", None)
    st.session_state.pop(f"ss_master_{local_id}", None)
    _bump_screenshot_upload_widget(local_id)
    return len(delete_ids)


def _load_screenshot_queue(local_id: str) -> list[dict]:
    key = _screenshots_session_key(local_id)
    if key not in st.session_state:
        st.session_state[key] = []
    return st.session_state[key]


def _append_screenshots(local_id: str, uploads) -> int:
    queue = _load_screenshot_queue(local_id)
    existing = {(item["name"], item["size"]) for item in queue}
    added = 0
    for upload in uploads or []:
        data = upload.getvalue()
        name = upload.name or f"screenshot-{len(queue) + 1}.png"
        signature = (name, len(data))
        if signature in existing:
            continue
        queue.append(
            {
                "id": str(uuid.uuid4()),
                "name": name,
                "bytes": data,
                "size": len(data),
            }
        )
        existing.add(signature)
        added += 1
    st.session_state[_screenshots_session_key(local_id)] = queue
    return added


def _render_screenshot_queue(
    local_id: str,
    holdings_key: str,
    holdings: list[dict],
    default_account: str,
) -> None:
    queue = _load_screenshot_queue(local_id)

    new_uploads = st.file_uploader(
        "스크린샷 추가",
        type=["png", "jpg", "jpeg", "webp"],
        accept_multiple_files=True,
        key=_screenshot_upload_widget_key(local_id),
        label_visibility="collapsed",
    )
    if new_uploads:
        added = _append_screenshots(local_id, new_uploads)
        if added:
            st.toast(f"스크린샷 {added}장 추가")
            st.rerun()

    if not queue:
        st.info("스크린샷을 추가하면 목록에서 선택·삭제 후 추출할 수 있습니다.")
        return

    st.caption("체크한 스크린샷만 추출·삭제됩니다.")
    ss_master_key = f"ss_master_{local_id}"
    _update_screenshots_master_state(local_id, ss_master_key)
    head = st.columns([0.08, 0.22, 0.7])
    head[0].checkbox(
        "전체 선택",
        key=ss_master_key,
        on_change=_make_screenshots_master_handler(local_id, ss_master_key),
        label_visibility="collapsed",
    )
    head[1].markdown("**미리보기**")
    head[2].markdown("**파일명**")
    for item in queue:
        shot_id = item["id"]
        row = st.columns([0.08, 0.22, 0.7])
        with row[0]:
            if f"ss_sel_{shot_id}" not in st.session_state:
                st.session_state[f"ss_sel_{shot_id}"] = False
            st.checkbox(
                "선택",
                key=f"ss_sel_{shot_id}",
                label_visibility="collapsed",
            )
        with row[1]:
            st.image(item["bytes"], width=120)
        with row[2]:
            st.markdown(f"**{item['name']}**")
            st.caption(f"{item['size'] // 1024} KB")

    btn_del, btn_extract, _ = st.columns([1, 1, 2])
    with btn_del:
        if st.button("선택 삭제", key="delete_selected_screenshots"):
            removed = _delete_selected_screenshots(local_id)
            if removed:
                st.toast(f"스크린샷 {removed}장 삭제")
                st.rerun()
            else:
                st.warning("삭제할 스크린샷을 체크하세요.")
    with btn_extract:
        selected = [
            item for item in queue if st.session_state.get(f"ss_sel_{item['id']}", False)
        ]
        extract_label = f"선택 {len(selected)}장 추출" if selected else "선택 0장 추출"
        if st.button(extract_label, type="secondary", key="extract_holdings_from_screenshot"):
            if not selected:
                st.warning("추출할 스크린샷을 선택하세요.")
            elif not _resolve_api_key():
                st.error(
                    "Anthropic API Key가 필요합니다. `.env` 또는 Streamlit Secrets에 "
                    "`ANTHROPIC_API_KEY`를 설정하세요."
                )
            else:
                files = [(item["bytes"], item["name"]) for item in selected]
                with st.spinner(f"AI가 {len(files)}장의 계좌 화면을 분석 중..."):
                    try:
                        created, ocr_errors = import_holdings_from_screenshots(
                            files,
                            default_account,
                        )
                        if created:
                            st.session_state[holdings_key] = holdings + created
                            for item in created:
                                st.session_state[f"hsel_{item['id']}"] = True
                            _bump_screenshot_upload_widget(local_id)
                            st.success(
                                f"{len(selected)}장에서 {len(created)}개 종목을 추출해 추가했습니다."
                            )
                        else:
                            st.warning("추출된 종목이 없습니다.")
                        if ocr_errors:
                            with st.expander("추출 중 일부 오류"):
                                for err in ocr_errors:
                                    st.caption(f"- {err}")
                        if created:
                            st.rerun()
                    except Exception as exc:
                        st.error(f"스크린샷 분석 실패: {exc}")


def _format_holding_price(price: float | None, market: str) -> str:
    if price is None:
        return "N/A"
    if market == "domestic":
        return f"{price:,.0f}원"
    return f"${price:,.2f}"


def _supabase_sql_editor_url() -> str | None:
    url = env_config.get_supabase_url() or ""
    if ".supabase.co" not in url:
        return None
    ref = url.replace("https://", "").replace("http://", "").split(".")[0]
    return f"https://supabase.com/dashboard/project/{ref}/sql/new"


_HOLDINGS_MIGRATION_SQL = """CREATE TABLE IF NOT EXISTS roadmap_stock_holdings (
  local_id TEXT PRIMARY KEY REFERENCES roadmap_users(local_id) ON DELETE CASCADE,
  data JSONB NOT NULL DEFAULT '[]'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE roadmap_stock_holdings ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'roadmap_stock_holdings'
      AND policyname = 'roadmap_holdings_anon_all'
  ) THEN
    CREATE POLICY "roadmap_holdings_anon_all" ON roadmap_stock_holdings
      FOR ALL TO anon USING (true) WITH CHECK (true);
  END IF;
END $$;"""


def _show_holdings_quote_warnings() -> None:
    for msg in st.session_state.pop("holdings_quote_warnings", []) or []:
        st.warning(msg)


def _stash_holdings_quote_warnings() -> None:
    warnings = pop_rate_limit_warnings()
    if warnings:
        st.session_state["holdings_quote_warnings"] = warnings


def _render_stock_holdings_section(local_id: str, saved: dict) -> tuple[float, float]:
    holdings_key = _holdings_session_key(local_id)
    mode_key = "roadmap_holdings_mode"

    if is_supabase_configured() and not is_stock_holdings_table_available():
        st.error(
            "Supabase에 `roadmap_stock_holdings` 테이블이 없습니다. "
            "아래 SQL을 **SQL Editor**에 붙여넣어 실행한 뒤 페이지를 새로고침하세요."
        )
        editor_url = _supabase_sql_editor_url()
        if editor_url:
            st.markdown(f"[Supabase SQL Editor 열기]({editor_url})")
        with st.expander("실행할 SQL (복사)", expanded=True):
            st.code(_HOLDINGS_MIGRATION_SQL, language="sql")
        if st.button("테이블 생성 확인 (새로고침)", key="recheck_holdings_table"):
            from roadmap_db import reset_stock_holdings_table_cache

            reset_stock_holdings_table_cache()
            st.rerun()

    holdings = _load_holdings_list(local_id)
    edited_holdings = _collect_holdings_edits(holdings) if holdings else []
    computed: list[dict] = []
    domestic_total = 0.0
    foreign_total = 0.0

    _show_holdings_quote_warnings()

    if edited_holdings:
        try:
            domestic_total, foreign_total, computed = aggregate_holdings(edited_holdings)
            _stash_holdings_quote_warnings()
            _show_holdings_quote_warnings()
        except Exception as exc:
            st.warning(f"보유종목 평가 실패: {exc}")

    btn_col, cap_col = st.columns([1, 3])
    with btn_col:
        if st.button("종목별 입력", type="primary", key="btn_stock_holdings_mode"):
            st.session_state[mode_key] = not st.session_state.get(mode_key, False)
            st.rerun()
    with cap_col:
        if holdings:
            st.caption(
                f"보유종목 {len(holdings)}개 · "
                "국내/해외 평가액은 종목 합산으로 자동 반영됩니다."
            )
        else:
            st.caption("종목을 추가하면 계좌·상장 구분과 함께 평가액이 자동 합산됩니다.")

    if st.session_state.get(mode_key):
        with st.expander("종목별 보유 주식", expanded=True):
            if not is_supabase_configured():
                st.warning(
                    "Supabase가 설정되지 않았습니다. "
                    "보유종목은 이 브라우저 세션에만 유지됩니다."
                )
            elif not is_stock_holdings_table_available():
                st.warning(
                    "보유종목 저장을 위해 Supabase에 테이블 생성이 필요합니다. "
                    "위 안내 SQL을 실행하면 **보유종목 저장**이 가능합니다."
                )
            st.caption(
                "국내 매입가=원 · 해외 매입가=USD · 평가액=만원 · "
                "종목명을 올바른 주식/ETF명·티커로 고치고 **Enter** 또는 다른 칸 클릭 시 자동 조회"
            )

            if computed:
                del_col, _ = st.columns([1, 4])
                with del_col:
                    if st.button("선택 종목 삭제", key="delete_selected_holdings"):
                        removed = _delete_selected_holdings(holdings_key)
                        if removed:
                            st.toast(f"종목 {removed}개 삭제")
                        st.rerun()

                h_master_key = f"hsel_master_{local_id}"
                _update_holdings_master_state(holdings_key, h_master_key)
                header = st.columns([0.08, 1.5, 0.85, 0.85, 0.55, 0.75, 0.95, 0.95, 0.95, 0.65])
                header[0].checkbox(
                    "전체 선택",
                    key=h_master_key,
                    on_change=_make_holdings_master_handler(holdings_key, h_master_key),
                    label_visibility="collapsed",
                )
                for col, label in zip(
                    header[1:],
                    [
                        "종목명",
                        "티커",
                        "계좌",
                        "상장",
                        "수량",
                        "매입가",
                        "현재가",
                        "평가(만원)",
                        "수익률%",
                    ],
                ):
                    col.markdown(f"**{label}**")

                account_keys = list(STOCK_ACCOUNT_TYPES.keys())
                for item in computed:
                    hid = item["id"]
                    market = item.get("market", "domestic")
                    _init_holding_name_key(item)
                    row = st.columns([0.08, 1.5, 0.85, 0.85, 0.55, 0.75, 0.95, 0.95, 0.95, 0.65])
                    row[0].checkbox(
                        "선택",
                        key=f"hsel_{hid}",
                        label_visibility="collapsed",
                    )
                    row[1].text_input(
                        "종목명",
                        key=f"hn_{hid}",
                        label_visibility="collapsed",
                        placeholder="삼성전자, KODEX 200, AAPL",
                        on_change=_make_holding_name_handler(holdings_key, hid),
                    )
                    err = st.session_state.get(f"holdings_name_error_{hid}")
                    if err:
                        row[1].caption(f"⚠ {err}")
                    row[2].write(item.get("ticker", "") or "—")
                    current_account = item.get("account_type", "direct")
                    if current_account not in STOCK_ACCOUNT_TYPES:
                        current_account = "direct"
                    account_idx = account_keys.index(current_account)
                    row[3].selectbox(
                        "계좌",
                        account_keys,
                        index=account_idx,
                        format_func=lambda k: STOCK_ACCOUNT_TYPES[k],
                        key=f"ha_{hid}",
                        label_visibility="collapsed",
                    )
                    row[4].write(STOCK_MARKET_LABELS.get(market, market))
                    row[5].number_input(
                        "수량",
                        min_value=0.0,
                        value=float(item.get("quantity") or 0),
                        step=1.0,
                        key=f"hq_{hid}",
                        label_visibility="collapsed",
                    )
                    row[6].number_input(
                        "매입가",
                        min_value=0.0,
                        value=float(item.get("avg_price") or 0),
                        step=100.0 if market == "domestic" else 1.0,
                        key=f"hp_{hid}",
                        label_visibility="collapsed",
                    )
                    if item.get("error"):
                        row[7].caption("조회 실패")
                    elif item.get("quote_rate_limited"):
                        row[7].caption("시세 제한")
                    else:
                        row[7].write(_format_holding_price(item.get("current_price"), market))
                    row[8].write(f"{float(item.get('value_man') or 0):,.1f}")
                    ret = item.get("return_pct")
                    row[9].write(f"{ret:+.2f}%" if ret is not None else "N/A")

            st.markdown("**스크린샷 업로드 (자동 입력)**")
            st.caption(
                "스크린샷을 추가한 뒤 **목록에서 선택**하고 추출하세요. "
                "잘못 올린 이미지는 **선택 삭제**로 제거할 수 있습니다."
            )
            st.selectbox(
                "기본 계좌 유형",
                list(STOCK_ACCOUNT_TYPES.keys()),
                format_func=lambda k: STOCK_ACCOUNT_TYPES[k],
                key="ocr_default_account",
                help="스크린샷에 계좌명이 없을 때 적용",
            )
            _render_screenshot_queue(
                local_id,
                holdings_key,
                holdings,
                st.session_state.get("ocr_default_account", "direct"),
            )

            st.markdown("**종목 추가 (수동)**")
            with st.form("add_stock_holding_form", clear_on_submit=True):
                add_cols = st.columns(4)
                with add_cols[0]:
                    add_query = st.text_input(
                        "종목명/티커",
                        placeholder="삼성전자, KODEX 200, AAPL",
                    )
                with add_cols[1]:
                    add_account = st.selectbox(
                        "계좌 유형",
                        list(STOCK_ACCOUNT_TYPES.keys()),
                        format_func=lambda k: STOCK_ACCOUNT_TYPES[k],
                    )
                with add_cols[2]:
                    add_qty = st.number_input("보유 수량", min_value=0.0, step=1.0)
                with add_cols[3]:
                    add_avg = st.number_input("평균 매입가", min_value=0.0, step=100.0)
                if st.form_submit_button("종목 추가"):
                    try:
                        created = new_holding(add_query, add_qty, add_avg, add_account)
                        st.session_state[holdings_key] = holdings + [created]
                        _stash_holdings_quote_warnings()
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))

            action1, action2 = st.columns(2)
            with action1:
                if st.button("보유종목 저장", key="save_stock_holdings"):
                    try:
                        edited = _collect_holdings_edits(st.session_state[holdings_key])
                        st.session_state[holdings_key] = edited
                        if is_supabase_configured():
                            save_stock_holdings(
                                local_id,
                                [strip_holding_for_save(h) for h in edited],
                            )
                            st.success("보유종목이 저장되었습니다.")
                        else:
                            st.info("Supabase 미설정 — 세션에만 반영되었습니다.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"저장 실패: {exc}")
            with action2:
                if st.button("현재가 반영", key="refresh_stock_holdings"):
                    clear_quote_cache()
                    edited = _collect_holdings_edits(st.session_state[holdings_key])
                    st.session_state[holdings_key] = edited
                    st.rerun()

    c1, c2 = st.columns(2)
    with c1:
        st.metric(
            MONTHLY_ASSET_FIELDS["domestic_stocks"],
            f"{domestic_total:,.1f}",
        )
    with c2:
        st.metric(
            MONTHLY_ASSET_FIELDS["foreign_stocks"],
            f"{foreign_total:,.1f}",
        )
    if holdings:
        st.caption(
            "※ 국내/해외주식 평가액은 보유종목 합산값 (자동 계산) · "
            f"시세는 {roadmap_holdings.QUOTE_CACHE_TTL_SEC // 60}분 캐시, **현재가 반영**으로 갱신"
        )
    return domestic_total, foreign_total


def _render_loans_section(saved: dict, prefix: str = "loan") -> dict[str, dict]:
    st.caption("해당하는 대출만 「보유」 체크 후 잔액·금리·상환 정보를 입력하세요.")
    saved_loans = saved.get("loans") or {}
    loans: dict[str, dict] = {}
    for cat_key, cat in LOAN_CATEGORIES.items():
        st.markdown(f"**{cat['label']}**")
        for loan_key, label in cat["loans"].items():
            loans[loan_key] = _render_single_loan(
                loan_key,
                label,
                saved_loans.get(loan_key) or {},
                f"{prefix}_{cat_key}",
            )
    return loans


def _render_monthly_form(local_id: str) -> dict:
    st.markdown("#### 월별 업데이트 (매달 말 입력)")
    st.caption(f"{UNIT_NOTE} · **수입·지출**만 입력합니다. 자산·부채는 **「💰 자산」** 탭에서 관리하세요.")
    ym = _active_year_month()
    saved = get_monthly_snapshot(local_id, ym)

    st.markdown("##### 수입")
    income = _render_number_grid(MONTHLY_INCOME_FIELDS, saved, "mo_inc")

    st.markdown("##### 지출")
    expense = _render_number_grid(MONTHLY_EXPENSE_FIELDS, saved, "mo_exp")

    partial = {**income, **expense}
    preview = _merge_monthly_partial(local_id, ym, partial)
    metrics = compute_monthly_metrics(preview)

    m1, m2, m3 = st.columns(3)
    m1.metric("월 수입", metrics["total_income_fmt"], help="단위: 만원")
    m2.metric("월 지출", metrics["total_expense_fmt"], help="단위: 만원")
    m3.metric("저축률", metrics["savings_rate_fmt"], help="단위: %")

    if st.button("월별 데이터 저장", type="primary", key="save_monthly"):
        try:
            merged = _merge_monthly_partial(local_id, ym, partial)
            full_metrics = compute_monthly_metrics(merged)
            save_monthly_snapshot(
                local_id,
                ym,
                merged,
                full_metrics["net_assets_man"],
            )
            st.success(f"{ym} 월별(수입·지출) 데이터가 저장되었습니다.")
        except Exception as exc:
            st.error(f"저장 실패: {exc}")
    return preview


def _render_assets_form(local_id: str) -> dict:
    st.markdown("#### 자산·부채 (매달 말 업데이트)")
    st.caption(
        f"{UNIT_NOTE} · **종목별 입력**으로 국내/해외주식 평가액을 자동 계산할 수 있습니다. "
        "보유종목은 Supabase에 저장되어 매달 자동으로 불러옵니다."
    )
    ym = _active_year_month()
    saved = get_monthly_snapshot(local_id, ym)

    st.markdown("##### 자산")
    other_assets = _render_number_grid(_OTHER_MONTHLY_ASSET_FIELDS, saved, "ast")
    domestic_stocks, foreign_stocks = _render_stock_holdings_section(local_id, saved)
    assets = {
        **other_assets,
        "domestic_stocks": domestic_stocks,
        "foreign_stocks": foreign_stocks,
    }

    st.markdown("##### 부채 (대출 상세)")
    loans = _render_loans_section(saved, prefix="ast")

    partial = {**assets, "loans": loans}
    preview = _merge_monthly_partial(local_id, ym, partial)
    metrics = compute_monthly_metrics(preview)
    debt = metrics.get("debt_analysis") or {}

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("자산 합계", metrics["total_assets_fmt"], help="단위: 만원")
    m2.metric("부채 합계", metrics["total_debt_fmt"], help="단위: 만원")
    m3.metric("순자산", metrics["net_assets_fmt"], help="단위: 만원")
    m4.metric("저축률", metrics.get("savings_rate_fmt", "N/A"), help="수입·지출 입력 시")

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("DSR", metrics.get("dsr_fmt", "N/A"), help="총부채원리금상환비율")
    d2.metric("DSR 평가", metrics.get("dsr_status", "N/A"))
    d3.metric("부채/자산", metrics.get("debt_to_asset_fmt", "N/A"))
    d4.metric("변동금리 비중", metrics.get("variable_ratio_fmt", "N/A"))

    if debt.get("variable_rate_warning"):
        st.warning(debt["variable_rate_warning"])
    if debt.get("repayment_priority"):
        with st.expander("대출 상환 우선순위 (금리 높은 순)"):
            for line in debt["repayment_priority"]:
                st.write(line)

    if st.button("자산·부채 저장", type="primary", key="save_assets"):
        try:
            merged = _merge_monthly_partial(local_id, ym, partial)
            full_metrics = compute_monthly_metrics(merged)
            save_monthly_snapshot(
                local_id,
                ym,
                merged,
                full_metrics["net_assets_man"],
            )
            st.success(f"{ym} 자산·부채 데이터가 저장되었습니다.")
        except Exception as exc:
            st.error(f"저장 실패: {exc}")
    return preview


def _render_annual_form(local_id: str) -> dict:
    st.markdown("#### 연간 업데이트 (1년에 한 번)")
    st.caption(f"{UNIT_NOTE} · 비율(%)·기간(년) 항목은 해당 단위로 입력")
    year = int(st.number_input("대상 연도 (년)", 2020, 2035, date.today().year, 1, key="an_year"))
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
    t1.metric("연금/IRP 절세 잔여", tax["combined_pension_room_fmt"], help="단위: 만원")
    t2.metric("ISA 납입 잔여", tax["isa_room_fmt"], help="단위: 만원")
    t3.metric("금융소득", tax["financial_income_fmt"], help="단위: 만원")
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


def _render_section_fields(section: dict, fields: list[tuple[str, str]], warn_keys: set[str] | None = None) -> None:
    warn_keys = warn_keys or set()
    for key, title in fields:
        val = section.get(key)
        if not val:
            continue
        if isinstance(val, list):
            if not val:
                continue
            st.markdown(f"**{title}**")
            for item in val:
                st.markdown(f"- {item}")
            continue
        text = str(val).strip()
        if not text or text == "해당 없음":
            continue
        st.markdown(f"**{title}**")
        if key in warn_keys:
            st.warning(text)
        else:
            st.write(text)


def _render_ai_results(roadmap: dict) -> None:
    st.success(roadmap.get("summary", ""))
    if roadmap.get("macro_note"):
        st.info(f"**거시환경** — {roadmap['macro_note']}")

    s1 = roadmap.get("section_1_diagnosis") or {}
    with st.expander("1️⃣ 현재 재무 상태 진단", expanded=True):
        _render_section_fields(
            s1,
            [
                ("net_worth_analysis", "순자산 분석 (또래 평균 대비)"),
                ("savings_rate_evaluation", "저축률 평가"),
                ("debt_health", "부채 건전성 (DSR·부채비율)"),
                ("emergency_fund", "비상금 충분 여부"),
                ("asset_allocation_balance", "자산 배분 균형"),
            ],
        )

    s2 = roadmap.get("section_2_tax") or {}
    with st.expander("2️⃣ 절세 분석", expanded=True):
        _render_section_fields(
            s2,
            [
                ("irp_pension_tax_saving", "IRP·연금저축 추가 납입 절세"),
                ("isa_strategy", "ISA 활용 전략"),
                ("financial_income_tax_warning", "금융소득종합과세 주의"),
                ("health_insurance_savings", "건강보험료 절감"),
                ("comprehensive_income_tax_strategy", "종합소득세 절세 전략"),
            ],
            warn_keys={"financial_income_tax_warning"},
        )

    s3 = roadmap.get("section_3_goals") or {}
    with st.expander("3️⃣ 목표별 달성 시뮬레이션", expanded=False):
        _render_section_fields(
            s3,
            [
                ("home_purchase", "내집마련 달성 시기"),
                ("retirement", "노후준비 (은퇴 시점 자산·월 수령액)"),
                ("fire_age", "FIRE 가능 나이"),
                ("children_education", "자녀교육비 준비 현황"),
            ],
        )

    s4 = roadmap.get("section_4_risks") or {}
    with st.expander("4️⃣ 리스크 분석", expanded=False):
        _render_section_fields(
            s4,
            [
                ("variable_rate_scenario", "변동금리 금리 인상 시나리오"),
                ("income_disruption", "소득 중단 시 버틸 기간"),
                ("concentration_risk", "자산 쏠림 리스크"),
                ("insurance_gap", "보험 공백 리스크"),
            ],
            warn_keys={"variable_rate_scenario", "concentration_risk", "insurance_gap"},
        )

    s5 = roadmap.get("section_5_action_plan") or {}
    with st.expander("5️⃣ 실행 가이드 (월별 액션플랜)", expanded=False):
        _render_section_fields(
            s5,
            [
                ("this_month", "이번 달 당장 해야 할 것"),
                ("within_3_months", "3개월 안에 할 것"),
                ("within_1_year", "1년 안에 할 것"),
                ("mid_long_term", "중장기 로드맵"),
            ],
        )

    s6 = roadmap.get("section_6_monthly_report") or {}
    with st.expander("6️⃣ 월별 성과 리포트", expanded=False):
        _render_section_fields(
            s6,
            [
                ("net_worth_change", "지난달 대비 순자산 변화"),
                ("savings_rate_trend", "저축률 추이"),
                ("goal_achievement", "목표 달성률"),
                ("strengths", "잘한 점"),
                ("improvements", "개선할 점"),
            ],
        )


def _chat_session_key(local_id: str) -> str:
    return f"roadmap_chat_{local_id}"


def _render_ai_chat(local_id: str, context: dict, macro: dict) -> None:
    st.divider()
    st.markdown("#### 💬 AI 재무 상담")
    st.caption("위 분석을 바탕으로 내 재무 상황에 맞는 질문을 해보세요.")

    chat_key = _chat_session_key(local_id)
    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    col_refresh, _ = st.columns([1, 4])
    with col_refresh:
        if st.button("대화 새로고침", key=f"chat_reset_{local_id}"):
            st.session_state[chat_key] = []
            st.rerun()

    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    ex_cols = st.columns(3)
    short_labels = ("IRP 추가납입", "성과급 활용", "전세 vs 매매")
    for col, question, label in zip(ex_cols, CHAT_EXAMPLE_QUESTIONS, short_labels):
        with col:
            if st.button(label, key=f"chat_ex_{label}_{local_id[:8]}", use_container_width=True):
                st.session_state[f"chat_pending_{local_id}"] = question

    pending = st.session_state.pop(f"chat_pending_{local_id}", None)
    user_input = st.chat_input("재무 관련 질문을 입력하세요", key=f"chat_input_{local_id}")
    prompt = pending or user_input

    if prompt:
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        try:
            with st.spinner("AI가 답변을 작성하는 중..."):
                reply = chat_financial_advisor(
                    context,
                    macro,
                    st.session_state[chat_key][:-1],
                    prompt,
                )
            st.session_state[chat_key].append({"role": "assistant", "content": reply})
        except Exception as exc:
            st.session_state[chat_key].pop()
            st.error(f"상담 실패: {exc}")
        st.rerun()


def render_financial_roadmap_section(indicator_snapshot: dict) -> None:
    st.markdown("### 🗺️ 재테크 로드맵")
    st.caption(
        "고정·월별·자산·연간·변동 정보를 Supabase에 누적 저장하고 Claude가 맞춤 분석합니다. "
        "투자 참고용이며 투자 권유가 아닙니다. "
        f"{UNIT_NOTE}"
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
        ak = anthropic_config_status()
        st.warning(
            "AI 분석을 사용하려면 Anthropic API Key가 필요합니다. "
            "로컬: `.env` · Cloud: Streamlit **Settings → Secrets**에 "
            "`ANTHROPIC_API_KEY`를 설정하세요."
        )
        st.caption(
            f"진단: env 파일={ak['env_file_exists']} · "
            f"키 입력={ak['raw_set']} · 유효={ak['key_valid']} · "
            f"미리보기={ak['preview']}"
        )

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

    if api_key:
        st.caption(f"API 키: `{api_key_preview(api_key)}` · 데이터 ID: `{local_id[:8]}…`")
    else:
        st.caption(f"데이터 ID: `{local_id[:8]}…`")

    st.text_input(
        "대상 년월 (YYYY-MM) — 월별·자산 탭 공통",
        _default_year_month(),
        key="mo_ym",
    )

    tab_fixed, tab_monthly, tab_assets, tab_annual, tab_variable, tab_analysis = st.tabs(
        ["📌 고정 정보", "📅 월별", "💰 자산", "📆 연간", "🔄 변동", "🤖 AI 분석"]
    )

    fixed = get_fixed_profile(local_id)
    monthly: dict = {}
    assets_data: dict = {}
    annual: dict = {}

    with tab_fixed:
        fixed = _render_fixed_form(local_id)

    with tab_monthly:
        monthly = _render_monthly_form(local_id)

    with tab_assets:
        assets_data = _render_assets_form(local_id)

    with tab_annual:
        annual = _render_annual_form(local_id)

    with tab_variable:
        _render_variable_form(local_id)

    with tab_analysis:
        st.markdown("#### AI 종합 분석")
        if not fixed:
            st.info("먼저 「고정 정보」 탭에서 프로필을 저장하세요.")
        if not monthly.get("net_income"):
            st.info("「월별」 탭에서 이번 달 수입·지출을 입력·저장하세요.")
        if not assets_data.get("cash_deposit") and not assets_data.get("domestic_stocks"):
            st.info("「자산」 탭에서 자산·부채를 입력·저장하세요.")

        ym = _active_year_month()
        snapshot = get_monthly_snapshot(local_id, ym) or {}
        merged = {**snapshot, **monthly, **assets_data}
        metrics = compute_monthly_metrics(merged) if merged else {}
        if metrics:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("순자산", metrics.get("net_assets_fmt", "N/A"), help="단위: 만원")
            c2.metric("저축률", metrics.get("savings_rate_fmt", "N/A"), help="단위: %")
            c3.metric("DSR", metrics.get("dsr_fmt", "N/A"), help="원리금/소득")
            c4.metric("부채/자산", metrics.get("debt_to_asset_fmt", "N/A"))
            debt = metrics.get("debt_analysis") or {}
            if debt.get("variable_rate_warning"):
                st.warning(debt["variable_rate_warning"])
            _render_history_charts(local_id, metrics)

        if not api_key:
            st.error("Anthropic API Key가 설정되지 않아 AI 분석을 실행할 수 없습니다.")
        elif st.button("AI 종합 분석 실행", type="primary", use_container_width=True, key="run_ai"):
            macro = {"indicators": indicator_snapshot}
            try:
                monthly_history = list_monthly_history(local_id)
                annual_history = list_annual_history(local_id)
                variable_events = list_variable_events(local_id)
                fixed_data = get_fixed_profile(local_id) or fixed
                ym = _active_year_month()
                monthly_data = get_monthly_snapshot(local_id, ym) or {**monthly, **assets_data}
                annual_data = get_annual_snapshot(local_id, date.today().year) or annual
                holdings = get_stock_holdings(local_id) or []

                context = build_analysis_context(
                    fixed_data,
                    monthly_data,
                    annual_data,
                    annual_history,
                    variable_events,
                    monthly_history,
                    holdings=holdings,
                )

                with st.spinner("거시지표 반영 중..."):
                    fear_greed = _load_fear_greed()
                    sectors = _load_sector_returns()
                    macro = build_roadmap_macro(indicator_snapshot, fear_greed, sectors)

                with st.spinner("Claude가 6가지 재무 분석을 작성하는 중..."):
                    roadmap = generate_comprehensive_roadmap(context, macro)
                st.session_state["roadmap_ai_result"] = roadmap
                st.session_state[f"roadmap_ai_context_{local_id}"] = context
                st.session_state[f"roadmap_ai_macro_{local_id}"] = macro
            except Exception as exc:
                st.error(f"AI 분석 실패: {exc}")

        if st.session_state.get("roadmap_ai_result"):
            _render_ai_results(st.session_state["roadmap_ai_result"])
            ctx = st.session_state.get(f"roadmap_ai_context_{local_id}")
            mac = st.session_state.get(f"roadmap_ai_macro_{local_id}")
            if (not ctx or not mac) and api_key:
                try:
                    ym = _active_year_month()
                    monthly_data = get_monthly_snapshot(local_id, ym) or {**monthly, **assets_data}
                    ctx = build_analysis_context(
                        get_fixed_profile(local_id) or fixed or {},
                        monthly_data,
                        get_annual_snapshot(local_id, date.today().year) or annual or {},
                        list_annual_history(local_id),
                        list_variable_events(local_id),
                        list_monthly_history(local_id),
                        holdings=get_stock_holdings(local_id) or [],
                    )
                    fear_greed = _load_fear_greed()
                    sectors = _load_sector_returns()
                    mac = build_roadmap_macro(indicator_snapshot, fear_greed, sectors)
                except Exception:
                    ctx = None
                    mac = None
            if ctx and mac and api_key:
                _render_ai_chat(local_id, ctx, mac)
