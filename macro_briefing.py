"""거시경제 브리핑 — 주요 지수 fetch + Claude 요약 분석."""
import json
from datetime import datetime

import anthropic
import yfinance as yf

# 주요 지수 (yfinance ticker)
INDICES = [
    ("KOSPI",     "^KS11"),
    ("KOSDAQ",    "^KQ11"),
    ("S&P 500",   "^GSPC"),
    ("나스닥",    "^IXIC"),
    ("USD/KRW",   "KRW=X"),
    ("US 10Y",    "^TNX"),
    ("WTI 원유",  "CL=F"),
]


def fetch_indices() -> list[dict]:
    """주요 지수의 현재가·일간 등락·YTD 등락 수집."""
    results = []
    for name, ticker in INDICES:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y")
            if hist.empty:
                continue
            current = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current
            ytd_start = float(hist["Close"].iloc[0])
            results.append({
                "name": name,
                "current": current,
                "daily_pct": (current - prev) / prev * 100 if prev else 0.0,
                "ytd_pct": (current - ytd_start) / ytd_start * 100 if ytd_start else 0.0,
            })
        except Exception:
            continue
    return results


def generate_macro_briefing(indices: list[dict], portfolio: list[dict],
                            api_key: str) -> dict:
    """Claude로 거시 브리핑 생성. 실패 시 빈 dict 반환 (지수 데이터만 포함)."""
    if not api_key or not indices:
        return {"indices": indices}

    idx_text = "\n".join([
        f"- {x['name']}: 현재 {x['current']:,.2f}, 일간 {x['daily_pct']:+.2f}%, YTD {x['ytd_pct']:+.2f}%"
        for x in indices
    ])
    holdings = ", ".join([h.get("종목명", "") for h in portfolio[:8]])

    prompt = (
        f"오늘({datetime.now().strftime('%Y년 %m월 %d일')}) 시장 브리핑을 VIP 고객용으로 작성한다.\n\n"
        f"[주요 지수]\n{idx_text}\n\n"
        f"[고객 보유 종목 일부]\n{holdings}\n\n"
        "너는 국내 증권사 PB센터의 시니어 애널리스트다. "
        "20년차 베테랑처럼 깊이 있는 시장 분석을 제공한다. "
        "추상적 표현 금지, 모든 의견은 위 데이터의 숫자·사실로 뒷받침한다.\n\n"
        "다음 구조의 JSON으로만 답하라. 다른 텍스트 일절 금지.\n\n"
        "{\n"
        '  "headline": "오늘의 시장 한 줄 요약 (구체적 사실·숫자 포함)",\n'
        '  "macro_overview": "글로벌·국내 시장 흐름 분석 (4-5문장)",\n'
        '  "key_drivers": ["오늘의 주요 동인 1", "동인 2", "동인 3"],\n'
        '  "portfolio_implication": "고객 포트폴리오와 관련된 시각 (2-3문장)"\n'
        "}"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        parsed = json.loads(raw)
        parsed["indices"] = indices
        return parsed
    except Exception:
        return {"indices": indices}
