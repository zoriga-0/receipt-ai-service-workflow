import re

import pandas as pd
import streamlit as st

import config
from auth import access_token, gate
from drive_store import FOLDER_NAME, RECORD_FILE, DriveError, get_folder, load_records, save_records
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
from api_client import run_via_api, server_status
from service import process_receipts
from session_keep import restore, sync
from theme import apply_theme
from ui_extras import AnalysisProgress, is_production, leave_guard

st.set_page_config(page_title="영수증 콜렉터", page_icon="🧾", layout="wide")
apply_theme()  # 디자인 (theme.py)

head_left, head_right = st.columns([4, 1], vertical_alignment="center")
head_left.markdown('<div class="rc-brand">영수증 콜렉터</div>', unsafe_allow_html=True)

# 들어오는 문: 구글 로그인(+비상용 비밀번호). 주소를 아는 누구나 Upstage 사용량을 쓰지 못하게 막는다
user = gate()

# 구글로 로그인했으면 내 드라이브의 '영수증 콜렉터' 폴더를 찾거나 만든다 (권한 확인 겸)
drive_folder, drive_msg = None, ""
if user.get("email"):
    cached = st.session_state.get("drive_folder")
    if cached and cached[0] == user["email"]:
        drive_folder = cached[1]
    elif not access_token():
        drive_msg = '드라이브 토큰이 없어요. secrets.toml [auth]에 expose_tokens = ["access"]를 넣어 주세요.'
    else:
        try:
            drive_folder = get_folder(access_token())
            st.session_state.drive_folder = (user["email"], drive_folder)
        except DriveError as e:
            drive_msg = str(e)
    with head_right.popover(user.get("name") or user["email"], width="stretch", icon=":material/person:"):
        st.caption(user["email"])
        if drive_folder:
            st.caption(f"저장 위치: 내 드라이브 / {FOLDER_NAME} / {RECORD_FILE}")
        elif drive_msg:
            st.warning(drive_msg)
        if st.button("로그아웃", width="stretch"):
            st.session_state.pop("drive_folder", None)
            st.logout()
drive_ready = bool(drive_folder)

# 새로고침했으면 보관해 둔 분석 결과를 되살린다 (Mac 메모리, 1시간)
owner = user.get("email", "")
restore(owner)


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
            + "\n\n.env 파일에 넣은 뒤 다시 실행하세요."
        )
if config.USE_MOCK and not PROD:
    st.info("USE_MOCK=1 상태입니다. Upstage API를 호출하지 않고 가짜 결과를 보여줍니다.")

##################################################
# 업로드
##################################################

if not st.session_state.get("work"):
    st.markdown(
        '<div class="rc-hero">영수증 사진을 올리면<br><span>정산용 엑셀로 정리해 드려요</span></div>',
        unsafe_allow_html=True,
    )

with st.container(key="upload_card"):
    uploaded_files = st.file_uploader(
        "영수증 사진",
        type=["png", "jpg", "jpeg", "pdf", "heic", "heif"],
        accept_multiple_files=True,
    )
    n_files = len(uploaded_files or [])

    # 지출 목적과 경비 구분 목록: 목적을 적거나 목록을 바꾸면 Solar가 목적에 맞게 다시 분류한다
    p1, p2 = st.columns([3, 1.2], vertical_alignment="bottom")
    purpose = p1.text_input(
        "어디에 쓴 돈인가요? (선택)",
        placeholder="예: 11월 MT 장보기",
        max_chars=100,
        help="적은 목적은 이번에 올린 영수증 전체에 적용돼요. 목적이 다른 영수증은 나눠서 분석해 주세요.",
    ).strip()
    with p2.popover("경비 구분", width="stretch", icon=":material/tune:"):
        preset = st.selectbox("기본 목록", list(CATEGORY_PRESETS), key="cat_preset")
        cat_text = st.text_input(
            "구분 목록",
            value=", ".join(CATEGORY_PRESETS[preset]),
            key=f"cat_text_{preset}",
            help="쉼표로 나눠 고칠 수 있어요. '기타'는 항상 들어가요.",
        )
        st.caption(" · ".join(parse_categories(cat_text)))
    categories = parse_categories(cat_text)

    # 버튼 1: 새 영수증만 분석
    run_new = st.button(
        f"영수증 {n_files}장 분석하기" if n_files else "분석하기",
        key="run_new",
        type="primary",
        width="stretch",
        disabled=not n_files or bool(missing),
    )

# 버튼 2: 지난 기록과 합쳐서 분석 (필요한 사람만 펼쳐서 쓴다)
with st.expander("지난 기록에 이어서 정리하기"):
    use_drive = drive_ready and st.checkbox(
        f"내 구글 드라이브의 {RECORD_FILE} 불러오기", value=True, key="use_drive"
    )
    previous_xlsx = st.file_uploader(
        "받아 두었던 엑셀·CSV" if drive_ready else "이 서비스에서 받았던 엑셀·CSV",
        type=["xlsx", "csv"],
    )
    has_prev = bool(previous_xlsx or use_drive)
    if has_prev and n_files:
        merge_label = f"지난 기록 + 영수증 {n_files}장 합쳐서 분석"
    elif has_prev:
        merge_label = "지난 기록만 불러오기"
    else:
        merge_label = "지난 기록을 고르면 이어서 정리할 수 있어요"
    run_merge = st.button(
        merge_label,
        key="run_merge",
        width="stretch",
        disabled=not has_prev or bool(missing and n_files),
    )

# 올린 파일이 바뀌면 이전 결과를 지운다.
upload_key = tuple((f.name, f.size) for f in (uploaded_files or [])) + (
    (previous_xlsx.name, previous_xlsx.size) if previous_xlsx else (),
) + (("drive",) if use_drive else ())
if st.session_state.pop("restored", False):
    # 새로고침으로 되살린 결과: 올린 파일 목록은 비어 있지만 결과는 지우지 않는다
    st.session_state.upload_key = upload_key
elif st.session_state.get("upload_key") != upload_key:
    st.session_state.upload_key = upload_key
    st.session_state.pop("work", None)


# 올리기만 하고 아직 분석 결과가 없을 때(분석 중 포함) 새로고침·창 닫기 경고를 띄운다.
# 분석 결과는 새로고침해도 되살아나므로 경고하지 않는다.
# 분석 전에 그려야 분석이 도는 동안에도 켜져 있다.
leave_guard(bool(n_files or previous_xlsx) and not st.session_state.get("work"))

if (run_new or run_merge) and config.API_URL and n_files:
    # 서버를 쓰는 설정이면, 분석 전에 서버가 켜져 있는지 먼저 확인한다
    alive, why = server_status()
    if not alive:
        st.error(why if not PROD else "분석 서버가 꺼져 있어요. 잠시 후 다시 시도해주세요.")
        st.stop()

if run_new or run_merge:
    # 1) 지난 기록: 내 드라이브 + 올린 파일 (버튼 2를 눌렀을 때만)
    prev_parts, prev_notes, drive_info = [], [], {}
    if run_merge and use_drive:
        try:
            drive_bytes, drive_meta = load_records(access_token(), drive_folder)
            drive_df = (
                read_previous_file(RECORD_FILE, drive_bytes) if drive_bytes else pd.DataFrame(columns=COLUMNS)
            )
        except DriveError as e:
            st.error(str(e))
            st.stop()
        except Exception as e:  # noqa: BLE001
            st.error(f"드라이브의 {RECORD_FILE}를 읽지 못했어요: {e}")
            st.stop()
        prev_parts.append(drive_df)
        prev_notes.append(f"내 드라이브 {len(drive_df)}건")
        drive_info = {  # loaded가 있어야 '전체 저장'을 한다 (드라이브 기록을 모르고 덮어쓰지 않게)
            "loaded": True,
            "modified": drive_meta["modifiedTime"] if drive_meta else None,
            "link": drive_meta.get("webViewLink") if drive_meta else None,
        }
    if run_merge and previous_xlsx:
        try:
            file_df = read_previous_file(previous_xlsx.name, previous_xlsx.getvalue())
        except Exception as e:  # noqa: BLE001
            st.error(f"이전 파일을 읽지 못했어요: {e}")
            st.stop()
        prev_parts.append(file_df)
        prev_notes.append(f"올린 파일 {len(file_df)}건")
    prev_df = (
        pd.concat(prev_parts, ignore_index=True)[COLUMNS] if prev_parts else pd.DataFrame(columns=COLUMNS)
    )

    # 2) 새 영수증 (HEIC → JPG)
    prepared, prep_errors = [], []
    for f in uploaded_files or []:
        name, data, err = prepare_upload(f.name, f.getvalue())
        # (한 줄짜리 식으로 쓰면 Streamlit이 결과 None을 화면에 찍어서 if문으로 쓴다)
        if err:
            prep_errors.append(err)
        else:
            prepared.append((name, data))

    new_df, details, originals = pd.DataFrame(columns=COLUMNS + ["_id"]), [], {}
    elapsed = None
    if prepared:
        tracker = AnalysisProgress(len(prepared))
        context = {"purpose": purpose, "categories": categories}
        runner = run_via_api if config.API_URL else None  # 서버가 있으면 서버로, 없으면 직접
        new_df, details, originals = process_receipts(prepared, tracker.update, context, runner)
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
        "prev_notes": prev_notes,
        "drive": drive_info,
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
sync(owner)
if work:
    df, details, originals, ver = work["df"], work["details"], work["originals"], work["ver"]

    st.markdown('<div class="rc-section">분석 결과</div>', unsafe_allow_html=True)
    # 요약 숫자는 표에서 고친 값까지 반영해야 해서, 자리만 먼저 잡고 아래에서 채운다
    summary_slot = st.container()

    for err in work["prep_errors"]:
        st.error(err)
    failed = [d for d in details if d["errors"]]
    if failed:
        where = "'검토 필요' 사유" if PROD else "아래 '분석 상세'"
        st.warning(f"{len(failed)}개 파일에서 분석 오류가 있었어요. {where}를 확인하세요.")
    if work["dup_count"]:
        st.warning(f"날짜·상호·금액이 같은 중복 의심 영수증이 {work['dup_count']}건 있어요.")
    info = []
    if work["prev_count"]:
        info.append(f"지난 기록 {work['prev_count']}건 포함 ({', '.join(work.get('prev_notes') or [])})")
    if work.get("elapsed") and work.get("n_new"):
        info.append(
            f"새 영수증 {work['n_new']}장 · {work['elapsed']:.0f}초 (장당 {work['elapsed'] / work['n_new']:.1f}초)"
        )

    currency_options = sorted(set(CURRENCIES) | {c for c in df["통화"].dropna() if c})
    # 경비 구분 선택지: 분석할 때 정한 목록 + 이전 기록에만 있던 구분
    cat_options = list(work.get("categories") or CATEGORIES)
    cat_options += sorted({c for c in df["경비구분"].dropna() if c and c not in cat_options})

    # 탭 이름의 건수는 직전 화면 기준 (표에서 고치면 다음 화면에 반영)
    base = work.get("latest") if work.get("latest") is not None else df
    n_review = int((base["검토여부"] == "검토 필요").sum())
    tab_review, tab_all, tab_export = st.tabs(
        [f"검토 필요 {n_review}" if n_review else "검토 필요", f"전체 {len(base)}", "내보내기"]
    )

    # ---------- 전체 결과 (직접 수정) ----------
    # 다른 탭과 요약 숫자가 이 표의 최신 값을 써야 하므로 코드는 이 탭을 먼저 실행한다.
    with tab_all:
        st.caption("칸을 두 번 눌러 고쳐요. 맨 아래 빈 줄에 행을 추가할 수 있어요.")
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
                    "결제금액", format="localized", min_value=0, step=0.01  # 달러 센트까지
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
        work["latest"] = edited.reindex(columns=COLUMNS + ["_id"])  # 새로고침 뒤 되살릴 값

    # ---------- 요약 (맨 위 자리에 채우기) ----------
    n_pending = int((edited["검토여부"] == "검토 필요").sum())
    with summary_slot:
        krw = edited.loc[edited["통화"] == "KRW", "결제금액"].sum()
        others = (
            edited[(edited["통화"] != "KRW") & edited["통화"].notna() & (edited["통화"] != "")]
            .groupby("통화")["결제금액"].sum()
        )
        other_txt = " · ".join(f"{c} {v:,.2f}" for c, v in others.items() if v)
        n_done = int((edited["검토여부"] == "검토 완료").sum())
        st.markdown(
            f'''<div class="rc-summary">
<div class="rc-total"><small>합계</small><b>{krw:,.0f}원</b>{f"<em>+ {other_txt}</em>" if other_txt else ""}</div>
<div class="rc-stats">
<div>영수증<b>{len(edited)}</b></div>
<div class="{"warn" if n_pending else ""}">검토 필요<b>{n_pending}</b></div>
<div>검토 완료<b>{n_done}</b></div>
</div>
</div>'''
            + (f'<div class="rc-meta">{" · ".join(info)}</div>' if info else ""),
            unsafe_allow_html=True,
        )

    # ---------- 검토 필요 (사진 보며 수정) ----------
    with tab_review:
        pending = edited.index[edited["검토여부"] == "검토 필요"].tolist()
        if not pending:
            st.success("검토할 영수증이 없어요. '내보내기' 탭에서 파일을 받으세요.")
        else:
            def label(i):
                r = edited.loc[i]
                amt = f"{r['결제금액']:,.0f}" if pd.notna(r["결제금액"]) else "금액 없음"
                return f"{text(r['상호명']) or '상호 없음'} · {amt} · {text(r['파일명']) or '직접 추가한 행'}"

            pick = st.selectbox(
                f"확인할 영수증 (남은 {len(pending)}건)", pending, format_func=label, key=f"pick_{ver}"
            )
            row = edited.loc[pick]
            rid = row.get("_id")
            has_photo = isinstance(rid, str) and rid in originals

            if has_photo:
                left, right = st.columns([1, 1], gap="large")
                with left:
                    src_name, src_data = originals[rid]
                    preview = cached_preview(src_name, src_data)
                    if preview:
                        st.image(preview, caption=src_name)
                    else:
                        st.caption("미리보기를 만들 수 없는 파일이에요.")
                        st.download_button("원본 내려받기", src_data, file_name=src_name)
            else:
                right = st.container()

            with right:
                st.warning(text(row["사유"]) or "사유가 적혀 있지 않아요.")
                if not has_photo:
                    st.caption("원본 사진이 없는 행이에요. (이전 기록에서 불러왔거나 직접 추가한 행)")
                with st.form(f"review_{ver}_{pick}", border=False):
                    a1, a2 = st.columns(2)
                    f_date = a1.text_input("사용일자 (YYYY-MM-DD)", value=text(row["사용일자"]))
                    f_amount = a2.text_input(
                        "결제금액",
                        value="" if pd.isna(row["결제금액"]) else f"{row['결제금액']:,.0f}",
                    )
                    b1, b2 = st.columns(2)
                    f_store = b1.text_input("상호명", value=text(row["상호명"]))
                    cur_now = text(row["통화"]) or "KRW"
                    f_cur = b2.selectbox(
                        "통화", currency_options,
                        index=currency_options.index(cur_now) if cur_now in currency_options else 0,
                    )
                    c1, c2 = st.columns(2)
                    cat_now = text(row["경비구분"])
                    f_cat = c1.selectbox(
                        "경비구분", cat_options,
                        index=cat_options.index(cat_now) if cat_now in cat_options else len(cat_options) - 1,
                    )
                    f_purpose = c2.text_input("목적", value=text(row["목적"]))
                    f_memo = st.text_area("사유 메모 (엑셀 '사유' 칸에 들어가요)", value=text(row["사유"]), height=70)
                    s1, s2 = st.columns(2)
                    done = s1.form_submit_button("확인 완료 → 다음", type="primary", width="stretch")
                    keep = s2.form_submit_button("수정만 저장", width="stretch")

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

    # ---------- 내보내기 ----------
    with tab_export:
        # 분기는 여러 개일 때만 고르게 한다
        quarters = sorted({q for q in edited["분기"] if q})
        has_unknown = bool((edited["분기"] == "").any())
        q_options = quarters + (["날짜 없음"] if has_unknown else [])
        if len(q_options) > 1:
            picked_q = st.multiselect("내보낼 분기", q_options, default=q_options)
        else:
            picked_q = q_options

        # 한 줄: 파일 이름 · 파일 형식 · 다운로드 (세부 설정은 아래에 접어 둔다)
        e1, e2, e3 = st.columns([2, 1.4, 1.2], vertical_alignment="bottom")
        file_stem = e1.text_input("파일 이름", value="expense_result")
        out_format = e2.radio("파일 형식", ["엑셀 (.xlsx)", "CSV (.csv)"], horizontal=True, key="out_format")
        as_csv = out_format.startswith("CSV")
        download_slot = e3.empty()
        extra_slot = st.container()  # 증빙 zip 버튼·안내 문구 자리

        mask = edited["분기"].isin(picked_q) | (("날짜 없음" in picked_q) & (edited["분기"] == ""))
        export_rows = edited[mask].reset_index(drop=True)

        # 구분별 합계 (금액은 쉼표, 합계 줄은 굵게)
        summary_df = build_summary_df(export_rows, cat_options)
        summary_df = summary_df[summary_df["건수"] > 0].reset_index(drop=True)
        if not summary_df.empty:
            st.markdown("**구분별 합계**")
            st.dataframe(
                summary_df.style.format({"금액합계": "{:,.0f}"}).apply(
                    lambda r: ["font-weight: 700" if r["경비구분"] == "합계" else "" for _ in r], axis=1
                ),
                hide_index=True,
                width="stretch",
            )

        with st.expander("파일 세부 설정 (컬럼·집계 시트·증빙 사진)"):
            # (1) 컬럼: 넣을지, 순서, 파일에 표시할 이름을 표 하나에서 정한다
            st.caption("넣지 않을 컬럼은 체크를 끄고, 순서는 숫자로, 이름은 오른쪽 칸을 더블클릭해 바꾸세요.")
            col_df = st.data_editor(
                pd.DataFrame({
                    "넣기": [True] * len(COLUMNS),
                    "순서": list(range(1, len(COLUMNS) + 1)),
                    "원래 이름": COLUMNS,
                    "파일에 표시할 이름": COLUMNS,
                }),
                key="column_editor",
                hide_index=True,
                width="stretch",
                column_config={
                    "넣기": st.column_config.CheckboxColumn("넣기", width="small"),
                    "순서": st.column_config.NumberColumn("순서", min_value=1, step=1, width="small"),
                    "원래 이름": st.column_config.TextColumn("원래 이름", disabled=True),
                },
            )
            col_df = col_df.assign(_pos=range(len(col_df)))
            col_df["순서"] = pd.to_numeric(col_df["순서"], errors="coerce").fillna(len(COLUMNS) + 1)
            picked = col_df[col_df["넣기"].fillna(False).astype(bool)].sort_values(["순서", "_pos"])
            selected_cols = [c for c in picked["원래 이름"] if c in COLUMNS]
            rename_map = dict(zip(col_df["원래 이름"], col_df["파일에 표시할 이름"]))

            # (3) 옵션
            o2, o3 = st.columns(2)
            include_summary = o2.checkbox("집계 시트 포함", value=True, help="엑셀 파일에만 들어가요.")
            want_zip = o3.checkbox(
                "증빙 사진 zip도 받기",
                value=False,
                help="행 번호에 맞춰 사진 이름을 바꿔 묶어줘요. 파일에 '증빙파일' 컬럼이 추가돼요.",
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

        if export_rows.empty:
            download_slot.info("선택한 분기에 영수증이 없어요.")
        elif not [c for c in selected_cols if c != "증빙파일"]:
            download_slot.info("넣을 컬럼을 하나 이상 남겨주세요.")
        elif duplicated:
            download_slot.error("컬럼 이름이 겹쳐요: " + ", ".join(duplicated))
        else:
            safe_stem = re.sub(r'[\\/:*?"<>|]', "_", file_stem.strip()) or "expense_result"
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
            download_slot.download_button(
                label=f"{file_label} 다운로드 ({len(export_rows)}건)",
                data=file_bytes,
                file_name=f"{safe_stem}.{file_ext}",
                mime=file_mime,
                type="primary",
                width="stretch",
            )

            with extra_slot:
                notes = []
                pending_left = int((export_rows["검토여부"] == "검토 필요").sum())
                if pending_left:
                    notes.append(
                        f"아직 검토 필요 {pending_left}건이 남아 있어요"
                        + ("" if as_csv else " (엑셀에서 노란색으로 표시)")
                    )
                if as_csv:
                    notes.append("CSV에는 집계 시트와 노란색 표시가 빠져요")
                if notes:
                    st.caption(" · ".join(notes))
                if want_zip:
                    if zip_items:
                        st.download_button(
                            label=f"증빙 사진 zip ({len(zip_items)}장)",
                            data=build_zip(zip_items),
                            file_name=f"{safe_stem}_증빙.zip",
                            mime="application/zip",
                        )
                    else:
                        st.caption("묶을 원본 사진이 없어요.")

        # ---------- 내 구글 드라이브에 저장 ----------
        if user.get("email"):
            st.divider()
            st.markdown("**내 구글 드라이브에 저장**")
            drive_info = work.setdefault("drive", {})
            flash = st.session_state.pop("drive_flash", None)
            if flash:
                st.success(flash)
            if not drive_ready:
                st.warning(drive_msg or "드라이브에 연결하지 못했어요.")
            else:
                if drive_info.get("loaded"):
                    st.caption(
                        f"불러온 드라이브 기록과 합친 전체 {len(edited)}건으로 {RECORD_FILE}를 바꿔요. "
                        "이전 내용은 드라이브의 '버전 관리'에 남아요."
                    )
                    save_label, save_done = f"드라이브에 저장 (전체 {len(edited)}건)", False
                else:
                    st.caption(f"드라이브의 {RECORD_FILE} 뒤에 이번 결과 {len(edited)}건을 덧붙여요.")
                    save_done = bool(drive_info.get("appended"))
                    save_label = "추가했어요" if save_done else f"드라이브 기록에 {len(edited)}건 추가"
                st.caption("영수증 사진은 저장하지 않아요.")
                d1, d2 = st.columns([1, 1])
                if d1.button(save_label, key="drive_save", disabled=save_done or edited.empty, width="stretch"):
                    token = access_token()
                    try:
                        rows = edited[COLUMNS]
                        if drive_info.get("loaded"):
                            base_modified, full = drive_info.get("modified"), rows
                        else:
                            old_bytes, old_meta = load_records(token, drive_folder)
                            old = (
                                read_previous_file(RECORD_FILE, old_bytes)[COLUMNS]
                                if old_bytes else pd.DataFrame(columns=COLUMNS)
                            )
                            base_modified = old_meta["modifiedTime"] if old_meta else None
                            full = pd.concat([old, rows], ignore_index=True)
                        xlsx = dataframe_to_excel_bytes(
                            add_quarter(full), columns=COLUMNS, include_summary=True, categories=cat_options
                        )
                        saved = save_records(token, drive_folder, xlsx, base_modified)
                        drive_info["link"] = saved.get("webViewLink") or drive_info.get("link")
                        if drive_info.get("loaded"):
                            drive_info["modified"] = saved.get("modifiedTime")
                        else:
                            drive_info["appended"] = True
                        st.session_state.drive_flash = f"내 드라이브에 저장했어요. ({RECORD_FILE}, 전체 {len(full)}건)"
                        st.rerun()
                    except DriveError as e:
                        st.error(str(e))
                    except Exception as e:  # noqa: BLE001
                        st.error(f"드라이브의 {RECORD_FILE}를 읽지 못했어요: {e}")
                if drive_info.get("link"):
                    d2.link_button("드라이브에서 열기", drive_info["link"], width="stretch")
                if drive_info.get("appended"):
                    st.caption("추가한 뒤에 고친 내용은 '지난 기록에 이어서 정리하기'로 드라이브 기록을 불러와 저장해 주세요.")

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