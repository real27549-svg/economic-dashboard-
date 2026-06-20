"""미국·한국 경제 지표 인터랙티브 웹 대시보드."""

import importlib
import json
from datetime import datetime, timezone

import plotly.graph_objects as go
import streamlit as st

import ai_outlook
import data
import market_extras
import stock_search

importlib.reload(data)
importlib.reload(ai_outlook)
importlib.reload(stock_search)
importlib.reload(market_extras)
from ai_outlook import analyze_market, analyze_stock_signal, build_stock_context, get_api_key
from data import DASHBOARD_SECTIONS, get_tooltip, load_indicator, recent_window
from market_extras import fetch_fear_greed_index, fetch_sector_week_returns
from stock_search import fetch_stock_profile, resolve_ticker

st.set_page_config(
    page_title="경제 지표 대시보드",
    page_icon="📊",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container { padding-top: 1rem; }
    div[data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 0.45rem;
        padding: 0.3rem 0.45rem;
        min-height: 0;
    }
    div[data-testid="stMetric"] label {
        font-size: 0.62rem !important;
        line-height: 1.15 !important;
        white-space: normal !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {
        font-size: 0.88rem !important;
        font-weight: 600 !important;
        line-height: 1.2 !important;
    }
    div[data-testid="stMetric"] [data-testid="stMetricDelta"] {
        font-size: 0.55rem !important;
        line-height: 1.1 !important;
    }
    .section-tag {
        font-size: 0.68rem;
        font-weight: 700;
        color: #475569;
        margin: 0.35rem 0 0.1rem 0;
        letter-spacing: -0.01em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

CARDS_PER_ROW = 5
DATA_CACHE_VERSION = 5


@st.cache_data(ttl=300, show_spinner=False)
def load_cached_indicator(config_key: str, _version: int = DATA_CACHE_VERSION) -> tuple:
    config = next(
        item
        for section in DASHBOARD_SECTIONS
        for item in section["items"]
        if item["key"] == config_key
    )
    return load_indicator(config)


def build_line_chart(df, value_col: str, title: str, ylabel: str, color: str) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=df["date"],
            y=df[value_col],
            mode="lines",
            line=dict(color=color, width=2),
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=title, x=0, font=dict(size=18)),
        xaxis_title="날짜",
        yaxis_title=ylabel,
        height=300,
        margin=dict(l=40, r=20, t=50, b=40),
        hovermode="x unified",
        template="plotly_white",
        dragmode="zoom",
    )
    fig.update_xaxes(rangeslider_visible=False, showgrid=True, gridcolor="#e2e8f0")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0")
    return fig


def build_yield_spread_chart(df, value_col: str, title: str, ylabel: str) -> go.Figure:
    values = df[value_col]
    pos = values.where(values >= 0)
    neg = values.where(values < 0)

    fig = go.Figure()
    fig.add_hline(y=0, line_dash="dash", line_color="#94a3b8", line_width=1)
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=pos,
            mode="lines",
            line=dict(color="#2563eb", width=2),
            fill="tozeroy",
            fillcolor="rgba(37, 99, 235, 0.12)",
            name="정상 (양수)",
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:+.2f}%p<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=neg,
            mode="lines",
            line=dict(color="#dc2626", width=2.5),
            fill="tozeroy",
            fillcolor="rgba(220, 38, 38, 0.35)",
            name="역전 (음수)",
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:+.2f}%p<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text=title, x=0, font=dict(size=18)),
        xaxis_title="날짜",
        yaxis_title=ylabel,
        height=300,
        margin=dict(l=40, r=20, t=50, b=40),
        hovermode="x unified",
        template="plotly_white",
        dragmode="zoom",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#e2e8f0")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0", ticksuffix="%p")
    return fig


def build_chart(config: dict, df, years: int) -> go.Figure:
    title = f"{config['title']} (최근 {years}년)"
    if config.get("chart_type") == "yield_spread":
        return build_yield_spread_chart(df, config["value_col"], title, config["ylabel"])
    return build_line_chart(
        df, config["value_col"], title, config["ylabel"], config["color"]
    )


def render_metric_cards(metrics: list[dict], per_row: int = CARDS_PER_ROW) -> None:
    for start in range(0, len(metrics), per_row):
        row = metrics[start : start + per_row]
        cols = st.columns(per_row)
        for col, metric in zip(cols, row):
            col.metric(
                label=f"{metric['label']} ℹ️",
                value=metric["value"],
                delta=metric["date"],
                help=metric["tooltip"],
            )


def render_all_cards(sections_data: list[dict]) -> None:
    with st.container(border=True):
        for section_data in sections_data:
            st.markdown(
                f'<p class="section-tag">{section_data["title"]}</p>',
                unsafe_allow_html=True,
            )
            render_metric_cards(section_data["metrics"])


def render_all_charts(sections_data: list[dict]) -> None:
    for section_data in sections_data:
        st.subheader(section_data["title"])
        for chart in section_data["charts"]:
            st.plotly_chart(chart, use_container_width=True)


@st.cache_data(ttl=300, show_spinner=False)
def load_fear_greed() -> dict:
    return fetch_fear_greed_index()


@st.cache_data(ttl=300, show_spinner=False)
def load_sector_returns() -> list[dict]:
    return fetch_sector_week_returns()


def build_fear_greed_gauge(fng: dict) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=fng["score"],
            number={"suffix": " / 100", "font": {"size": 36}},
            title={
                "text": f"CNN Fear & Greed Index<br><span style='font-size:14px'>{fng['label']}</span>",
                "font": {"size": 18},
            },
            gauge={
                "axis": {"range": [0, 100], "tickmode": "linear", "tick0": 0, "dtick": 10},
                "bar": {"color": fng["color"], "thickness": 0.28},
                "bgcolor": "white",
                "borderwidth": 0,
                "steps": [
                    {"range": [0, 25], "color": "#fecaca"},
                    {"range": [25, 45], "color": "#fed7aa"},
                    {"range": [45, 55], "color": "#fef08a"},
                    {"range": [55, 75], "color": "#d9f99d"},
                    {"range": [75, 100], "color": "#bbf7d0"},
                ],
            },
        )
    )
    fig.update_layout(
        height=340,
        margin=dict(t=70, b=10, l=30, r=30),
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def build_sector_heatmap(sectors_data: list[dict]) -> go.Figure:
    sorted_data = sorted(sectors_data, key=lambda item: item["return_pct"])
    sectors = [item["sector"] for item in sorted_data]
    returns = [item["return_pct"] for item in sorted_data]
    max_abs = max(max(abs(min(returns)), abs(max(returns))), 1.0)

    fig = go.Figure(
        data=go.Heatmap(
            z=[returns],
            x=sectors,
            y=["1주 수익률"],
            text=[[f"{value:+.2f}%" for value in returns]],
            texttemplate="%{text}",
            textfont={"size": 11, "color": "#0f172a"},
            colorscale=[
                [0.0, "#dc2626"],
                [0.5, "#f8fafc"],
                [1.0, "#16a34a"],
            ],
            zmid=0,
            zmin=-max_abs,
            zmax=max_abs,
            showscale=True,
            colorbar={"title": "수익률(%)"},
            hovertemplate="%{x}: %{z:+.2f}%<extra></extra>",
        )
    )
    fig.update_layout(
        title=dict(text="S&P 500 섹터별 1주 수익률", x=0, font=dict(size=18)),
        height=340,
        margin=dict(t=50, b=10, l=20, r=20),
    )
    return fig


def render_market_extras_section() -> None:
    st.divider()
    st.markdown("### 🌡️ 공포·탐욕 & 섹터")
    try:
        with st.spinner("CNN Fear & Greed · 섹터 데이터 불러오는 중..."):
            fng = load_fear_greed()
            sectors = load_sector_returns()
    except Exception as exc:
        st.error(f"시장 심리/섹터 데이터 로드 실패: {exc}")
        return

    col_gauge, col_heat = st.columns(2)
    with col_gauge:
        st.plotly_chart(build_fear_greed_gauge(fng), use_container_width=True)
        prev = fng.get("previous_close")
        week = fng.get("previous_1_week")
        if prev is not None and week is not None:
            st.caption(
                f"전일 {float(prev):.1f} · 1주 전 {float(week):.1f} · "
                f"0-25 극도공포 | 26-45 공포 | 46-55 중립 | 56-75 탐욕 | 76-100 극도탐욕"
            )
    with col_heat:
        st.plotly_chart(build_sector_heatmap(sectors), use_container_width=True)
        st.caption("SPDR 섹터 ETF 기준 최근 약 1주(5거래일) 수익률 · 초록=상승, 빨강=하락")


def resolve_api_key() -> str | None:
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY")
        if key:
            return key
    except (AttributeError, FileNotFoundError, KeyError):
        pass
    return get_api_key()


@st.cache_data(ttl=3600, show_spinner=False)
def get_us_outlook(snapshot_json: str, api_key: str) -> dict:
    return analyze_market("us", json.loads(snapshot_json), api_key)


@st.cache_data(ttl=3600, show_spinner=False)
def get_kr_outlook(snapshot_json: str, api_key: str) -> dict:
    return analyze_market("kr", json.loads(snapshot_json), api_key)


def render_outlook_content(result: dict) -> None:
    st.markdown("**현재 시장 상황 요약**")
    st.info(result["summary"])
    st.markdown("**주식시장 전망**")
    st.success(result["outlook"])
    st.markdown("**주의해야 할 점**")
    st.warning(result["caution"])


@st.cache_data(ttl=300, show_spinner=False)
def load_stock_profile(query: str) -> dict:
    return fetch_stock_profile(query)


def build_stock_chart(chart_df, name: str, symbol: str, currency: str) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=chart_df["date"],
            y=chart_df["close"],
            mode="lines",
            line=dict(color="#2563eb", width=2),
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:,.2f}<extra></extra>",
        )
    )
    ylabel = "주가 (원)" if currency == "KRW" else f"주가 ({currency})"
    fig.update_layout(
        title=dict(text=f"{name} ({symbol}) — 최근 1년", x=0, font=dict(size=18)),
        xaxis_title="날짜",
        yaxis_title=ylabel,
        height=360,
        margin=dict(l=40, r=20, t=50, b=40),
        hovermode="x unified",
        template="plotly_white",
        dragmode="zoom",
    )
    fig.update_xaxes(showgrid=True, gridcolor="#e2e8f0")
    fig.update_yaxes(showgrid=True, gridcolor="#e2e8f0")
    return fig


@st.cache_data(ttl=3600, show_spinner=False)
def get_stock_signal(stock_json: str, snapshot_json: str, api_key: str) -> dict:
    stock = json.loads(stock_json)
    snapshot = json.loads(snapshot_json)
    return analyze_stock_signal(stock, snapshot, api_key)


def render_stock_signal(signal: dict) -> None:
    label = signal["signal"]
    reason = signal["reason"]
    if label == "매수 고려":
        st.success(f"**🟢 AI 신호: 매수 고려**\n\n{reason}")
    elif label == "매도 고려":
        st.error(f"**🔴 AI 신호: 매도 고려**\n\n{reason}")
    else:
        st.warning(f"**🟡 AI 신호: 중립**\n\n{reason}")
    st.caption("AI 참고 의견이며 투자 권유가 아닙니다.")


def render_stock_search_section(indicator_snapshot: dict) -> None:
    st.divider()
    st.markdown("### 🔍 종목 검색")
    st.caption("티커(AAPL, 005930.KS) 또는 한글 회사명(삼성전자, 애플)으로 검색")

    col_input, col_btn = st.columns([4, 1])
    with col_input:
        ticker = st.text_input(
            "티커 심볼",
            placeholder="삼성전자, 애플, AAPL, 005930.KS",
            label_visibility="collapsed",
            key="stock_ticker_input",
        )
    with col_btn:
        search = st.button("검색", type="primary", use_container_width=True, key="stock_search_btn")

    if not search or not ticker.strip():
        return

    try:
        resolved, matched = resolve_ticker(ticker)
        with st.spinner(f"{ticker.strip()} → {resolved} 조회 중..."):
            profile = load_stock_profile(ticker.strip())
    except Exception as exc:
        st.error(f"종목 조회 실패: {exc}")
        return

    if profile.get("matched_name") and profile["matched_name"].lower() != profile["symbol"].lower():
        st.info(f"「{profile['query']}」→ **{profile['symbol']}**")

    st.subheader(f"{profile['name']} ({profile['symbol']})")
    st.caption(f"기준: {profile['as_of']}")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("현재가", profile["price_fmt"])
    m2.metric("52주 최고", profile["high_52_fmt"])
    m3.metric("52주 최저", profile["low_52_fmt"])
    m4.metric("PER", profile["per_fmt"])
    m5.metric("시가총액", profile["market_cap_fmt"])

    api_key = resolve_api_key()
    if api_key:
        try:
            stock_ctx = build_stock_context(profile)
            stock_json = json.dumps(stock_ctx, ensure_ascii=False, sort_keys=True)
            snapshot_json = json.dumps(indicator_snapshot, ensure_ascii=False, sort_keys=True)
            with st.spinner("Claude가 AI 매매 신호 분석 중..."):
                signal = get_stock_signal(stock_json, snapshot_json, api_key)
            render_stock_signal(signal)
        except Exception as exc:
            st.warning(f"AI 매매 신호 분석 실패: {exc}")
    else:
        st.info("AI 매매 신호를 보려면 `.env`에 Anthropic API Key를 설정하세요.")

    st.plotly_chart(
        build_stock_chart(
            profile["chart_df"],
            profile["name"],
            profile["symbol"],
            profile["currency"],
        ),
        use_container_width=True,
    )

    st.markdown("**최근 뉴스**")
    if not profile["news"]:
        st.info("최근 뉴스가 없습니다.")
        return

    for item in profile["news"]:
        pub = item["published"][:10] if item["published"] else ""
        publisher = f" · {item['publisher']}" if item["publisher"] else ""
        if item["url"]:
            st.markdown(f"- [{item['title']}]({item['url']}) `{pub}{publisher}`")
        else:
            st.markdown(f"- {item['title']} `{pub}{publisher}`")


def render_ai_outlook_section(indicator_snapshot: dict) -> None:
    st.divider()
    st.markdown("### 🤖 AI 시장 전망")
    st.caption("Claude가 현재 지표를 바탕으로 자동 분석합니다. 투자 참고용이며 투자 권유가 아닙니다.")

    api_key = resolve_api_key()
    if not api_key:
        st.warning(
            "`.env` 파일에 API Key를 저장해 주세요. "
            "프로젝트 폴더의 `.env.example`을 `.env`로 복사한 뒤 키를 입력하면 자동으로 불러옵니다."
        )
        return

    snapshot_json = json.dumps(indicator_snapshot, ensure_ascii=False, sort_keys=True)
    tab_us, tab_kr = st.tabs(["미국 시장 (미장)", "한국 시장 (국장)"])

    with tab_us:
        if st.button("미장 분석 새로고침", key="refresh_us"):
            get_us_outlook.clear()
        try:
            with st.spinner("Claude가 미국 시장을 분석하는 중..."):
                us_result = get_us_outlook(snapshot_json, api_key)
            render_outlook_content(us_result)
        except Exception as exc:
            st.error(f"AI 분석 실패: {exc}")

    with tab_kr:
        if st.button("국장 분석 새로고침", key="refresh_kr"):
            get_kr_outlook.clear()
        try:
            with st.spinner("Claude가 한국 시장을 분석하는 중..."):
                kr_result = get_kr_outlook(snapshot_json, api_key)
            render_outlook_content(kr_result)
        except Exception as exc:
            st.error(f"AI 분석 실패: {exc}")


st.title("경제 지표 대시보드")
st.caption(
    "FRED · yfinance · 드래그 확대 · 장단기 금리차 역전=빨간색 · ℹ️/? 툴팁"
)

col_refresh, col_years, col_info = st.columns([1, 2, 3])
with col_refresh:
    if st.button("새로고침", type="primary", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
with col_years:
    years = st.slider("표시 기간 (년)", min_value=1, max_value=30, value=10)
with col_info:
    st.write(
        f"업데이트: {datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')}"
    )

try:
    with st.spinner("데이터 불러오는 중..."):
        sections_data = []
        indicator_snapshot = {}
        for section in DASHBOARD_SECTIONS:
            section_metrics = []
            section_charts = []
            for config in section["items"]:
                prepared, latest_date, latest_value = load_cached_indicator(config["key"])
                window = recent_window(prepared, years=years)
                formatted_value = config["format"].format(latest_value)
                date_str = latest_date.strftime("%Y-%m-%d")
                section_metrics.append(
                    {
                        "label": config["label"],
                        "value": formatted_value,
                        "date": date_str,
                        "tooltip": get_tooltip(config["key"], config),
                    }
                )
                indicator_snapshot[config["key"]] = {
                    "label": config["label"],
                    "value": formatted_value,
                    "date": date_str,
                }
                section_charts.append(build_chart(config, window, years))
            sections_data.append(
                {
                    "title": section["title"],
                    "metrics": section_metrics,
                    "charts": section_charts,
                }
            )

except Exception as exc:
    st.error(f"데이터를 불러오지 못했습니다: {exc}")
    st.stop()

render_all_cards(sections_data)

render_market_extras_section()

st.divider()
st.markdown("### 📈 그래프")
render_all_charts(sections_data)

render_stock_search_section(indicator_snapshot)

render_ai_outlook_section(indicator_snapshot)

st.caption(
    "데이터: [FRED](https://fred.stlouisfed.org/) · 코스피/금: yfinance · AI: Claude · 5분 캐시"
)
