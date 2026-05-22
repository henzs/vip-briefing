"""계좌잔고 이미지를 Claude Vision으로 분석해 보유 종목 리스트를 추출."""
import base64
import json
import re
from io import BytesIO

import anthropic
from PIL import Image


def _extract_json(raw: str) -> str:
    """Claude 응답에서 JSON 부분만 추출. 앞뒤 설명/계산과정/마크다운 펜스 모두 처리."""
    raw = raw.strip()
    # 1) ```json ... ``` 또는 ``` ... ``` 코드 펜스 추출
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fence:
        candidate = fence.group(1).strip()
        if candidate.startswith("[") or candidate.startswith("{"):
            return candidate
    # 2) 첫 [ 부터 마지막 ] 까지 (배열)
    start, end = raw.find("["), raw.rfind("]")
    if start >= 0 and end > start:
        return raw[start:end + 1]
    # 3) 첫 { 부터 마지막 } 까지 (객체)
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start:end + 1]
    return raw

# Claude API의 이미지 크기 제한은 base64 인코딩 후 5MB.
# base64는 원본을 약 4/3배로 부풀리므로, 원본 한도는 5MB × 3/4 ≈ 3.93MB.
# 안전 여유를 두어 3.7MB로 설정 (base64 후 약 4.93MB).
MAX_IMAGE_BYTES = 3_700_000

PROMPT = """이 이미지는 증권사 HTS의 잔고손익평가 화면이야. 두 가지를 추출한다.

[추출 1] 계좌 합계 정보 (이미지 상단의 합계/요약 영역)
- 예수금: 현금 잔고 (반드시 '예수금' 라벨, 출금가능액과 혼동 금지)
- 매매잔고합계: '매매잔고' 또는 '평가금액합' 라벨의 값 (현금+주식 평가 총합)

[추출 2] 보유 종목별 행

규칙:
1. 종목 행만 [추출 2]에 포함. 상단 합계/요약은 [추출 1] 'account'에만 사용.
2. 종목명은 이미지 텍스트 그대로 정확히. 한글은 한 글자 한 글자, 영문 티커는 대문자.
   **종목명이 화면에서 잘려서 일부만 보이면 (예: 'LIG디펜스앤...'), 보이는 글자만 그대로 추출. 절대 알아서 완성하거나 비슷한 다른 종목명으로 바꾸지 마라.** (정식 종목명은 코드에서 네이버 검색으로 후처리한다)
3. (일반), (담보), (신용) 등 괄호 표시는 제거.
4. 같은 종목 여러 줄이면 각각 별도 항목 (합산은 코드에서 처리).
5. 종목별 필드 (해당 라벨의 값만, 보이지 않으면 생략):
   - 현재가: '현재가' 컬럼 (콤마 제거 숫자)
   - 잔고수량: '잔고수량' (없으면 '매매잔고' 또는 '보유수량')
   - 매입가: '매입가' (없으면 '매수평단', '평균매입가')
   - 평가금액: '평가금액' 컬럼 (매입금액/매입원가/평가손익금액과 절대 혼동 금지)
   - 평가손익금액: '평가손익금액' 또는 '평가손익' (부호 포함, 음수면 -로)
   - 손익율: '손익율' 또는 '수익률' (% 단위, 부호 포함, 예: +8.40, -10.40)
6. 비중(%)은 이미지에 없으면 평가금액 기준 전체 합 대비 % 계산.
7. 반드시 아래 JSON 형식 그대로 반환. 다른 텍스트 일절 금지.

{
  "account": {
    "예수금": 263622612,
    "매매잔고합계": 1258112650
  },
  "stocks": [
    {"종목명": "현대차", "현재가": 591000, "잔고수량": 100, "매입가": 545217, "평가금액": 59100000, "평가손익금액": 4578260, "손익율": 8.40, "비중": 7.6},
    {"종목명": "삼성전자", "현재가": 270500, "잔고수량": 150, "매입가": 262526, "평가금액": 40575000, "평가손익금액": 1196063, "손익율": 3.04, "비중": 5.2}
  ]
}

account 필드의 값이 이미지에 안 보이면 해당 키만 생략 (또는 빈 객체 {}). 종목 필드도 안 보이면 생략 가능. 추측 절대 금지."""


def _compress_if_needed(image_bytes: bytes, media_type: str) -> tuple[bytes, str]:
    """5MB 초과 시 PIL로 축소. (압축된 바이트, 새 media_type) 반환.

    JPEG 품질·치수를 단계적으로 낮춰가며 한도 안에 들어올 때까지 시도.
    """
    if len(image_bytes) <= MAX_IMAGE_BYTES:
        return image_bytes, media_type

    img = Image.open(BytesIO(image_bytes))
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    # 1차: 원 해상도 유지, JPEG 품질만 낮춤
    for quality in (90, 80, 70):
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= MAX_IMAGE_BYTES:
            return data, "image/jpeg"

    # 2차: 해상도 축소 + 품질 조정
    for scale in (0.85, 0.7, 0.55, 0.4):
        new_size = (int(img.width * scale), int(img.height * scale))
        resized = img.resize(new_size, Image.LANCZOS)
        for quality in (85, 75, 65):
            buf = BytesIO()
            resized.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            if len(data) <= MAX_IMAGE_BYTES:
                return data, "image/jpeg"

    # 3차 (최후): 1200px 썸네일
    img.thumbnail((1200, 1200), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=70, optimize=True)
    return buf.getvalue(), "image/jpeg"


def parse_portfolio_image(image_bytes: bytes, media_type: str, api_key: str) -> list[dict]:
    """이미지 바이트를 받아 종목 리스트 반환. 실패 시 RuntimeError 발생.

    Claude API의 5MB 제한을 초과하면 자동으로 PIL 축소.
    """
    image_bytes, media_type = _compress_if_needed(image_bytes, media_type)
    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": image_data},
                },
                {"type": "text", "text": PROMPT},
            ],
        }],
    )

    # 응답에서 JSON 부분만 추출 (앞뒤 설명·계산과정·마크다운 펜스 모두 처리)
    raw = response.content[0].text
    clean = _extract_json(raw)

    try:
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 파싱 실패: {e}\n원본 응답:\n{raw}") from e

    # 신구 포맷 모두 지원: dict(account+stocks) 또는 list(stocks만)
    if isinstance(parsed, dict):
        return {
            "stocks": parsed.get("stocks", []) or [],
            "account": parsed.get("account", {}) or {},
        }
    if isinstance(parsed, list):
        return {"stocks": parsed, "account": {}}
    return {"stocks": [], "account": {}}


def detect_media_type(filename: str) -> str:
    """파일명 확장자로 MIME 타입 판별."""
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else "png"
    return {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    }.get(suffix, "image/png")
