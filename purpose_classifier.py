"""
purpose_classifier.py

목적 반영 분류: 사용자가 적은 '지출 목적'과 '경비 구분 목록'을 기준으로
경비 구분을 다시 고르고, 목적과 맞지 않는 내역이 있는지 본다.

Studio 워크플로우는 파일로만 시작할 수 있어서 글(목적·목록)을 넣을 수 없다.
그래서 이 단계는 Upstage Solar 모델을 직접 부른다. (같은 UPSTAGE_API_KEY 사용)
"""

import config
from agent_client import AgentError, _friendly_error, parse_json_text, to_dict

FIT_OPTIONS = ("예", "일부", "아니오", "확인 필요")

SYSTEM_PROMPT = """너는 경비 정산 담당자다. 영수증 한 장에서 읽어낸 정보와 사용자가 적은 지출 목적을 보고 판단한다.

규칙
1. 경비구분은 반드시 [분류 목록] 중 하나를 글자 그대로 고른다. 목록에 없는 이름을 만들지 않는다.
2. 지출 목적이 있으면 영수증 전체를 그 목적에 맞는 구분 하나로 고른다.
   식재료와 생활용품처럼 품목 종류가 섞여 있어도, 목적을 위해 함께 산 물건이면 문제 삼지 않는다.
   예) 목적 "MT 장보기", 품목 고기·채소·종량제봉투 → 경비구분 "행사비", 목적부합 "예"
3. '기타'는 목록의 어떤 구분에도 맞지 않을 때만 고른다. 품목이 섞였다는 이유만으로 '기타'를 고르지 않는다.
4. 품목을 하나씩 보고, 목적과 관계없어 보이는 개인 물품(면도기, 담배, 개인 화장품, 개인 의류 등)이
   하나라도 있으면 경비구분은 목적에 맞게 고르되 목적부합을 "일부"로 하고, 사유에 그 품목과 금액을 적는다.
   예) 목적 "MT 장보기", 품목 라면·생수·면도기 6,700원 → 경비구분 "행사비", 목적부합 "일부",
       사유 "면도기 6,700원은 개인 물품으로 보여 확인이 필요합니다"
5. 지출 목적이 '(없음)'이면 상호명과 품목으로 판단한다.
6. 판단할 근거가 정말 없을 때만 목적부합을 "확인 필요"로 한다.
7. [1차 분류 의견]은 목적을 모르고 내린 판단이다. 품목을 알아보는 데만 참고하고, 그 결론(특히 '섞여 있어 기타')은 따르지 않는다.

출력은 아래 JSON 하나만 쓴다. 다른 설명은 쓰지 않는다.
{"경비구분": "<분류 목록 중 하나>", "목적부합": "예|일부|아니오|확인 필요", "사유": "<한 문장>"}"""

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(
            api_key=config.UPSTAGE_API_KEY,
            base_url=config.SOLAR_BASE_URL,
            timeout=60,
            max_retries=2,
        )
    return _client


def set_client(client):
    """테스트용: 가짜 클라이언트를 주입한다."""
    global _client
    _client = client


def build_user_prompt(
    purpose: str,
    categories: list[str],
    extract: dict | None,
    review: dict | None,
    extract_raw: str = "",
    review_raw: str = "",
) -> str:
    extract = extract or {}
    review = review or {}
    amount = extract.get("결제금액")
    amount_txt = f"{amount:,} {extract.get('통화') or ''}".strip() if amount is not None else "(없음)"
    lines = [
        f"[분류 목록] {', '.join(categories)}",
        f"[지출 목적] {purpose or '(없음)'}",
        "[영수증에서 읽은 값]",
        f"- 사용일자: {extract.get('사용일자') or '(없음)'}",
        f"- 상호명: {extract.get('상호명') or '(없음)'}",
        f"- 결제금액: {amount_txt}",
        "[1차 분류 의견] (목적을 모르고 내린 판단, 품목 참고용)",
        f"- 경비구분: {review.get('경비구분') or '(없음)'}",
        f"- 사유: {review.get('사유') or '(없음)'}",
    ]
    # 원본 응답에는 품목·메뉴 같은 단서가 들어 있을 수 있다 (길면 자른다)
    raw = "\n".join(t for t in (extract_raw, review_raw) if t)[:1500]
    if raw:
        lines += ["[원본 응답 (품목 단서)]", raw]
    return "\n".join(lines)


def _pick(data: dict, *keys) -> str:
    for k in keys:
        if k in data and data[k] not in (None, ""):
            v = data[k]
            return str(v[0] if isinstance(v, list) and v else v).strip()
    # 키 이름이 조금 다를 때: 포함 여부로 찾기
    for k, v in data.items():
        if any(word in str(k) for word in keys):
            return str(v).strip()
    return ""


def normalize_purpose_result(data: dict, categories: list[str]) -> dict:
    category = _pick(data, "경비구분", "category", "구분")
    fit = _pick(data, "목적부합", "fit", "목적")
    fit = next((f for f in FIT_OPTIONS if f.replace(" ", "") == fit.replace(" ", "")), "확인 필요")
    return {
        "경비구분": category,
        "목록에있음": category in categories,
        "목적부합": fit,
        "사유": _pick(data, "사유", "reason", "이유"),
    }


def run_purpose_classifier(
    purpose: str,
    categories: list[str],
    extract: dict | None,
    review: dict | None,
    extract_raw: str = "",
    review_raw: str = "",
) -> tuple[dict, str]:
    """반환: (정리된 결과, 원본 응답 텍스트)"""
    if config.USE_MOCK:
        guess = (review or {}).get("경비구분")
        category = guess if guess in categories else categories[-1]
        data = {"경비구분": category, "목적부합": "예", "사유": f"[MOCK] 목적: {purpose or '없음'}"}
        return normalize_purpose_result(data, categories), str(data)

    prompt = build_user_prompt(purpose, categories, extract, review, extract_raw, review_raw)
    try:
        resp = _get_client().chat.completions.create(
            model=config.PURPOSE_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        text = resp.choices[0].message.content or ""
    except Exception as e:  # noqa: BLE001
        raise _friendly_error(e, config.PURPOSE_MODEL) from e

    try:
        data = parse_json_text(text)
    except AgentError:
        data = text  # JSON이 아니면 '키: 값' 문장으로 읽어 본다
    return normalize_purpose_result(to_dict(data, text), categories), text