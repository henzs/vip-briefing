"""뉴스 수집 테스트 — naver search 기반."""
import re
import sys
import requests

io_encoding = "utf-8"
sys.stdout.reconfigure(encoding=io_encoding)


def fetch(name):
    url = f"https://r.jina.ai/https://search.naver.com/search.naver?where=news&query={name}"
    resp = requests.get(
        url, timeout=15,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"},
    )
    if resp.status_code != 200:
        return [], resp.text
    text = resp.text

    news = []
    seen = set()

    # 마크다운 링크 패턴 [제목](url) — 비이미지 URL만
    pattern = re.compile(r"\[([^\[\]]+)\]\((https?://[^)]+)\)")
    for m in pattern.finditer(text):
        title = m.group(1).strip()
        url_str = m.group(2)
        if any(x in url_str for x in ["pstatic.net", "naver.com/press", "naver.com/main", "search.pstatic"]):
            continue
        if "<mark>" in title or "</mark>" in title:
            title = re.sub(r"</?mark>", "", title).strip()
        if re.search(r"[가-힣]", title) and len(title) >= 10 and title not in seen:
            seen.add(title)
            news.append(title)
        if len(news) >= 10:
            break

    return news, text


for name in ["한미반도체", "동진쎄미켐", "LG 씨엔에스"]:
    print(f"\n=== {name} ===")
    headlines, raw = fetch(name)
    print(f"수집: {len(headlines)}개")
    for h in headlines:
        print(f"  - {h}")
    if not headlines:
        print(f"(raw length: {len(raw)})")
        # Show first 1500 chars to debug
        print("--- raw sample ---")
        print(raw[:1500])
