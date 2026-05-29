"""종목 1년 주가 차트 — matplotlib으로 PNG 생성.

KR 종목: pykrx OHLCV
US 종목: yfinance history

한국어 폰트 이슈 회피를 위해 차트 라벨은 영문 유지.
"""
import re
import sys
from datetime import datetime, timedelta
from io import BytesIO

import matplotlib

matplotlib.use("Agg")  # non-interactive backend (서버 환경 안전)
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


def _generate_kr_chart(ticker: str) -> bytes | None:
    if not re.fullmatch(r"\d{6}", ticker):
        return None
    try:
        from pykrx import stock as krx
        end_date = datetime.now()
        start_date = end_date - timedelta(days=400)
        df = krx.get_market_ohlcv_by_date(
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
            ticker,
        )
        if df is None or df.empty:
            return None
        close = df["종가"]
    except Exception as e:
        print(f"[chart] KR fetch fail for {ticker}: {e}", file=sys.stderr)
        return None
    return _plot_chart(close, ticker)


def _generate_us_chart(ticker: str) -> bytes | None:
    try:
        import yfinance as yf
        df = yf.Ticker(ticker).history(period="1y")
        if df is None or df.empty:
            return None
        close = df["Close"]
    except Exception as e:
        print(f"[chart] US fetch fail for {ticker}: {e}", file=sys.stderr)
        return None
    return _plot_chart(close, ticker)


def _plot_chart(close, ticker: str) -> bytes | None:
    """공통 차트 그리기 — 종가 + MA20 + MA60."""
    try:
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()

        fig, ax = plt.subplots(figsize=(8, 3.4))
        ax.plot(close.index, close.values, color="#2A1F15",
                linewidth=1.6, label="Close")
        ax.plot(ma20.index, ma20.values, color="#16A34A",
                linewidth=1.0, alpha=0.75, label="MA20")
        ax.plot(ma60.index, ma60.values, color="#B91C1C",
                linewidth=1.0, alpha=0.75, label="MA60")

        ax.set_title(f"{ticker}  —  1-Year Price", fontsize=11, color="#2A1F15")
        ax.legend(loc="upper left", fontsize=9, frameon=False)
        ax.grid(True, alpha=0.18)
        ax.tick_params(axis="both", labelsize=8, colors="#3A2A1E")
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color("#3A2A1E")

        # Y axis: 천 단위 콤마
        ax.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"{x:,.0f}")
        )
        # X axis: 2개월 간격 YYYY-MM
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        plt.xticks(rotation=0)

        fig.patch.set_facecolor("#F5EFE2")
        ax.set_facecolor("#F5EFE2")

        plt.tight_layout()

        buf = BytesIO()
        plt.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                    facecolor="#F5EFE2")
        plt.close(fig)
        return buf.getvalue()
    except Exception as e:
        print(f"[chart] plot fail for {ticker}: {e}", file=sys.stderr)
        return None


def generate_price_chart(ticker: str, market: str = "KR") -> bytes | None:
    """1년 주가 차트 PNG 바이트. 실패 시 None."""
    if not ticker:
        return None
    if market == "US":
        return _generate_us_chart(ticker)
    return _generate_kr_chart(ticker)
