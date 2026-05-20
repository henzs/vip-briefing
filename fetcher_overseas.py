"""해외 주식: Claude Haiku로 티커 식별 + yfinance로 데이터 수집."""
import re

import anthropic
import yfinance as yf


def identify_ticker(display_name: str, api_key: str) -> str | None:
    """증권사 표시명 → Yahoo Finance 티커 (Claude Haiku 사용)."""
    if not api_key:
        return None
    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16,
            messages=[{
                "role": "user",
                "content": (
                    f'What is the Yahoo Finance ticker symbol for "{display_name}"? '
                    "Reply with ONLY the ticker symbol (e.g., NVDA, TSLA, SOXL). "
                    "If unknown or ambiguous, reply NULL."
                ),
            }],
        )
        raw = resp.content[0].text.strip().upper()
        if raw == "NULL" or not re.fullmatch(r"[A-Z0-9.\-]{1,7}", raw):
            return None
        return raw
    except Exception:
        return None


def get_yahoo_data(ticker: str) -> dict:
    """yfinance로 해외 주식 데이터 수집. 국내 데이터와 호환되는 스키마로 반환."""
    NOT_AVAILABLE = "조회 불가"
    krx_data = {
        "source": "Yahoo Finance",
        "current_price": NOT_AVAILABLE, "market_cap": NOT_AVAILABLE,
        "week52_high": NOT_AVAILABLE, "week52_low": NOT_AVAILABLE,
        "foreign_ownership_ratio": NOT_AVAILABLE,
    }
    naver_data = {
        "source": "Yahoo Finance",
        "per": NOT_AVAILABLE, "pbr": NOT_AVAILABLE,
        "eps": NOT_AVAILABLE, "bps": NOT_AVAILABLE,
        "dividend_yield": NOT_AVAILABLE, "analyst_target_price": NOT_AVAILABLE,
    }
    name = ticker
    try:
        info = yf.Ticker(ticker).info
        name = info.get("longName") or info.get("shortName") or ticker

        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price is not None:
            krx_data["current_price"] = round(float(price), 2)
        if info.get("marketCap"):
            krx_data["market_cap"] = int(info["marketCap"])
        if info.get("fiftyTwoWeekHigh"):
            krx_data["week52_high"] = round(float(info["fiftyTwoWeekHigh"]), 2)
        if info.get("fiftyTwoWeekLow"):
            krx_data["week52_low"] = round(float(info["fiftyTwoWeekLow"]), 2)
        if info.get("trailingPE"):
            naver_data["per"] = round(float(info["trailingPE"]), 2)
        if info.get("priceToBook"):
            naver_data["pbr"] = round(float(info["priceToBook"]), 2)
        if info.get("trailingEps"):
            naver_data["eps"] = round(float(info["trailingEps"]), 2)
        if info.get("bookValue"):
            naver_data["bps"] = round(float(info["bookValue"]), 2)
        if info.get("dividendYield"):
            naver_data["dividend_yield"] = f"{info['dividendYield'] * 100:.2f}%"
        if info.get("targetMeanPrice"):
            naver_data["analyst_target_price"] = round(float(info["targetMeanPrice"]), 2)
    except Exception:
        pass

    return {"ticker": ticker, "name": name, "krx": krx_data, "naver_finance": naver_data}
