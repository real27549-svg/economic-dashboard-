"""경제 지표 데이터 조회."""

import io
from datetime import datetime, timedelta

import pandas as pd
import requests

FRED_CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="

SERIES_TOOLTIPS = {
    "FEDFUNDS": "금리 오르면 성장주 하락, 채권 하락 / 금리 내리면 성장주 상승, 채권 상승",
    "CPIAUCSL": "물가 오르면 금리인상 우려로 주식 하락 / 물가 내리면 금리인하 기대로 주식 상승",
    "UNRATE": "실업률 오르면 경기침체 우려로 주식 하락",
    "PPIACO": "생산자물가 오르면 기업 마진 축소로 주식 하락",
    "DGS10": "오르면 성장주 밸류에이션 하락 압력",
    "DGS2": "단기 금리, 연준 통화정책 변화에 민감",
    "T10Y2Y": "음수(역전) 구간은 경기침체 신호로 해석",
    "PAYEMS": "고용 증가는 경기 확장 신호, 고용 감소는 경기 둔화 신호",
    "DTWEXBGS": "달러 강세면 신흥국 및 원자재 하락, 수출주 불리",
    "VIXCLS": "VIX 상승은 시장 공포 확대, 주식 변동성 증가 신호",
    "NASDAQCOM": "기술주 전반적 시장 심리 반영",
    "GOLD": "금값 상승은 불확실성·인플레 헷지 수요 반영",
    "DCOILWTICO": "유가 상승은 인플레 압력, 유가 급등은 경기 둔화 우려",
    "KOSPI": "한국 주식시장 전반의 투자 심리 반영",
    "DEXKOUS": "원화 약세(수치 상승)는 수출주에 유리, 수입물가 부담 증가",
}


def get_tooltip(key: str, config: dict | None = None) -> str:
    if config and config.get("tooltip"):
        return config["tooltip"]
    return SERIES_TOOLTIPS.get(key, "")


def _base_config(**kwargs) -> dict:
    defaults = {
        "source": "fred",
        "resample_monthly": False,
        "transform": None,
        "chart_type": "line",
        "ticker": None,
    }
    defaults.update(kwargs)
    return defaults


DASHBOARD_SECTIONS = [
    {
        "title": "미국 거시지표",
        "items": [
            _base_config(
                key="FEDFUNDS",
                series_id="FEDFUNDS",
                value_col="rate",
                label="연방기금금리",
                title="미국 연방기금금리",
                ylabel="금리 (%)",
                format="{:.2f}%",
                color="#2563eb",
            ),
            _base_config(
                key="CPIAUCSL",
                series_id="CPIAUCSL",
                value_col="cpi",
                label="소비자물가지수 (CPI)",
                title="미국 소비자물가지수 (CPI)",
                ylabel="지수 (1982-84=100)",
                format="{:.2f}",
                color="#dc2626",
            ),
            _base_config(
                key="UNRATE",
                series_id="UNRATE",
                value_col="unemployment",
                label="실업률",
                title="미국 실업률",
                ylabel="실업률 (%)",
                format="{:.1f}%",
                color="#9333ea",
            ),
            _base_config(
                key="PPIACO",
                series_id="PPIACO",
                value_col="ppi",
                label="생산자물가지수 (PPI)",
                title="미국 생산자물가지수 (PPI)",
                ylabel="지수 (1982=100)",
                format="{:.2f}",
                color="#ea580c",
            ),
            _base_config(
                key="DGS10",
                series_id="DGS10",
                value_col="treasury10y",
                label="10년물 국채금리",
                title="10년물 국채금리",
                ylabel="금리 (%)",
                format="{:.2f}%",
                color="#4f46e5",
            ),
            _base_config(
                key="DGS2",
                series_id="DGS2",
                value_col="treasury2y",
                label="2년물 국채금리",
                title="2년물 국채금리",
                ylabel="금리 (%)",
                format="{:.2f}%",
                color="#7c3aed",
            ),
            _base_config(
                key="T10Y2Y",
                series_id="T10Y2Y",
                value_col="spread",
                label="장단기 금리차 (10Y-2Y)",
                title="장단기 금리차 (10년물 - 2년물)",
                ylabel="금리차 (%p)",
                format="{:+.2f}%p",
                chart_type="yield_spread",
                color="#2563eb",
            ),
            _base_config(
                key="PAYEMS",
                series_id="PAYEMS",
                value_col="nfp",
                label="비농업 고용 (NFP)",
                title="비농업 고용 증감 (NFP)",
                ylabel="증감 (천 명)",
                format="{:+,.0f}K",
                transform="monthly_change",
                color="#0d9488",
            ),
            _base_config(
                key="DTWEXBGS",
                series_id="DTWEXBGS",
                value_col="dxy",
                label="달러인덱스 (DXY)",
                title="달러인덱스 (DXY)",
                ylabel="지수",
                format="{:.2f}",
                color="#0891b2",
            ),
        ],
    },
    {
        "title": "시장심리",
        "items": [
            _base_config(
                key="VIXCLS",
                source="yfinance",
                ticker="^VIX",
                series_id="VIXCLS",
                value_col="vix",
                label="VIX 공포지수",
                title="VIX 공포지수",
                ylabel="지수",
                format="{:.2f}",
                color="#b91c1c",
            ),
            _base_config(
                key="NASDAQCOM",
                source="yfinance",
                ticker="^IXIC",
                series_id="NASDAQCOM",
                value_col="nasdaq",
                label="나스닥 종합지수",
                title="나스닥 종합지수",
                ylabel="지수",
                format="{:,.2f}",
                color="#16a34a",
            ),
        ],
    },
    {
        "title": "원자재",
        "items": [
            _base_config(
                key="GOLD",
                source="yfinance",
                ticker="GC=F",
                series_id="GOLD",
                value_col="gold",
                label="금 가격 (Gold)",
                title="금 가격 (Gold)",
                ylabel="USD/온스",
                format="${:,.2f}",
                color="#ca8a04",
            ),
            _base_config(
                key="DCOILWTICO",
                source="yfinance",
                ticker="CL=F",
                series_id="DCOILWTICO",
                value_col="wti",
                label="WTI 원유",
                title="WTI 원유 가격",
                ylabel="USD/배럴",
                format="${:.2f}",
                color="#1f2937",
            ),
        ],
    },
    {
        "title": "한국 지표",
        "items": [
            _base_config(
                key="KOSPI",
                source="yfinance",
                ticker="^KS11",
                series_id="KOSPI",
                value_col="kospi",
                label="코스피 지수",
                title="코스피 지수",
                ylabel="지수",
                format="{:,.2f}",
                color="#e11d48",
            ),
            _base_config(
                key="DEXKOUS",
                source="yfinance",
                ticker="KRW=X",
                series_id="DEXKOUS",
                value_col="usdkrw",
                label="원달러 환율",
                title="원달러 환율 (USD/KRW)",
                ylabel="원/달러",
                format="{:,.2f}원",
                color="#0369a1",
            ),
        ],
    },
]


def get_all_series() -> list[dict]:
    return [item for section in DASHBOARD_SECTIONS for item in section["items"]]


SERIES_CONFIGS = get_all_series()


def fetch_fred_series(series_id: str, value_col: str) -> pd.DataFrame:
    url = f"{FRED_CSV_BASE}{series_id}"
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    df = pd.read_csv(io.StringIO(response.text))
    df.columns = ["date", value_col]
    df["date"] = pd.to_datetime(df["date"])
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    return df.dropna().sort_values("date")


def _extract_close_series(hist: pd.DataFrame) -> pd.Series:
    if isinstance(hist.columns, pd.MultiIndex):
        return hist["Close"].iloc[:, 0]
    return hist["Close"]


def _get_live_yfinance_quote(ticker_obj) -> tuple[float, pd.Timestamp] | tuple[None, None]:
    """yfinance에서 가장 최신 시세를 조회합니다."""
    import yfinance as yf

    ticker = ticker_obj.ticker

    try:
        fast_info = ticker_obj.fast_info
        price = getattr(fast_info, "last_price", None)
        if price is None and hasattr(fast_info, "get"):
            price = fast_info.get("lastPrice")
        if price is not None and not pd.isna(price):
            return float(price), pd.Timestamp.now().normalize()
    except Exception:
        pass

    try:
        info = ticker_obj.info
        price = info.get("regularMarketPrice") or info.get("currentPrice")
        if price is not None and not pd.isna(price):
            return float(price), pd.Timestamp.now().normalize()
    except Exception:
        pass

    for interval in ("1m", "5m", "15m"):
        try:
            intraday = yf.download(
                ticker,
                period="1d",
                interval=interval,
                progress=False,
                auto_adjust=True,
            )
            if not intraday.empty:
                close = _extract_close_series(intraday).dropna()
                if not close.empty:
                    ts = pd.to_datetime(close.index[-1], utc=True).tz_convert(None)
                    return float(close.iloc[-1]), ts.normalize()
        except Exception:
            continue

    return None, None


def fetch_yfinance_series(ticker: str, value_col: str) -> pd.DataFrame:
    import yfinance as yf

    ticker_obj = yf.Ticker(ticker)
    hist = ticker_obj.history(period="max", auto_adjust=True)
    if hist.empty:
        raise ValueError(f"yfinance 데이터 없음: {ticker}")

    close = _extract_close_series(hist).dropna()
    df = close.reset_index()
    df.columns = ["date", value_col]
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna().sort_values("date")

    live_price, live_date = _get_live_yfinance_quote(ticker_obj)
    if live_price is not None and live_date is not None:
        live_date = pd.Timestamp(live_date).normalize()
        last_date = pd.Timestamp(df.iloc[-1]["date"]).normalize()
        if live_date > last_date:
            df = pd.concat(
                [df, pd.DataFrame({"date": [live_date], value_col: [live_price]})],
                ignore_index=True,
            )
        elif live_date == last_date:
            df.iloc[-1, df.columns.get_loc(value_col)] = live_price
            df.iloc[-1, df.columns.get_loc("date")] = live_date

    return df.sort_values("date")


def apply_transform(df: pd.DataFrame, value_col: str, transform: str | None) -> pd.DataFrame:
    if transform == "monthly_change":
        work = df.copy()
        work["month"] = pd.to_datetime(work["date"]).dt.to_period("M")
        monthly = work.groupby("month", as_index=False).agg(
            date=("date", "max"),
            **{value_col: (value_col, "last")},
        )
        monthly[value_col] = monthly[value_col].diff()
        monthly = monthly.dropna(subset=[value_col])
        return monthly[["date", value_col]]
    return df


def _today() -> pd.Timestamp:
    return pd.Timestamp.now().normalize()


def _trim_future_dates(df: pd.DataFrame) -> pd.DataFrame:
    """오늘 이후 날짜를 제거합니다."""
    today = _today()
    dates = pd.to_datetime(df["date"]).dt.normalize()
    return df.loc[dates <= today].copy()


def _latest_observation(df: pd.DataFrame, value_col: str) -> tuple[pd.Timestamp, float]:
    trimmed = _trim_future_dates(df)
    if trimmed.empty:
        raise ValueError("유효한 데이터가 없습니다.")
    row = trimmed.iloc[-1]
    return pd.Timestamp(row["date"]).normalize(), float(row[value_col])


def prepare_series(df: pd.DataFrame, value_col: str, resample_monthly: bool = False) -> pd.DataFrame:
    """그래프용 시계열 (일별 원본 사용, 월말 날짜 생성 안 함)."""
    return _trim_future_dates(df.copy())


def load_indicator(config: dict) -> tuple[pd.DataFrame, pd.Timestamp, float]:
    value_col = config["value_col"]
    source = config.get("source", "fred")

    if source == "fred":
        df = fetch_fred_series(config["series_id"], value_col)
    elif source == "yfinance":
        df = fetch_yfinance_series(config["ticker"], value_col)
    else:
        raise ValueError(f"지원하지 않는 데이터 소스: {source}")

    df = apply_transform(df, value_col, config.get("transform"))
    latest_date, latest_value = _latest_observation(df, value_col)
    chart_df = prepare_series(df, value_col, config.get("resample_monthly", False))
    return chart_df, latest_date, latest_value


def recent_window(df: pd.DataFrame, years: int = 10) -> pd.DataFrame:
    cutoff = df["date"].max() - pd.DateOffset(years=years)
    return df[df["date"] >= cutoff]
