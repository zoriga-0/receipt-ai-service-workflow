"""
excel_builder.py

결과 표를 .xlsx로 만든다. (3번 '엑셀 정리·집계' 역할을 Python이 담당)

시트 구성
  - 경비내역: 영수증 1장당 1행, 검토 필요 행은 노란색 표시
  - 집계: 통화·경비구분별 건수와 금액 합계 (SUMIFS 수식이라
          경비내역 시트에서 값을 고치면 집계도 같이 바뀐다)
"""

import io

import pandas as pd
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from normalize import CATEGORIES

DETAIL_SHEET = "경비내역"
SUMMARY_SHEET = "집계"

_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_REVIEW_FILL = PatternFill("solid", fgColor="FFF2CC")
_TOTAL_FILL = PatternFill("solid", fgColor="DDEBF7")
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_WIDTHS = {"사용일자": 12, "분기": 13, "상호명": 28, "결제금액": 14, "경비구분": 12, "목적": 20,
           "통화": 8, "검토여부": 12, "사유": 50, "파일명": 28, "증빙파일": 36}

META_SHEET = "_columns"  # 숨김 시트: 원래 컬럼 이름 (이전 엑셀 불러오기용)


def summary_categories(df: pd.DataFrame, categories: list[str] | None = None) -> list[str]:
    """집계에 쓸 경비 구분: 사용자 목록 순서대로 + 표에만 있는 구분은 뒤에."""
    base = list(categories or CATEGORIES)
    extra = [c for c in df.get("경비구분", pd.Series(dtype=object)).dropna().unique()
             if c and c not in base]
    return base + sorted(extra)


def build_summary_df(df: pd.DataFrame, categories: list[str] | None = None) -> pd.DataFrame:
    """화면에 보여줄 집계표 (엑셀 집계 시트와 같은 내용)."""
    if df.empty:
        return pd.DataFrame(columns=["통화", "경비구분", "건수", "금액합계"])
    amounts = pd.to_numeric(df["결제금액"], errors="coerce").fillna(0)
    rows = []
    for cur in sorted(c for c in df["통화"].fillna("").unique() if c):
        mask = df["통화"] == cur
        for cat in summary_categories(df, categories):
            m = mask & (df["경비구분"] == cat)
            rows.append({"통화": cur, "경비구분": cat, "건수": int(m.sum()),
                         "금액합계": amounts[m].sum()})
        rows.append({"통화": cur, "경비구분": "합계", "건수": int(mask.sum()),
                     "금액합계": amounts[mask].sum()})
    return pd.DataFrame(rows)


def _style_header(ws, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = _BORDER
    ws.freeze_panes = "A2"


def _write_detail(ws, df: pd.DataFrame):
    cols = list(df.columns)
    _style_header(ws, len(cols))
    review_col = cols.index("검토여부") + 1 if "검토여부" in cols else None
    amount_col = cols.index("결제금액") + 1 if "결제금액" in cols else None

    for r in range(2, len(df) + 2):
        needs_review = review_col and ws.cell(row=r, column=review_col).value == "검토 필요"
        for c in range(1, len(cols) + 1):
            cell = ws.cell(row=r, column=c)
            cell.border = _BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=(cols[c - 1] == "사유"))
            if needs_review:
                cell.fill = _REVIEW_FILL
        if amount_col:
            ws.cell(row=r, column=amount_col).number_format = "#,##0.##"

    for i, name in enumerate(cols, start=1):
        ws.column_dimensions[get_column_letter(i)].width = _WIDTHS.get(name, 14)
    ws.auto_filter.ref = ws.dimensions


def _write_summary(ws, df: pd.DataFrame, categories: list[str] | None = None):
    cols = list(df.columns)
    n = len(df) + 1  # 마지막 데이터 행
    col = {name: get_column_letter(cols.index(name) + 1) for name in cols}
    rng = lambda name: f"'{DETAIL_SHEET}'!${col[name]}$2:${col[name]}${max(n, 2)}"  # noqa: E731

    headers = ["통화", "경비구분", "건수", "금액합계"]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
    _style_header(ws, len(headers))

    r = 2
    currencies = sorted(c for c in df["통화"].fillna("").unique() if c) or ["KRW"]
    for cur in currencies:
        first = r
        for cat in summary_categories(df, categories):
            ws.cell(row=r, column=1, value=cur)
            ws.cell(row=r, column=2, value=cat)
            ws.cell(row=r, column=3,
                    value=f'=COUNTIFS({rng("통화")},A{r},{rng("경비구분")},B{r})')
            ws.cell(row=r, column=4,
                    value=f'=SUMIFS({rng("결제금액")},{rng("통화")},A{r},{rng("경비구분")},B{r})')
            r += 1
        ws.cell(row=r, column=1, value=cur)
        ws.cell(row=r, column=2, value="합계")
        ws.cell(row=r, column=3, value=f"=SUM(C{first}:C{r - 1})")
        ws.cell(row=r, column=4, value=f"=SUM(D{first}:D{r - 1})")
        for c in range(1, 5):
            ws.cell(row=r, column=c).fill = _TOTAL_FILL
            ws.cell(row=r, column=c).font = Font(bold=True)
        r += 1

    for row in ws.iter_rows(min_row=2, max_row=r - 1, max_col=4):
        for cell in row:
            cell.border = _BORDER
        row[3].number_format = "#,##0.##"

    r += 1
    ws.cell(row=r, column=1, value="검토 필요 건수").font = Font(bold=True)
    ws.cell(row=r, column=3, value=f'=COUNTIF({rng("검토여부")},"검토 필요")')
    ws.cell(row=r + 1, column=1, value="전체 영수증 수").font = Font(bold=True)
    ws.cell(row=r + 1, column=3, value=f"=COUNTA({rng('파일명')})")

    for letter, w in zip("ABCD", (10, 12, 10, 16)):
        ws.column_dimensions[letter].width = w


_SUMMARY_COLS = {"통화", "경비구분", "결제금액", "검토여부", "파일명"}


def _write_summary_values(ws, full_df: pd.DataFrame, categories: list[str] | None = None):
    """선택한 컬럼에 집계용 컬럼이 빠졌을 때: 수식 대신 계산된 값으로 집계."""
    summary = build_summary_df(full_df, categories)
    summary = summary[summary["건수"] > 0]
    headers = ["통화", "경비구분", "건수", "금액합계"]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=1, column=c, value=h)
    _style_header(ws, len(headers))
    r = 2
    for _, row in summary.iterrows():
        for c, h in enumerate(headers, start=1):
            v = row[h]
            ws.cell(row=r, column=c, value=v.item() if hasattr(v, "item") else v)
            ws.cell(row=r, column=c).border = _BORDER
        ws.cell(row=r, column=4).number_format = "#,##0.##"
        if row["경비구분"] == "합계":
            for c in range(1, 5):
                ws.cell(row=r, column=c).fill = _TOTAL_FILL
                ws.cell(row=r, column=c).font = Font(bold=True)
        r += 1
    r += 1
    review = int((full_df.get("검토여부") == "검토 필요").sum()) if "검토여부" in full_df else 0
    ws.cell(row=r, column=1, value="검토 필요 건수").font = Font(bold=True)
    ws.cell(row=r, column=3, value=review)
    ws.cell(row=r + 1, column=1, value="전체 영수증 수").font = Font(bold=True)
    ws.cell(row=r + 1, column=3, value=len(full_df))
    for letter, w in zip("ABCD", (10, 12, 10, 16)):
        ws.column_dimensions[letter].width = w


def resolve_headers(columns: list[str], rename: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """
    화면에서 입력한 새 이름을 정리한다.
    반환: ({원래 이름: 엑셀 이름}, 중복된 엑셀 이름 목록)
    빈칸이면 원래 이름을 쓴다.
    """
    headers = {}
    for col in columns:
        new = str(rename.get(col) or "").strip()
        headers[col] = new or col
    seen, dup = set(), []
    for name in headers.values():
        if name in seen and name not in dup:
            dup.append(name)
        seen.add(name)
    return headers, dup


def dataframe_to_excel_bytes(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    include_summary: bool = True,
    headers: dict[str, str] | None = None,
    categories: list[str] | None = None,
) -> bytes:
    """
    df: 전체 결과(화면에서 수정한 값 포함)
    columns: 엑셀에 넣을 컬럼 (순서대로). None이면 전체
    include_summary: 집계 시트 포함 여부
    headers: {원래 컬럼명: 엑셀에 표시할 이름} (바꾸지 않은 컬럼은 생략 가능)
    """
    columns = columns or [c for c in df.columns if not str(c).startswith("_")]
    export_df = df[columns]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name=DETAIL_SHEET)
        _write_detail(writer.sheets[DETAIL_SHEET], export_df)
        if headers:  # 서식·수식은 원래 이름 기준으로 만든 뒤, 제목 칸 글자만 바꾼다
            ws_detail = writer.sheets[DETAIL_SHEET]
            for i, name in enumerate(export_df.columns, start=1):
                ws_detail.cell(row=1, column=i, value=headers.get(name) or name)
        if include_summary and {"통화", "경비구분", "결제금액"} <= set(df.columns):
            ws = writer.book.create_sheet(SUMMARY_SHEET)
            if _SUMMARY_COLS <= set(export_df.columns):
                _write_summary(ws, export_df, categories)  # 수식: 경비내역을 고치면 같이 바뀜
            else:
                _write_summary_values(ws, df, categories)  # 값: 선택에서 빠진 컬럼이 있을 때
        meta = writer.book.create_sheet(META_SHEET)
        for i, name in enumerate(export_df.columns, start=1):
            meta.cell(row=1, column=i, value=name)
        meta.sheet_state = "hidden"
    output.seek(0)
    return output.getvalue()



def dataframe_to_csv_bytes(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    """
    결과 표를 CSV로 만든다. (표 하나만 담기므로 집계 시트·노란색 표시는 없다)
    UTF-8 BOM을 붙여서 엑셀에서 열어도 한글이 깨지지 않는다.
    """
    columns = columns or [c for c in df.columns if not str(c).startswith("_")]
    out = df[columns].copy()
    if "결제금액" in out.columns:  # 28000.0 → 28000
        out["결제금액"] = out["결제금액"].map(
            lambda v: "" if pd.isna(v) else (int(v) if float(v).is_integer() else v)
        )
    if headers:
        out = out.rename(columns={c: headers.get(c) or c for c in columns})
    return out.to_csv(index=False).encode("utf-8-sig")