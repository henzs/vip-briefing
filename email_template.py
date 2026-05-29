"""고객 발송용 메일 제목·본문 자동 생성."""
import re
from datetime import datetime


def _first_sentence(text: str, max_chars: int = 90) -> str:
    """첫 마침표까지 (없으면 첫 max_chars)."""
    if not isinstance(text, str):
        return ""
    text = text.replace("\n", " ").strip()
    if not text:
        return ""
    m = re.search(r"[^.!?]+[.!?]", text)
    first = (m.group(0) if m else text).strip()
    if len(first) > max_chars:
        first = first[: max_chars - 1].rstrip() + "…"
    return first


def build_email(client_name: str, rm_name: str, portfolio: list[dict],
                ai_analysis: list[dict], account: dict,
                report_filename: str = "분석보고서.docx") -> dict:
    """메일 제목·본문 생성. 사용자가 직접 메일 클라이언트에 복사·붙여넣기 용도.

    Returns: {"subject": str, "body": str}
    """
    client_name = client_name or "고객"
    rm_name = rm_name or "담당 RM"

    # 핵심 발견 추출 (AI 분석 상위 3 종목별 한 줄)
    findings = []
    if ai_analysis:
        for ai in ai_analysis[:3]:
            name = ai.get("name") or "(종목)"
            # competitive_position 우선, 없으면 valuation, 없으면 catalysts
            source = (ai.get("competitive_position")
                      or ai.get("valuation")
                      or ai.get("catalysts")
                      or "")
            highlight = _first_sentence(source, max_chars=85)
            if highlight:
                findings.append(f" • {name}: {highlight}")

    if not findings:
        findings.append(" • 보유 종목 전반에 대한 정밀 분석을 완료했습니다.")

    findings_text = "\n".join(findings)

    # 매매잔고 규모 표현
    total_balance = account.get("매매잔고합계") or 0
    if isinstance(total_balance, (int, float)) and total_balance > 0:
        bil = total_balance / 100_000_000
        balance_text = f"(매매잔고 약 {bil:,.1f}억원)"
    else:
        balance_text = ""

    today_str = datetime.now().strftime("%Y년 %m월 %d일")
    n_top = len(ai_analysis) if ai_analysis else 0

    subject = (
        f"[{client_name}님] 보유 포트폴리오 정기 분석 리포트 "
        f"— {today_str}"
    )

    body = (
        f"{client_name}님 안녕하세요.\n"
        f"유진투자증권 법인전담팀 {rm_name}입니다.\n"
        f"\n"
        f"{client_name}님의 현재 포트폴리오 {balance_text}를 정밀 분석한\n"
        f"분기 정기 리포트를 첨부드립니다.\n"
        f"\n"
        f"📌 핵심 발견 ({today_str} 기준)\n"
        f"{findings_text}\n"
        f"\n"
        f"보고서에는 다음 내용이 포함되어 있습니다:\n"
        f" • 거시경제 브리핑 (오늘의 시장)\n"
        f" • 상위 {n_top}개 보유 종목 심층 분석 (산업 포지션·밸류에이션·모멘텀·리스크)\n"
        f" • PER 역사/업종 평균 비교\n"
        f" • 종목별 1년 주가 차트 및 30일 외국인·기관 수급\n"
        f" • 구체적 리밸런싱 액션 플랜\n"
        f"\n"
        f"📞 상담을 원하시면\n"
        f" - 본 메일에 회신\n"
        f" - 또는 평소 거래하시는 담당 PB께 직접 연락\n"
        f"\n"
        f"분기마다 정기 분석을 받아보고 싶으시면 회신 한 줄로 신청해주세요.\n"
        f"\n"
        f"감사합니다.\n"
        f"\n"
        f"{rm_name} 드림\n"
        f"유진투자증권 법인전담팀\n"
        f"\n"
        f"※ 본 자료는 투자 참고용이며 투자 권유가 아닙니다.\n"
        f"※ 첨부파일: {report_filename}"
    )

    return {"subject": subject, "body": body}
