"""포트폴리오 건강 진단 — 집중도·섹터·성과·알파 계산 (Pure calculation, AI 호출 없음)."""
import yfinance as yf


def _hhi(weights: list[float]) -> float:
    """Herfindahl-Hirschman Index. 0~10000 범위. 높을수록 집중."""
    return sum(w * w for w in weights)


def _fetch_benchmark_ytd(ticker: str = "^KS11") -> float | None:
    """벤치마크 YTD 손익율 (%). 실패 시 None."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1y")
        if hist.empty:
            return None
        start = float(hist["Close"].iloc[0])
        end = float(hist["Close"].iloc[-1])
        return (end - start) / start * 100 if start else None
    except Exception:
        return None


def diagnose_health(portfolio: list[dict], sector_map: dict) -> dict:
    """포트폴리오 건강 진단 — 집중도/섹터/성과/알파 종합 평가."""
    if not portfolio:
        return {}

    sorted_p = sorted(portfolio, key=lambda h: h.get("비중", 0), reverse=True)
    weights = [h.get("비중", 0) for h in portfolio]

    # 1. 집중도
    top3_weight = sum(h.get("비중", 0) for h in sorted_p[:3])
    hhi = _hhi(weights)
    if hhi > 2500 or top3_weight > 75:
        conc_verdict = "고집중"
    elif hhi > 1500 or top3_weight > 50:
        conc_verdict = "다소 집중"
    else:
        conc_verdict = "분산 양호"

    # 2. 섹터 편중
    sector_agg: dict[str, float] = {}
    for h in portfolio:
        s = sector_map.get(h.get("ticker") or "", "기타")
        sector_agg[s] = sector_agg.get(s, 0) + h.get("비중", 0)
    if sector_agg:
        max_sector_name, max_sector_weight = max(sector_agg.items(), key=lambda x: x[1])
    else:
        max_sector_name, max_sector_weight = "-", 0.0
    if max_sector_weight > 40:
        sect_verdict = "편중"
    elif max_sector_weight > 25:
        sect_verdict = "다소 편중"
    else:
        sect_verdict = "균형"

    # 3. 성과 분포
    pnl_arr = [h for h in portfolio if h.get("손익율") is not None]
    profit_count = sum(1 for h in pnl_arr if h["손익율"] >= 0)
    loss_count = len(pnl_arr) - profit_count
    avg_return = sum(h["손익율"] for h in pnl_arr) / len(pnl_arr) if pnl_arr else 0.0
    best = max(pnl_arr, key=lambda h: h["손익율"]) if pnl_arr else None
    worst = min(pnl_arr, key=lambda h: h["손익율"]) if pnl_arr else None

    # 4. 알파 (vs KOSPI YTD)
    benchmark_ytd = _fetch_benchmark_ytd("^KS11")
    alpha = (avg_return - benchmark_ytd) if benchmark_ytd is not None else None

    return {
        "concentration": {
            "top3_weight": top3_weight,
            "hhi": hhi,
            "verdict": conc_verdict,
        },
        "sector": {
            "max_sector": max_sector_name,
            "max_sector_weight": max_sector_weight,
            "verdict": sect_verdict,
            "agg": sector_agg,
        },
        "performance": {
            "profit_count": profit_count,
            "loss_count": loss_count,
            "total_measured": len(pnl_arr),
            "avg_return": avg_return,
            "best": (best["종목명"], best["손익율"]) if best else None,
            "worst": (worst["종목명"], worst["손익율"]) if worst else None,
        },
        "alpha": {
            "portfolio_ytd": avg_return,
            "benchmark_ytd": benchmark_ytd,
            "alpha": alpha,
            "benchmark_name": "KOSPI",
        },
    }
