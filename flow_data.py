"""외국인·기관 30일 누적 순매수 (pykrx 기반, KR 종목 전용)."""
import re
from datetime import datetime, timedelta


def fetch_30day_flow(ticker: str) -> dict | None:
    """30 거래일 외국인·기관 누적 순매수. 실패 시 None."""
    if not ticker or not re.fullmatch(r"\d{6}", ticker):
        return None
    try:
        from pykrx import stock as krx
        end_date = datetime.now()
        start_date = end_date - timedelta(days=50)  # 영업일 약 30일 확보
        df = krx.get_market_trading_value_by_date(
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
            ticker,
        )
        if df is None or df.empty:
            return None
        df_30 = df.tail(30)
        foreign = float(df_30["외국인합계"].sum()) if "외국인합계" in df_30 else 0.0
        institution = float(df_30["기관합계"].sum()) if "기관합계" in df_30 else 0.0
        return {
            "foreign_30d_won": foreign,
            "institution_30d_won": institution,
            "trading_days": len(df_30),
        }
    except Exception:
        return None


def format_flow_billion(won: float) -> tuple[str, str]:
    """원화 금액 → ('+1,200억원', '순매수') 형태."""
    if won == 0 or won is None:
        return "0원", "변동 없음"
    sign = "+" if won > 0 else "-"
    direction = "순매수" if won > 0 else "순매도"
    bil = abs(won) / 100_000_000
    return f"{sign}{bil:,.0f}억원", direction
