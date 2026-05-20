"""포트폴리오 리밸런싱 구체 액션 제안 (Claude Sonnet 기반)."""
import json

import anthropic


def generate_rebalancing(portfolio: list[dict], ai_analysis: list[dict],
                         health: dict, macro: dict, api_key: str) -> list[dict]:
    """리밸런싱 구체 액션 리스트 반환. 실패 시 빈 리스트."""
    if not api_key or not portfolio:
        return []

    sorted_p = sorted(portfolio, key=lambda h: h.get("비중", 0), reverse=True)
    holdings_text = "\n".join([
        f"- {h['종목명']} ({h.get('ticker', '-')}): "
        f"비중 {h.get('비중', 0):.1f}%, "
        f"손익율 {h.get('손익율') if h.get('손익율') is not None else 'N/A'}{'%' if h.get('손익율') is not None else ''}"
        for h in sorted_p[:10]
    ])

    conc = health.get("concentration", {}) or {}
    sect = health.get("sector", {}) or {}
    perf = health.get("performance", {}) or {}
    alpha = health.get("alpha", {}) or {}

    context_lines = [
        f"- 집중도: 상위 3종목 합계 {conc.get('top3_weight', 0):.1f}% ({conc.get('verdict', '-')})",
        f"- 최대 섹터: {sect.get('max_sector', '-')} {sect.get('max_sector_weight', 0):.1f}% ({sect.get('verdict', '-')})",
        f"- 수익 분포: 수익 {perf.get('profit_count', 0)}개 / 손실 {perf.get('loss_count', 0)}개, 평균 {perf.get('avg_return', 0):+.2f}%",
    ]
    if alpha.get("alpha") is not None:
        context_lines.append(
            f"- 알파 vs {alpha.get('benchmark_name', 'KOSPI')}: "
            f"{alpha['alpha']:+.2f}%p (포트 {alpha.get('portfolio_ytd', 0):+.2f}% vs 벤치 {alpha.get('benchmark_ytd', 0):+.2f}%)"
        )
    if macro.get("headline"):
        context_lines.append(f"- 시장 환경: {macro['headline']}")

    context = "\n".join(context_lines)

    prompt = (
        "너는 국내 증권사 PB센터의 시니어 애널리스트다. "
        "20년차 베테랑처럼 깊이 있는 리밸런싱 액션을 제안한다.\n\n"
        f"[포트폴리오 진단]\n{context}\n\n"
        f"[보유 종목]\n{holdings_text}\n\n"
        "[작성 규칙]\n"
        "- 추상적 표현 금지 ('지켜봐야', '주목할 필요' 등 X)\n"
        "- 각 액션은 구체적 숫자(현재 비중 → 목표 비중)와 근거로 표현\n"
        "- 액션은 우선순위 순으로 3~5개\n"
        "- 손실 종목 무조건 매도 같은 단순 권고 금지, 근거 기반 판단\n\n"
        "다음 JSON으로만 답하라. 다른 텍스트 일절 금지.\n\n"
        "{\n"
        '  "actions": [\n'
        "    {\n"
        '      "priority": 1,\n'
        '      "action_type": "축소|확대|신규매수|매도|현금확보 중 하나",\n'
        '      "target": "종목명 또는 자산군(예: 헬스케어 ETF, 미국 배당 ETF)",\n'
        '      "current_weight": 현재 비중 % (신규매수면 0),\n'
        '      "target_weight": 목표 비중 %,\n'
        '      "rationale": "구체적 근거 (1-2문장, 숫자 포함)"\n'
        "    }\n"
        "  ]\n"
        "}"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        parsed = json.loads(raw)
        return parsed.get("actions", [])
    except Exception:
        return []
