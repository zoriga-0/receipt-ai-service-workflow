import re

import pandas as pd
import streamlit as st

import config
from excel_builder import (
    build_summary_df,
    dataframe_to_csv_bytes,
    dataframe_to_excel_bytes,
    resolve_headers,
)
from media import build_zip, evidence_filename, make_preview, prepare_upload
from normalize import (
    CATEGORIES,
    CATEGORY_PRESETS,
    COLUMNS,
    REVIEW_OPTIONS,
    normalize_date,
    parse_amount,
    parse_categories,
)
from records import add_quarter, detect_duplicates, read_previous_file
from service import process_receipts
from ui_extras import AnalysisProgress, is_production, leave_guard

try:  # 드래그로 컬럼 순서를 바꾸는 컴포넌트 (pip install streamlit-sortables)
    from streamlit_sortables import sort_items
except ImportError:
    sort_items = None

st.set_page_config(page_title="영수증 콜렉터", page_icon="🧾", layout="wide")

# 앱처럼 보이게: Streamlit 메뉴·상단 장식 숨기기
st.markdown(
    """
    <style>
    #MainMenu, footer,
    [data-testid="stToolbar"], [data-testid="stDecoration"] {visibility: hidden;}
    header[data-testid="stHeader"] {background: transparent;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("영수증 경비 정리 서비스")
st.write("영수증을 여러 장 올리면 1장당 1행으로 정리하고 엑셀로 내려받을 수 있습니다.")

CURRENCIES = ["KRW", "USD", "JPY", "EUR", "CNY", "GBP"]


@st.cache_data(show_spinner=False, max_entries=200)
def cached_preview(name: str, data: bytes):
    return make_preview(name, data)


def text(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


##################################################
# 설정 확인
##################################################

# https(배포 사이트)면 개발용 정보(환경변수 이름, MOCK 안내, Agent 원본 응답)를 숨긴다.
PROD = is_production()

missing = config.missing_settings()
if missing:
    if PROD:
        st.error("지금은 영수증 분석을 할 수 없습니다. 잠시 후 다시 시도해주세요.")
    else:
        st.error(
            "다음 환경변수가 비어 있어 영수증 분석을 실행할 수 없습니다: "
            + ", ".join(missing)
            + "\n\n로컬은 .env 파일, Railway는 Variables 탭에 넣은 뒤 다시 실행하세요."
        )
if config.USE_MOCK and not PROD:
    st.info("USE_MOCK=1 상태입니다. Upstage API를 호출하지 않고 가짜 결과를 보여줍니다.")

##################################################
# 업로드
##################################################

uploaded_files = st.file_uploader(
    "영수증 사진 올리기 (사진·PDF·아이폰 HEIC)",
    type=["png", "jpg", "jpeg", "pdf", "heic", "heif"],
    accept_multiple_files=True,
)
n_files = len(uploaded_files or [])

# 지출 목적과 경비 구분 목록: 목적을 적거나 목록을 바꾸면 Solar가 목적에 맞게 다시 분류한다
purpose = st.text_input(
    "이번 영수증은 무엇을 위한 지출인가요? (선택)",
    placeholder="예: 11월 MT 장보기, 동아리 정기 회의",
    max_chars=100,
).strip()
with st.expander("경비 구분 목록 바꾸기"):
    preset = st.selectbox("기본 목록", list(CATEGORY_PRESETS), key="cat_preset")
    cat_text = st.text_input(
        "구분 목록 (쉼표로 나눠 고칠 수 있어요. '기타'는 항상 들어가요)",
        value=", ".join(CATEGORY_PRESETS[preset]),
        key=f"cat_text_{preset}",
    )
categories = parse_categories(cat_text)
st.caption("경비 구분: " + " · ".join(categories))

# 버튼 1: 새 영수증만 분석
run_new = st.button(
    f"영수증 {n_files}장 분석하기" if n_files else "영수증을 올리면 분석할 수 있어요",
    key="run_new",
    type="primary",
    disabled=not n_files or bool(missing),
)
# 버튼 2: 지난번 파일과 합쳐서 분석 (필요한 사람만 펼쳐서 쓴다)
with st.expander("지난번 엑셀·CSV에 이어서 정리하기"):
    previous_xlsx = st.file_uploader("이 서비스에서 받았던 엑셀 또는 CSV", type=["xlsx", "csv"])
    if previous_xlsx and n_files:
        merge_label = f"이전 기록 + 영수증 {n_files}장 합쳐서 분석"
    elif previous_xlsx:
        merge_label = "이전 기록만 불러오기"
    else:
        merge_label = "엑셀이나 CSV를 올리면 이어서 정리할 수 있어요"
    run_merge = st.button(
        merge_label,
        key="run_merge",
        disabled=not previous_xlsx or bool(missing and n_files),
    )

# 올린 파일이 바뀌면 이전 결과를 지운다.
upload_key = tuple((f.name, f.size) for f in (uploaded_files or [])) + (
    (previous_xlsx.name, previous_xlsx.size) if previous_xlsx else (),
)
if st.session_state.get("upload_key") != upload_key:
    st.session_state.upload_key = upload_key
    st.session_state.pop("work", None)



# 파일을 올렸거나, 분석 중이거나, 결과가 있으면 새로고침·창 닫기 때 경고를 띄운다.
# 분석 전에 그려야 분석이 도는 동안에도 켜져 있다.
leave_guard(bool(n_files or previous_xlsx or st.session_state.get("work")))

if run_new or run_merge:
    # 1) 이전 엑셀 (버튼 2를 눌렀을 때만)
    prev_df = pd.DataFrame(columns=COLUMNS)
    if run_merge and previous_xlsx:
        try:
            prev_df = read_previous_file(previous_xlsx.name, previous_xlsx.getvalue())
        except Exception as e:  # noqa: BLE001
            st.error(f"이전 파일을 읽지 못했습니다: {e}")
            st.stop()

    # 2) 새 영수증 (HEIC → JPG)
    prepared, prep_errors = [], []
    for f in uploaded_files or []:
        name, data, err = prepare_upload(f.name, f.getvalue())
        (prep_errors.append(err) if err else prepared.append((name, data)))

    new_df, details, originals = pd.DataFrame(columns=COLUMNS + ["_id"]), [], {}
    elapsed = None
    if prepared:
        tracker = AnalysisProgress(len(prepared))
        context = {"purpose": purpose, "categories": categories}
        new_df, details, originals = process_receipts(prepared, tracker.update, context)
        elapsed = tracker.finish(len(prepared))

    # 3) 합치고 중복 확인 (이전 엑셀 행은 표시하지 않고 새 영수증만 표시)
    combined = pd.concat([prev_df.assign(_id=None), new_df], ignore_index=True)
    combined["결제금액"] = pd.to_numeric(combined["결제금액"], errors="coerce")
    mark = [False] * len(prev_df) + [True] * len(new_df)
    combined, dup_count = detect_duplicates(combined, mark)

    st.session_state.work = {
        "df": add_quarter(combined)[COLUMNS + ["_id"]],
        "details": details,
        "originals": originals,
        "ver": st.session_state.get("work", {}).get("ver", 0) + 1,
        "prev_count": len(prev_df),
        "dup_count": dup_count,
        "prep_errors": prep_errors,
        "elapsed": elapsed,
        "n_new": len(prepared),
        "categories": categories,
    }

##################################################
# 결과
##################################################

work = st.session_state.get("work")
if work:
    df, details, originals, ver = work["df"], work["details"], work["originals"], work["ver"]

    for err in work["prep_errors"]:
        st.error(err)
    failed = [d for d in details if d["errors"]]
    if failed:
        where = "'검토 필요' 사유" if PROD else "아래 '분석 상세'"
        st.warning(f"{len(failed)}개 파일에서 분석 오류가 있었습니다. {where}를 확인하세요.")
    if work.get("elapsed") and work.get("n_new"):
        st.caption(
            f"분석 시간 {work['elapsed']:.0f}초 · 영수증 {work['n_new']}장 · "
            f"장당 평균 {work['elapsed'] / work['n_new']:.1f}초"
        )
    if work["prev_count"]:
        st.info(f"이전 기록에서 {work['prev_count']}건을 불러와 새 영수증과 합쳤습니다.")
    if work["dup_count"]:
        st.warning(f"날짜·상호·금액이 같은 중복 의심 영수증이 {work['dup_count']}건 있습니다.")

    currency_options = sorted(set(CURRENCIES) | {c for c in df["통화"].dropna() if c})
    # 경비 구분 선택지: 분석할 때 정한 목록 + 이전 기록에만 있던 구분
    cat_options = list(work.get("categories") or CATEGORIES)
    cat_options += sorted({c for c in df["경비구분"].dropna() if c and c not in cat_options})

    tab_review, tab_all = st.tabs(["검토 필요 확인", "전체 결과 표"])

    # ---------- 전체 결과 표 (직접 수정) ----------
    # 검토 탭이 이 표의 최신 값을 써야 하므로 코드는 이 탭을 먼저 실행한다.
    with tab_all:
        st.caption(
            "셀을 더블클릭해 값을 고칠 수 있습니다. 맨 아래 빈 줄에서 행을 추가하고, "
            "왼쪽 체크박스로 행을 골라 삭제할 수 있습니다. 분기는 사용일자로 자동 계산됩니다."
        )
        edited = st.data_editor(
            df,
            key=f"editor_{ver}",
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "_id": None,  # 숨김: 원본 사진 연결용
                "사용일자": st.column_config.TextColumn(
                    "사용일자", help="YYYY-MM-DD 형식", validate=r"^(\d{4}-\d{2}-\d{2})?$"
                ),
                "분기": st.column_config.TextColumn("분기", disabled=True),
                "결제금액": st.column_config.NumberColumn(
                    "결제금액", format="localized", min_value=0, step=1
                ),
                "경비구분": st.column_config.SelectboxColumn("경비구분", options=cat_options),
                "목적": st.column_config.TextColumn("목적"),
                "통화": st.column_config.SelectboxColumn("통화", options=currency_options),
                "검토여부": st.column_config.SelectboxColumn("검토여부", options=REVIEW_OPTIONS),
                "사유": st.column_config.TextColumn("사유", width="large"),
                "파일명": st.column_config.TextColumn("파일명", disabled=True),
            },
        )
        edited = add_quarter(edited.reset_index(drop=True))
        edited["결제금액"] = pd.to_numeric(edited["결제금액"], errors="coerce")

    # ---------- 검토 필요 확인 (사진 보며 수정) ----------
    with tab_review:
        pending = edited.index[edited["검토여부"] == "검토 필요"].tolist()
        if not pending:
            st.success("검토가 필요한 영수증이 없습니다. 엑셀을 내려받으셔도 됩니다.")
        else:
            st.caption(f"남은 검토 {len(pending)}건 · '확인 완료'를 누르면 '검토 완료'로 바뀌고 다음 건으로 넘어갑니다.")

            def label(i):
                r = edited.loc[i]
                amt = f"{r['결제금액']:,.0f}" if pd.notna(r["결제금액"]) else "금액 없음"
                return f"{text(r['파일명']) or '(직접 추가한 행)'} · {text(r['상호명']) or '상호 없음'} · {amt}"

            pick = st.selectbox("확인할 영수증", pending, format_func=label, key=f"pick_{ver}")
            row = edited.loc[pick]
            left, right = st.columns([1, 1])

            with left:
                rid = row.get("_id")
                if isinstance(rid, str) and rid in originals:
                    src_name, src_data = originals[rid]
                    preview = cached_preview(src_name, src_data)
                    if preview:
                        st.image(preview, caption=src_name)
                    else:
                        st.info("미리보기를 만들 수 없는 파일입니다. 내려받아 확인하세요.")
                        st.download_button("원본 내려받기", src_data, file_name=src_name)
                else:
                    st.info("원본 사진이 없는 행입니다. (이전 엑셀에서 불러왔거나 직접 추가한 행)")

            with right:
                st.markdown("**검토 사유**")
                st.write(text(row["사유"]) or "(사유 없음)")
                with st.form(f"review_{ver}_{pick}"):
                    f_date = st.text_input("사용일자 (YYYY-MM-DD)", value=text(row["사용일자"]))
                    f_store = st.text_input("상호명", value=text(row["상호명"]))
                    f_amount = st.text_input(
                        "결제금액",
                        value="" if pd.isna(row["결제금액"]) else f"{row['결제금액']:,.0f}",
                    )
                    cat_now = text(row["경비구분"])
                    f_cat = st.selectbox(
                        "경비구분", cat_options,
                        index=cat_options.index(cat_now) if cat_now in cat_options else len(cat_options) - 1,
                    )
                    f_purpose = st.text_input("목적", value=text(row["목적"]))
                    cur_now = text(row["통화"]) or "KRW"
                    f_cur = st.selectbox(
                        "통화", currency_options,
                        index=currency_options.index(cur_now) if cur_now in currency_options else 0,
                    )
                    f_memo = st.text_area("사유 (메모)", value=text(row["사유"]), height=90)
                    b1, b2 = st.columns(2)
                    done = b1.form_submit_button("확인 완료", type="primary")
                    keep = b2.form_submit_button("수정만 저장")

                if done or keep:
                    date_ok = normalize_date(f_date) if f_date.strip() else ""
                    if f_date.strip() and not re.match(r"^\d{4}-\d{2}-\d{2}$", date_ok):
                        st.error("사용일자는 2022-02-21 같은 형식으로 입력해주세요.")
                    else:
                        new_df = edited.copy()
                        new_df.at[pick, "사용일자"] = date_ok
                        new_df.at[pick, "상호명"] = f_store.strip()
                        amount = parse_amount(f_amount)
                        new_df.at[pick, "결제금액"] = amount if amount else float("nan")
                        new_df.at[pick, "경비구분"] = f_cat
                        new_df.at[pick, "목적"] = f_purpose.strip()                        
                        new_df.at[pick, "통화"] = f_cur
                        new_df.at[pick, "사유"] = f_memo.strip()
                        if done:
                            new_df.at[pick, "검토여부"] = "검토 완료"
                        work["df"] = add_quarter(new_df)[COLUMNS + ["_id"]]
                        work["ver"] = ver + 1
                        st.rerun()

    # ---------- 요약 ----------
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("영수증", f"{len(edited)}장")
    c2.metric("검토 필요", f"{int((edited['검토여부'] == '검토 필요').sum())}건")
    c3.metric("검토 완료", f"{int((edited['검토여부'] == '검토 완료').sum())}건")
    krw = edited.loc[edited["통화"] == "KRW", "결제금액"].sum()
    c4.metric("KRW 합계", f"{krw:,.0f}원")

    # ---------- 내보내기 (엑셀 / CSV) ----------
    st.subheader("내보내기")

    # (1) 분기 고르기
    quarters = sorted({q for q in edited["분기"] if q})
    has_unknown = bool((edited["분기"] == "").any())
    q_options = quarters + (["날짜 없음"] if has_unknown else [])
    picked_q = st.multiselect("내보낼 분기", q_options, default=q_options) if len(q_options) > 1 else q_options
    mask = edited["분기"].isin(picked_q) | (("날짜 없음" in picked_q) & (edited["분기"] == ""))
    export_rows = edited[mask].reset_index(drop=True)

    summary_df = build_summary_df(export_rows, cat_options)
    st.dataframe(summary_df[summary_df["건수"] > 0], hide_index=True)

    # (2) 컬럼 고르기·순서 바꾸기
    if sort_items is not None:
        st.caption("컬럼을 끌어서 순서를 바꾸고, 엑셀에서 뺄 컬럼은 아래 '제외' 칸으로 옮기세요.")
        boxes = sort_items(
            [
                {"header": "엑셀에 넣을 컬럼 (왼쪽부터 순서대로)", "items": list(COLUMNS)},
                {"header": "제외", "items": []},
            ],
            multi_containers=True,
            key="column_sorter",
        )
        selected_cols = [c for c in boxes[0]["items"] if c in COLUMNS]
    else:
        selected_cols = st.multiselect(
            "엑셀에 넣을 컬럼 (고른 순서대로 들어갑니다)", options=COLUMNS, default=COLUMNS
        )

    # (3) 컬럼 이름 바꾸기
    with st.expander("엑셀 컬럼 이름 바꾸기"):
        st.caption("오른쪽 칸을 더블클릭해 고치세요. 비워두면 원래 이름을 씁니다.")
        rename_df = st.data_editor(
            pd.DataFrame({"원래 이름": COLUMNS, "엑셀에 표시할 이름": COLUMNS}),
            key="rename_editor",
            hide_index=True,
            width="stretch",
            column_config={"원래 이름": st.column_config.TextColumn(disabled=True)},
        )
    rename_map = dict(zip(rename_df["원래 이름"], rename_df["엑셀에 표시할 이름"]))

    # (4) 옵션
    col_a, col_b, col_c = st.columns([2, 1, 1])
    file_stem = col_a.text_input("파일 이름", value="expense_result")
    include_summary = col_b.checkbox("집계 시트 포함", value=True, help="엑셀 파일에만 들어가요.")
    want_zip = col_c.checkbox(
        "증빙 사진 zip도 받기",
        value=False,
        help="엑셀 행 번호에 맞춰 사진 이름을 바꿔 묶어줍니다. 엑셀에 '증빙파일' 컬럼이 추가됩니다.",
    )

    zip_items = []
    if want_zip:
        export_rows = export_rows.copy()
        names = []
        for no, (_, r) in enumerate(export_rows.iterrows(), start=1):
            rid = r.get("_id")
            if isinstance(rid, str) and rid in originals:
                src_name, src_data = originals[rid]
                zname = evidence_filename(no, r["사용일자"], r["상호명"], src_name)
                zip_items.append((zname, src_data))
                names.append(zname)
            else:
                names.append("")
        export_rows["증빙파일"] = names
        selected_cols = selected_cols + ["증빙파일"]

    headers, duplicated = resolve_headers(selected_cols, rename_map)
    if selected_cols:
        st.caption("엑셀 순서: " + "  →  ".join(headers[c] for c in selected_cols))

    if export_rows.empty:
        st.info("선택한 분기에 해당하는 영수증이 없습니다.")
    elif not [c for c in selected_cols if c != "증빙파일"]:
        st.info("엑셀에 넣을 컬럼을 하나 이상 남겨주세요.")
    elif duplicated:
        st.error("엑셀 컬럼 이름이 겹칩니다: " + ", ".join(duplicated))
    else:
        safe_stem = re.sub(r'[\\/:*?"<>|]', "_", file_stem.strip()) or "expense_result"
        pending_left = int((export_rows["검토여부"] == "검토 필요").sum())

        # 파일 형식은 다운로드 버튼 바로 옆에서 고른다
        f1, f2, f3 = st.columns([1.4, 1, 1], vertical_alignment="bottom")
        out_format = f1.radio(
            "파일 형식", ["엑셀 (.xlsx)", "CSV (.csv)"], horizontal=True, key="out_format"
        )
        as_csv = out_format.startswith("CSV")
        if as_csv:
            file_bytes = dataframe_to_csv_bytes(export_rows, columns=selected_cols, headers=headers)
            file_label, file_ext, file_mime = "CSV", "csv", "text/csv"
        else:
            file_bytes = dataframe_to_excel_bytes(
                export_rows,
                columns=selected_cols,
                include_summary=include_summary,
                headers=headers,
                categories=cat_options,
            )
            file_label, file_ext = "엑셀", "xlsx"
            file_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        f2.download_button(
            label=f"{file_label} 다운로드 ({len(export_rows)}건)",
            data=file_bytes,
            file_name=f"{safe_stem}.{file_ext}",
            mime=file_mime,
            type="primary",
        )
        if want_zip:
            if zip_items:
                f3.download_button(
                    label=f"증빙 사진 zip ({len(zip_items)}장)",
                    data=build_zip(zip_items),
                    file_name=f"{safe_stem}_증빙.zip",
                    mime="application/zip",
                )
            else:
                f3.info("묶을 원본 사진이 없습니다.")

        notes = []
        if pending_left:
            notes.append(
                f"아직 검토 필요 {pending_left}건이 남아 있어요"
                + ("" if as_csv else " (엑셀에서 노란색으로 표시)")
            )
        if as_csv:
            notes.append("CSV에는 집계 시트와 노란색 표시가 빠져요")
        if notes:
            st.caption(" · ".join(notes))

    # ---------- 분석 상세 (개발 환경에서만) ----------
    if details and not PROD:
        with st.expander("분석 상세 (Agent 원본 응답·오류)"):
            for d in details:
                st.markdown(f"**{d['파일명']}**")
                for err in d["errors"]:
                    st.error(err)
                for note in d.get("notes", []):
                    st.warning(note)
                col_x, col_y, col_z = st.columns(3)
                col_x.caption("1번 추출 Agent 응답")
                col_x.code(d["extract_raw"] or "(없음)", language="json")
                col_y.caption("2번 검토 Agent 응답")
                col_y.code(d["review_raw"] or "(없음)", language="json")
                col_z.caption("3번 검증 Agent 응답")
                col_z.code(d.get("verify_raw") or "(없음)", language="json")
                if d.get("purpose_raw"):
                    st.caption("목적 반영 분류 (Solar) 응답")
                    st.code(d["purpose_raw"], language="json")