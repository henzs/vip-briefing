"""PER 역사·업종 평균 비교.

- 역사적 PER: pykrx로 최근 5년 일별 PER → 평균/최저/최고
- 업종 평균 PER: 수동 매핑 테이블 (KRX 실시간 업종 지수 적용은 별도 작업)
KR 종목 전용 (해외는 yfinance에 historical PER 데이터가 제한적).
"""
import re
from datetime import datetime, timedelta

# 업종 평균 PER (2026년 시점 근사치 — 매년 검토 필요)
SECTOR_AVG_PER: dict[str, float] = {
    "반도체": 18.0,
    "반도체장비": 22.0,
    "전자부품": 14.0,
    "IT부품": 16.0,
    "2차전지": 22.0,
    "2차전지소재": 25.0,
    "소재": 14.0,
    "바이오": 30.0,
    "자동차": 7.5,
    "자동차부품": 9.0,
    "기계": 12.0,
    "철강": 7.0,
    "비철금속": 10.0,
    "금융": 5.5,
    "보험": 7.0,
    "핀테크": 30.0,
    "IT플랫폼": 25.0,
    "게임": 18.0,
    "화학": 12.0,
    "에너지/화학": 11.0,
    "중공업": 12.0,
    "조선": 13.0,
    "유틸리티": 10.0,
    "통신": 9.0,
    "소비재": 14.0,
    "건설/지주": 8.0,
    "방산": 18.0,
    "엔터": 25.0,
    "가전": 12.0,
    "건설": 7.5,
    "기타": 12.0,
}


def fetch_per_history(ticker: str, years: int = 5) -> dict | None:
    """KR 종목 5년 일별 PER → 통계. 실패 시 None."""
    if not ticker or not re.fullmatch(r"\d{6}", ticker):
        return None
    try:
        from pykrx import stock as krx
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years * 365)
        df = krx.get_market_fundamental_by_date(
            start_date.strftime("%Y%m%d"),
            end_date.strftime("%Y%m%d"),
            ticker,
        )
        if df is None or df.empty or "PER" not in df.columns:
            return None
        per_series = df["PER"].dropna()
        per_series = per_series[per_series > 0]  # 음수/0 제외
        if len(per_series) < 30:
            return None
        return {
            "avg_5y": float(per_series.mean()),
            "min_5y": float(per_series.min()),
            "max_5y": float(per_series.max()),
            "median_5y": float(per_series.median()),
        }
    except Exception:
        return None


def get_per_comparison(ticker: str, current_per, sector: str) -> dict:
    """현재 PER vs 5년 평균 vs 업종 평균 통합 비교 데이터."""
    history = fetch_per_history(ticker) or {}
    sector_avg = SECTOR_AVG_PER.get(sector, SECTOR_AVG_PER["기타"])

    result = {
        "current_per": float(current_per) if isinstance(current_per, (int, float)) else None,
        "sector": sector,
        "sector_avg_per": sector_avg,
        **history,
    }

    cur = result["current_per"]
    avg_5y = result.get("avg_5y")
    if cur and avg_5y:
        result["vs_history_pct"] = (cur / avg_5y - 1) * 100
    if cur and sector_avg:
        result["vs_sector_pct"] = (cur / sector_avg - 1) * 100

    return result
