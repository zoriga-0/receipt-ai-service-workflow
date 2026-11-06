"""
normalize.py

Studio Agent가 돌려준 JSON을 엑셀 1행 형식으로 정리한다.

Studio 추출 결과는 보통 이렇게 생겼다:
    {"상호명": ["스타벅스 강남점"], "결제금액": ["10,300원"], ...}
값이 배열로 감싸져 있거나, 키 이름이 한글/영어로 다를 수 있어서
아래 별칭 표로 맞춘다. 워크플로우 스키마의 키 이름을 바꾸면
FIELD_ALIASES에 추가하면 된다.
"""

import re

CATEGORIES = ("식비", "교통비", "활동비", "기타")

# 사용자가 고를 수 있는 경비 구분 목록 (화면에서 쉼표로 고쳐 쓸 수 있다)
CATEGORY_PRESETS = {
    "기본": ["식비", "교통비", "활동비", "기타"],
    "학생회·동아리": ["행사비", "회의비", "간식비", "비품·소모품비", "교통비", "기타"],
    "회사": ["복리후생비", "접대비", "회의비", "여비교통비", "소모품비", "기타"],
}


def parse_categories(text: str) -> list[str]:
    """'행사비, 회의비, 기타' → ['행사비', '회의비', '기타']. 중복 제거, '기타'는 항상 맨 뒤."""
    items = []
    for part in str(text or "").replace("\n", ",").split(","):
        name = part.strip()
        if name and name not in items:
            items.append(name)
    items = [c for c in items if c != "기타"] + ["기타"]
    return items

FIELD_ALIASES = {
    "사용일자": ["사용일자", "사용일", "거래일자", "거래일시", "결제일자", "결제일시", "일자", "날짜",
              "date", "usedate", "transactiondate", "paymentdate", "receiptdate"],
    "상호명": ["상호명", "상호", "가맹점명", "가맹점", "매장명", "업체명", "상점명", "가게명", "점포명",
            "판매처", "판매자", "판매점", "사업장명", "사업자명", "업소명", "회사명", "브랜드", "사용처",
            "storename", "store", "merchant", "merchantname", "shopname", "shop", "vendor",
            "vendorname", "businessname", "companyname", "seller", "name"],
    "결제금액": ["결제금액", "합계금액", "총금액", "합계", "총액", "금액", "결제액",
             "amount", "totalamount", "total", "paymentamount", "totalprice"],
    "경비구분": ["경비구분", "경비분류", "분류", "카테고리", "category", "expensecategory", "expensetype"],
    "통화": ["통화", "화폐", "currency", "currencycode"],
    "검토여부": ["검토여부", "검토필요여부", "검토필요", "검토", "reviewrequired", "needsreview",
             "review", "reviewstatus"],
    "사유": ["사유", "검토사유", "판단사유", "이유", "reason", "reviewreason", "comment"],
}


# 키 이름이 별칭과 정확히 같지 않을 때 '포함 여부'로 찾는 단어
_FUZZY = {
    "상호명": ["상호", "가맹", "매장", "상점", "가게", "점포", "업체", "판매", "업소", "사업장",
            "store", "merchant", "shop", "vendor", "seller"],
    "사용일자": ["일자", "날짜", "일시", "date"],
    "결제금액": ["금액", "합계", "총액", "amount", "total"],
    "경비구분": ["구분", "분류", "category"],
    "검토여부": ["검토", "review"],
    "사유": ["사유", "이유", "reason"],
}

_CITATION = re.compile(r"【[^】]*】|\[\^?\d+\]|†\d*")


def _norm_key(key) -> str:
    return re.sub(r"[\s_\-()\[\]./]", "", str(key)).lower()


_ALIAS_LOOKUP = {}
for _field, _aliases in FIELD_ALIASES.items():
    for _a in _aliases:
        _ALIAS_LOOKUP.setdefault(_norm_key(_a), _field)


##################################################
# 값 꺼내기
##################################################

def _walk(obj, out: dict):
    """중첩 dict를 평탄화한다. 같은 필드가 여러 번 나오면 처음 값을 쓴다."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            field = _ALIAS_LOOKUP.get(_norm_key(k))
            if field and field not in out and not isinstance(v, dict):
                out[field] = v
            elif isinstance(v, dict):
                if field and field not in out and "value" in v:
                    out[field] = v["value"]
                else:
                    _walk(v, out)
            elif isinstance(v, list) and v and all(isinstance(i, dict) for i in v):
                _walk(v[0], out)


def _scalar(v, join=False):
    """배열로 감싼 값을 하나로 만든다."""
    if isinstance(v, dict):
        v = v.get("value", "")
    if isinstance(v, list):
        items = [_scalar(i) for i in v]
        items = [i for i in items if i not in (None, "")]
        if not items:
            return ""
        if join:
            return " / ".join(dict.fromkeys(str(i) for i in items))
        return items[0]
    if v is None:
        return ""
    if isinstance(v, str):
        return _CITATION.sub("", v).strip()
    return v


def _fuzzy_fill(obj, out: dict):
    """정확히 맞는 키가 없던 필드를 '키에 포함된 단어'로 한 번 더 찾는다."""
    if not isinstance(obj, dict):
        return
    for k, v in obj.items():
        if isinstance(v, dict):
            _fuzzy_fill(v, out)
            continue
        nk = _norm_key(k)
        if nk in _ALIAS_LOOKUP:
            continue
        for field, words in _FUZZY.items():
            if field not in out and any(w in nk for w in words):
                out[field] = v
                break


def extract_fields(data: dict) -> dict:
    flat = {}
    _walk(data, flat)
    _fuzzy_fill(data, flat)
    return {
        field: _scalar(flat.get(field), join=(field == "사유"))
        for field in FIELD_ALIASES
    }


##################################################
# 정규화
##################################################

_CURRENCY_HINTS = [
    ("KRW", ["krw", "원", "₩", "won"]),
    ("USD", ["usd", "$", "달러", "dollar"]),
    ("EUR", ["eur", "€", "유로"]),
    ("JPY", ["jpy", "¥", "円", "엔", "yen"]),
    ("CNY", ["cny", "rmb", "위안", "元"]),
    ("GBP", ["gbp", "£", "파운드"]),
]


def detect_currency(*texts) -> str:
    joined = " ".join(str(t) for t in texts if t not in (None, "")).lower()
    for code, hints in _CURRENCY_HINTS:
        if any(h in joined for h in hints):
            return code
    m = re.search(r"\b([a-z]{3})\b", joined)
    return m.group(1).upper() if m else ""


def parse_amount(v):
    if v in (None, ""):
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else round(float(v), 2)
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", str(v))
    if not m:
        return None
    num = float(m.group(0).replace(",", ""))
    return int(num) if num.is_integer() else round(num, 2)


def normalize_date(v) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    m = re.search(r"(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})", s)
    if not m:
        m = re.search(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?!\d)", s)
    if not m:
        m2 = re.search(r"(?<!\d)(\d{2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})(?!\d)", s)
        if m2:
            y, mo, d = 2000 + int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"
        return s
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 1 <= mo <= 12 and 1 <= d <= 31:
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return s


_CATEGORY_KEYWORDS = {
    "식비": ["식비", "식대", "식사", "음식", "음료", "카페", "커피", "회식", "meal", "food"],
    "교통비": ["교통", "택시", "버스", "지하철", "기차", "ktx", "주차", "주유", "유류", "통행",
            "transport", "taxi"],
    "활동비": ["활동", "행사", "동아리", "학생회", "대관", "재료", "비품", "인쇄", "activity"],
}


def normalize_category(v) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    if s in CATEGORIES:
        return s
    low = s.lower()
    for cat, words in _CATEGORY_KEYWORDS.items():
        if any(w in low for w in words):
            return cat
    return "기타"


def normalize_review(v) -> str:
    if isinstance(v, bool):
        return "검토 필요" if v else "검토 불필요"
    s = str(v or "").strip().lower().replace(" ", "")
    if not s:
        return ""
    if "완료" in s:
        return "검토 완료"
    if any(w in s for w in ("불필요", "필요없", "없음", "아니", "false", "no")) or s in ("n", "0", "x"):
        return "검토 불필요"
    if any(w in s for w in ("필요", "검토", "true", "yes", "확인")) or s in ("y", "1", "o"):
        return "검토 필요"
    return str(v)


def normalize_extract(data: dict) -> dict:
    f = extract_fields(data)
    amount_raw = f["결제금액"]
    currency = str(f["통화"]).upper() if f["통화"] else ""
    if currency and len(currency) != 3:
        currency = detect_currency(currency) or currency
    currency = currency or detect_currency(amount_raw) or "KRW"
    return {
        "사용일자": normalize_date(f["사용일자"]),
        "상호명": str(f["상호명"] or ""),
        "결제금액": parse_amount(amount_raw) or None,
        "경비구분": normalize_category(f["경비구분"]),
        "통화": currency,
    }


def normalize_review_result(data: dict) -> dict:
    f = extract_fields(data)
    return {
        "경비구분": normalize_category(f["경비구분"]),
        "검토여부": normalize_review(f["검토여부"]),
        "사유": str(f["사유"] or ""),
    }


##################################################
# 1번 + 2번 결과 합치기
##################################################

COLUMNS = ["사용일자", "분기", "상호명", "결제금액", "경비구분", "목적", "통화", "검토여부", "사유", "파일명"]
REVIEW_OPTIONS = ["검토 필요", "검토 완료", "검토 불필요"]


##################################################
# 검산: AI가 '자신 있게 틀린' 값을 잡기 위한 규칙
##################################################

def sanity_check(extract: dict, today=None) -> list[str]:
    """추가 AI 호출 없이 코드로 확인할 수 있는 이상값."""
    import datetime as _dt

    problems = []
    amount = extract.get("결제금액")
    currency = extract.get("통화") or "KRW"
    if isinstance(amount, (int, float)):
        if amount <= 0:
            problems.append(f"금액이 0 이하({amount:,})")
        elif currency == "KRW" and (amount < 100 or not float(amount).is_integer()):
            # 예: '10,300원'을 10.3으로 읽은 경우
            problems.append(f"원화 금액이 비정상적임({amount}) — 쉼표/소수점 오인식 의심")

    date = extract.get("사용일자") or ""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date)
    if date and not m:
        problems.append(f"날짜 형식을 읽지 못함({date})")
    elif m:
        try:
            d = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d > (today or _dt.date.today()):
                problems.append(f"미래 날짜({date}) — 연도/월 오인식 의심")
        except ValueError:
            problems.append(f"존재하지 않는 날짜({date})")
    return problems


def compare_verify(extract: dict, verify: dict) -> list[str]:
    """1번(추출)과 3번(검증)이 같은 사진을 각자 읽은 값이 다르면 사유를 돌려준다."""
    problems = []
    a1, a2 = extract.get("결제금액"), verify.get("결제금액")
    if a1 not in (None, "") and a2 not in (None, "") and float(a1) != float(a2):
        problems.append(f"교차검증 불일치: 금액 {a1:,} ≠ {a2:,}")
    d1, d2 = extract.get("사용일자"), verify.get("사용일자")
    if d1 and d2 and d1 != d2:
        problems.append(f"교차검증 불일치: 날짜 {d1} ≠ {d2}")
    return problems


def merge_row(
    file_name: str,
    extract: dict | None,
    review: dict | None,
    errors: list[str],
    verify: dict | None = None,
    purpose_result: dict | None = None,
    context: dict | None = None,
) -> dict:
    """
    purpose_result: 목적 반영 분류(Solar) 결과. 있으면 경비구분을 이 값으로 정한다.
    context: {"purpose": 지출 목적, "categories": 경비 구분 목록}
    """
    extract = extract or {}
    review = review or {}
    context = context or {}
    categories = list(context.get("categories") or CATEGORIES)

    category = review.get("경비구분") or extract.get("경비구분") or "기타"
    review_flag = review.get("검토여부", "")
    reasons = [review["사유"]] if review.get("사유") else []

    missing = [k for k in ("사용일자", "상호명", "결제금액") if extract.get(k) in (None, "")]
    if missing and extract:
        reasons.append("필수값 누락: " + ", ".join(missing))
    checks = sanity_check(extract) if extract else []
    if verify and extract:
        checks += compare_verify(extract, verify)

    # 목적 반영 분류: 목록 안의 구분이면 그 값을 쓰고, 목적과 안 맞으면 검토 필요
    if purpose_result:
        if purpose_result.get("사유"):
            if review_flag != "검토 필요":
                reasons = [purpose_result["사유"]]
            else:
                reasons.append(f"목적 판단: {purpose_result['사유']}")
        if purpose_result.get("목록에있음"):
            category = purpose_result["경비구분"]
        else:
            checks.append(f"분류 목록에 없는 구분: {purpose_result.get('경비구분') or '(빈 값)'}")
        if purpose_result.get("목적부합") not in (None, "예"):
            checks.append(f"목적 확인({purpose_result['목적부합']})")
    if category not in categories:
        if not purpose_result:
            checks.append(f"분류 목록에 없는 구분: {category}")
        category = "기타" if "기타" in categories else categories[-1]
    reasons.extend(checks)
    if errors:
        reasons.extend(errors)
    if missing or checks or errors or not review_flag:
        review_flag = "검토 필요"

    return {
        "사용일자": extract.get("사용일자", ""),
        "상호명": extract.get("상호명", ""),
        "결제금액": extract.get("결제금액"),
        "경비구분": category,
        "목적": context.get("purpose", ""),
        "통화": extract.get("통화", ""),
        "검토여부": review_flag,
        "사유": " / ".join(reasons),
        "파일명": file_name,
    }