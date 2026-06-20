"""
미국·한국 경제 지표 데이터를 FRED/yfinance에서 가져와 그래프로 보여주는 프로그램.
"""

import sys

import matplotlib.pyplot as plt

from data import SERIES_CONFIGS, load_indicator, recent_window

if sys.platform == "win32":
    plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


def plot_and_save(df, value_col: str, title: str, ylabel: str, output_path: str, years: int = 10) -> None:
    recent = recent_window(df, years=years)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(recent["date"], recent[value_col], linewidth=2, color="#1f77b4")
    ax.set_title(f"{title} (최근 {years}년)", fontsize=16, pad=12)
    ax.set_xlabel("날짜")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.show(block=False)
    plt.close(fig)


def main() -> None:
    years = 10
    for chart in SERIES_CONFIGS:
        print(f"{chart['label']} 데이터를 가져오는 중...")
        plot_df, _, _ = load_indicator(chart)
        latest = plot_df.iloc[-1]
        print(
            f"최신 {chart['label']}: {latest['date'].strftime('%Y-%m-%d')} → "
            f"{chart['format'].format(latest[chart['value_col']])}"
        )
        output = f"chart_{chart['key'].lower()}.png"
        plot_and_save(
            plot_df,
            value_col=chart["value_col"],
            title=chart["title"],
            ylabel=chart["ylabel"],
            output_path=output,
            years=years,
        )
        print(f"그래프 저장: {output}\n")


if __name__ == "__main__":
    main()
