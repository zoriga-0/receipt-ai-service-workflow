"""
records.py

결과 표 후처리: 분기 계산, 중복 영수증 감지, 이전 엑셀 불러오기.
"""

import datetime as dt
import io
import re

import pandas as pd

from normalize import (
    _ALIAS_LOOKUP,
    COLUMNS,
    REVIEW_OPTIONS,
    _norm_key,
    normalize_date,
    normalize_review,
    parse_amount,
)


def _text(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def join_reason(old, new: str) -> str:
    old = _text(old)
    return f"{old} / {new}" if old else new


##################################################
# 분기
##################################################

def quarter_of(date_str) -> str:
    m = re.match(r"^(\d{4})-(\d{2})-\d{2}$", _text(date_str))
    if not m:
        return ""
    month = int(m.group(2))
    if not 1 <= month <= 12:
        return ""
    return f"{m.group(1)}년 {(month - 1) // 3 + 1}분기"


def add_quarter(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["분기"] = df["사용일자"].map(quarter_of)
    return df


##################################################
# 중복 감지
##################################################

def _store_key(s) -> str:
    return re.sub(r"[\s()\[\]·\-_.,]", "", _text(s)).lower()


def detect_duplicates(df: pd.DataFrame, mark_mask: list[bool] | None = None) -> tuple[pd.DataFrame, int]:
    """
    사용일자·상호명·결제금액이 모두 같은 행을 '중복 의심'으로 표시한다.
    먼저 나온 행은 그대로 두고, 뒤에 나온 행만 표시한다.
    mark_mask: True인 행만 표시 대상 (이전 엑셀 행은 False로 두면 건드리지 않음)
    """
    df = df.copy().reset_index(drop=True)
    if mark_mask is None:
        mark_mask = [True] * len(df)
    seen: dict[tuple, str] = {}
    marked = 0
    for i, row in df.iterrows():
        date, store, amount = _text(row["사용일자"]), _store_key(row["상호명"]), row["결제금액"]
        if not date or not store or pd.isna(amount):
            continue
        key = (date, store, float(amount))
        if key not in seen:
            seen[key] = _text(row["파일명"]) or "이전 엑셀의 행"
            continue
        reason = _text(row["사유"])
        if mark_mask[i] and "중복 의심" not in reason and "동일 파일 중복" not in reason:
            df.at[i, "검토여부"] = "검토 필요"
            df.at[i, "사유"] = join_reason(row["사유"], f"중복 의심: {seen[key]}와 날짜·상호·금액이 같음")
            marked += 1
    return df, marked


##################################################
# 이전 엑셀 불러오기
##################################################

def _clean_date(v) -> str:
    if isinstance(v, (dt.date, dt.datetime, pd.Timestamp)):
        return v.strftime("%Y-%m-%d")
    return normalize_date(_text(v))


def read_previous_excel(data: bytes) -> pd.DataFrame:
    """
    이 서비스에서 받은 엑셀을 다시 읽어 결과 표 형식으로 돌려준다.
    컬럼 이름을 바꿔서 받은 엑셀도 숨김 시트(_columns)로 원래 이름을 찾는다.
    """
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=object)
    if "경비내역" in sheets:
        sheet_name = "경비내역"
    else:
        candidates = [n for n in sheets if not n.startswith("_") and n != "집계"]
        if not candidates:
            raise ValueError("엑셀에서 경비 내역 시트를 찾지 못했습니다.")
        sheet_name = candidates[0]
    raw = sheets[sheet_name]

    originals = list(raw.columns)
    meta = sheets.get("_columns")
    if meta is not None and len(meta.columns) == len(raw.columns):
        originals = [str(c) for c in meta.columns]
    return _to_result_table(raw, originals)


def read_previous_csv(data: bytes) -> pd.DataFrame:
    """
    이 서비스에서 받은 CSV(또는 같은 컬럼의 CSV)를 결과 표 형식으로 돌려준다.
    한글 엑셀에서 저장한 CSV(cp949)도 읽는다.
    CSV는 숨김 시트가 없어서, 컬럼 이름을 직접 바꿨다면 별칭 표로 찾을 수 있는 이름이어야 한다.
    """
    raw = None
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            raw = pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding=enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if raw is None:
        raise ValueError("CSV 글자 인코딩을 읽지 못했습니다. UTF-8로 저장해 다시 올려주세요.")
    return _to_result_table(raw, list(raw.columns))


def read_previous_file(name: str, data: bytes) -> pd.DataFrame:
    """파일 확장자를 보고 엑셀 또는 CSV로 읽는다."""
    if name.lower().endswith(".csv"):
        return read_previous_csv(data)
    return read_previous_excel(data)


def _to_result_table(raw: pd.DataFrame, originals: list) -> pd.DataFrame:
    """엑셀·CSV에서 읽은 표를 결과 표 컬럼(COLUMNS)에 맞춘다."""
    mapping = {}  # 표준 컬럼 → 엑셀 컬럼
    for excel_col, orig in zip(raw.columns, originals):
        field = orig if orig in COLUMNS else _ALIAS_LOOKUP.get(_norm_key(orig))
        if not field:
            field = _ALIAS_LOOKUP.get(_norm_key(excel_col))
        if field and field not in mapping:
            mapping[field] = excel_col

    needed = {"사용일자", "상호명", "결제금액"}
    if not needed & set(mapping):
        raise ValueError("사용일자·상호명·결제금액 컬럼을 찾지 못했습니다. 이 서비스에서 받은 파일인지 확인하세요.")

    out = pd.DataFrame({c: raw[mapping[c]] if c in mapping else "" for c in COLUMNS})
    out["사용일자"] = out["사용일자"].map(_clean_date)
    out["결제금액"] = pd.to_numeric(out["결제금액"].map(parse_amount), errors="coerce")
    # 사용자가 정한 구분(행사비 등)도 있으니 바꾸지 않고 그대로 둔다
    out["경비구분"] = out["경비구분"].map(lambda v: _text(v) or "기타")
    out["통화"] = out["통화"].map(lambda v: _text(v).upper() or "KRW")
    out["검토여부"] = out["검토여부"].map(
        lambda v: _text(v) if _text(v) in REVIEW_OPTIONS else (normalize_review(_text(v)) or "검토 불필요")
    )
    for c in ("상호명", "목적", "사유", "파일명"):
        out[c] = out[c].map(_text)

    empty = (out["사용일자"] == "") & (out["상호명"] == "") & out["결제금액"].isna()
    return out[~empty].reset_index(drop=True)