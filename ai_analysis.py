"""상위 종목 AI 심층 분석 (Claude Sonnet)."""
import json
import time

import anthropic


def _fp(v) -> str:
    if v in (None, "조회 불가"):
        return "N/A"
    try:
        return f"{int(v):,}원"
    except (TypeError, ValueError):
        return str(v)


def _fl(v) -> str:
    if v in (None, "조회 불가"):
        return "N/A"
    try:
        n = float(v)
        if n >= 1e12: return f"{n/1e12:.1f}조"
        if n >= 1e8:  return f"{n/1e8:.0f}억"
        return f"{n:,.0f}원"
    except (TypeError, ValueError):
        return str(v)


def _safe_parse_json(raw: str) -> list[dict] | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 잘린 JSON 복구 시도: 마지막 } 까지 + ]
    last = raw.rfind("}")
    if last > 0:
        try:
            return json.loads(raw[: last + 1] + "]")
        except json.JSONDecodeError:
            pass
    return None


def analyze_top_holdings(portfolio: list[dict], stock_data: dict, api_key: str,
                         top_n: int = 3) -> list[dict]:
    """비중 상위 top_n 종목에 대한 심층 분석.

    반환: [{name, ticker, competitive_position, recent_performance, valuation,
           catalysts, risks(list[str]), strategy_short, strategy_mid}, ...]
    """
    if not api_key:
        raise RuntimeError("API 키가 없습니다.")

    top = sorted(portfolio, key=lambda h: h.get("비중", 0), reverse=True)[:top_n]
    if not top:
        return []

    summaries = []
    for h in top:
        d = stock_data.get(h.get("ticker") or "", {}) or {}
        krx = d.get("krx", {}) or {}
        nf = d.get("naver_finance", {}) or {}
        target = nf.get("analyst_target_price")
        target_str = f"{target:,}원" if isinstance(target, (int, float)) else "N/A"
        summaries.append(
            f"[{h['종목명']} | {h.get('ticker') or 'N/A'} | 비중: {h.get('비중',0):.1f}%]\n"
            f"현재가: {_fp(krx.get('current_price'))} | 시가총액: {_fl(krx.get('market_cap'))}\n"
            f"PER: {nf.get('per','N/A')} | PBR: {nf.get('pbr','N/A')} | "
            f"EPS: {nf.get('eps','N/A')} | BPS: {nf.get('bps','N/A')}\n"
            f"52주 고점: {_fp(krx.get('week52_high'))} | 52주 저점: {_fp(krx.get('week52_low'))}\n"
            f"외국인 보유: {krx.get('foreign_ownership_ratio','N/A')}%\n"
            f"증권사 목표주가: {target_str}\n"
            f"배당수익률: {nf.get('dividend_yield','N/A')}"
        )

    system_prompt = (
        "[역할 정의]\n"
        "너는 국내 증권사 PB센터의 시니어 애널리스트다. "
        "20년차 베테랑처럼 깊이 있는 분석을 제공한다.\n\n"
        "[분석 항목 — 각 종목별로 모두 작성]\n"
        "- competitive_position: 산업 내 경쟁 포지션 (시장점유율, 진입장벽/해자, 경쟁사 대비 차별점, 3-4문장)\n"
        "- recent_performance: 최근 실적 트렌드와 가이던스 (최근 분기 매출·영업이익, 회사 가이던스, 컨센서스 변동, 3-4문장)\n"
        "- valuation: 밸류에이션 분석 — PER·PBR을 동종업계 평균과 구체적으로 비교 "
        "(예: 'PER 18배 vs 업종 평균 14배 → 28% 프리미엄', 3-4문장)\n"
        "- catalysts: 향후 6-12개월 모멘텀 동인 (실적 모멘텀, 신제품·신사업, 정책·매크로 등 구체 트리거, 3-4문장)\n"
        "- risks: 구체적 리스크 3가지 (사실 기반, 배열로 반환)\n"
        "- strategy_short: 단기(3개월) 투자 전략 — 구체적 액션 "
        "(예: '비중 30% → 20%로 축소', '50,000원 분할 매수 시작')\n"
        "- strategy_mid: 중기(6-12개월) 투자 전략 — 구체적 액션\n\n"
        "[작성 규칙]\n"
        "- 추상적 표현 금지: '긍정적이다', '지켜봐야 한다', '주목할 필요' 같은 모호한 표현 사용 금지\n"
        "- 모든 의견은 숫자·사실로 뒷받침 (PER, 매출 증가율, 점유율 등 정량 데이터 인용)\n"
        "- 각 텍스트 필드는 완결된 단락으로 작성, 절대 중간에 끊기지 않게\n\n"
        "[금지사항]\n"
        "- 일반론적 조언 금지 ('분산투자 중요', '리스크 관리 유의' 같은 일반론)\n"
        "- '투자는 본인 책임' 같은 면피성 문구는 분석 본문에 포함하지 말 것\n\n"
        "[필수 JSON 출력 형식 — 다른 텍스트 일절 금지]\n"
        "반드시 아래 JSON 형식으로만 답하라. name 필드는 입력 데이터의 종목명을 그대로 사용한다.\n\n"
        "{\n"
        '  "stocks": [\n'
        "    {\n"
        '      "name": "한미약품",\n'
        '      "ticker": "128940",\n'
        '      "competitive_position": "산업 내 경쟁 포지션 분석 (3-4문장)",\n'
        '      "recent_performance": "최근 실적과 가이던스 (3-4문장)",\n'
        '      "valuation": "밸류에이션 분석 (PER/PBR 동종업계 비교, 3-4문장)",\n'
        '      "catalysts": "향후 6-12개월 모멘텀 동인 (3-4문장)",\n'
        '      "risks": ["리스크1", "리스크2", "리스크3"],\n'
        '      "strategy_short": "단기 전략 (구체적 액션)",\n'
        '      "strategy_mid": "중기 전략 (구체적 액션)"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    user_message = (
        f"VIP 고객 포트폴리오 상위 {len(top)}개 종목 데이터:\n\n"
        f"{chr(10).join(summaries)}"
    )

    client = anthropic.Anthropic(api_key=api_key)
    last_err: Exception | None = None
    for attempt in range(3):
        if attempt > 0:
            time.sleep(1.5)
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=16000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```", 2)[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            parsed = _safe_parse_json(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get("stocks"), list):
                return parsed["stocks"]
            last_err = RuntimeError("JSON 파싱 실패 또는 'stocks' 키 없음")
        except Exception as e:
            last_err = e

    raise RuntimeError(f"AI 분석 실패 (3회 재시도 후): {last_err}")
