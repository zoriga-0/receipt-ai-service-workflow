"""
streamlit_app.py — 영수증 콜렉터 화면

화면은 두 가지 상태로 나뉜다.
  1) 시작: 영수증 올리기 · 목적 · 분석 버튼 (+ 지난 기록에 이어서)
  2) 결과: 합계 카드 → 검토 안내 → 영수증 카드 목록 → 내보내기
     - 카드의 '수정'이나 '하나씩 확인하기'를 누르면 사진과 입력칸이 있는 창(dialog)이 뜬다.
     - 표 편집(행 추가·삭제)은 '표로 보고 고치기'에 접어 둔다.
     - '영수증 더 추가하기'로 올린 영수증은 지금 결과에 이어 붙는다.
"""

import html
import re

import pandas as pd
import streamlit as st

import config
from api_client import run_via_api, server_status
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
from service import process_receipts
from session_keep import restore, sync
from theme import apply_theme
from ui_extras import AnalysisProgress, is_production, leave_guard

st.set_page_config(page_title="영수증 콜렉터", page_icon="🧾", layout="wide")
apply_theme()  # 디자인 (theme.py)

CURRENCIES = ["KRW", "USD", "JPY", "EUR", "CNY", "GBP"]
FILE_TYPES = ["png", "jpg", "jpeg", "pdf", "heic", "heif"]


def text(v) -> str:
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


def money(v, currency="KRW") -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "금액 없음"
    if currency in ("", "KRW", None):
        return f"{v:,.0f}원"
    return f"{currency} {v:,.2f}"


@st.cache_data(show_spinner=False, max_entries=200)
def cached_preview(name: str, data: bytes):
    return make_preview(name, data)


##################################################
# 맨 위: 이름 + 계정
##################################################

with st.container(key="row_topbar"):
    top_l, top_r = st.columns([3, 1], vertical_alignment="center")
    top_l.markdown('<div class="rc-brand">영수증 콜렉터</div>', unsafe_allow_html=True)

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
    with top_r.popover("계정", icon=":material/account_circle:", width="stretch"):
        st.markdown(f"**{html.escape(user.get('name') or '')}**")
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
st.session_state.pop("restored", None)

##################################################
# 설정 확인
##################################################

# https(배포 사이트)면 개발용 정보(환경변수 이름, MOCK 안내, Agent 원본 응답)를 숨긴다.
PROD = is_production()

missing = config.missing_settings()
if missing:
    if PROD:
        st.error("지금은 영수증 분석을 할 수 없어요. 잠시 후 다시 시도해 주세요.")
    else:
        st.error("다음 환경변수가 비어 있어 분석할 수 없어요: " + ", ".join(missing) + "\n\n.env에 넣고 다시 켜세요.")
if config.USE_MOCK and not PROD:
    st.info("USE_MOCK=1: Upstage를 부르지 않고 가짜 결과를 보여줘요.")

##################################################
# 입력 칸 (시작 화면과 '더 추가하기'에서 같이 쓴다)
##################################################


def input_panel(adding: bool):
    """반환: (올린 파일, 목적, 경비 구분 목록, 분석 버튼)"""
    nonce = st.session_state.get("upload_nonce", 0)  # 분석이 끝나면 올리기 칸을 비우려고 키를 바꾼다
    files = st.file_uploader(
        "영수증 사진",
        type=FILE_TYPES,
        accept_multiple_files=True,
        key=f"files_{nonce}",
        label_visibility="collapsed",
    )
    n = len(files or [])

    # 지출 목적: 적으면 Solar가 목적에 맞게 다시 분류하고, 목적과 안 맞는 품목을 짚는다
    purpose = st.text_input(
        "어디에 쓴 돈인가요? (선택)",
        placeholder="예: 11월 MT 장보기",
        max_chars=100,
        key=f"purpose_{nonce}",
        help="이번에 올린 영수증 전체에 적용돼요. 목적이 다르면 나눠서 올려 주세요.",
    ).strip()

    # 경비 구분: 칩으로 보여주고 '바꾸기'에서 고친다
    preset = st.session_state.get("cat_preset", list(CATEGORY_PRESETS)[0])
    cats = parse_categories(st.session_state.get(f"cat_text_{preset}", ", ".join(CATEGORY_PRESETS[preset])))
    with st.container(key="row_cats"):
        c_l, c_r = st.columns([2.6, 1.1], vertical_alignment="center")
        c_l.markdown(
            '<div class="rc-chips"><span class="rc-chips-label">경비 구분</span>'
            + "".join(f'<span class="rc-chip">{html.escape(c)}</span>' for c in cats)
            + "</div>",
            unsafe_allow_html=True,
        )
        with c_r.popover("바꾸기", width="stretch"):
            preset = st.selectbox("기본 목록", list(CATEGORY_PRESETS), key="cat_preset")
            st.text_input(
                "구분 목록",
                value=", ".join(CATEGORY_PRESETS[preset]),
                key=f"cat_text_{preset}",
                help="쉼표로 나눠 고칠 수 있어요. '기타'는 항상 들어가요.",
            )
    categories = parse_categories(
        st.session_state.get(f"cat_text_{preset}", ", ".join(CATEGORY_PRESETS[preset]))
    )

    if adding:
        label = f"영수증 {n}장 추가 분석" if n else "추가할 영수증을 올려 주세요"
    else:
        label = f"영수증 {n}장 분석하기" if n else "분석하기"
    run = st.button(label, key="run_new", type="primary", width="stretch", disabled=not n or bool(missing))
    return files, purpose, categories, run


def previous_panel(n_files: int):
    """지난 기록(내 드라이브 / 받아 둔 엑셀·CSV)에 이어서. 반환: (드라이브 사용, 올린 파일, 버튼)"""
    use_drive = drive_ready and st.checkbox(
        f"내 구글 드라이브의 {RECORD_FILE} 불러오기", value=True, key="use_drive"
    )
    prev_file = st.file_uploader(
        "받아 두었던 엑셀·CSV",
        type=["xlsx", "csv"],
        key=f"prev_{st.session_state.get('upload_nonce', 0)}",
    )
    has_prev = bool(prev_file or use_drive)
    if has_prev and n_files:
        label = f"지난 기록 + 영수증 {n_files}장 합쳐서 분석"
    elif has_prev:
        label = "지난 기록 불러오기"
    else:
        label = "불러올 기록을 골라 주세요"
    run = st.button(label, key="run_merge", width="stretch", disabled=not has_prev or bool(missing and n_files))
    return use_drive, prev_file, run


##################################################
# 화면 1: 시작 / 화면 2 위쪽: 결과 요약 + 더 추가하기
##################################################

work = st.session_state.get("work")
summary_slot = None
if not work:
    st.markdown(
        '<div class="rc-hero">영수증 사진을 올리면<br><span>정산용 엑셀로 정리해 드려요</span></div>',
        unsafe_allow_html=True,
    )
    with st.container(key="upload_card"):
        uploaded_files, purpose, categories, run_new = input_panel(adding=False)
    with st.expander("지난 기록에 이어서 정리하기", icon=":material/history:"):
        use_drive, previous_file, run_merge = previous_panel(len(uploaded_files or []))
else:
    summary_slot = st.container(key="summary_card")  # 합계는 표에서 고친 값까지 반영해야 해서 아래에서 채운다
    # 추가 분석이 끝나면 접힌 상태로 다시 그리려고 이름 끝에 보이지 않는 글자를 묶음 수만큼 붙인다
    add_label = "영수증 더 추가하기" + "\u200b" * work.get("batch", 0)
    with st.expander(add_label, icon=":material/add_photo_alternate:"):
        uploaded_files, purpose, categories, run_new = input_panel(adding=True)
        st.markdown('<div class="rc-sub">또는 지난 기록 불러오기</div>', unsafe_allow_html=True)
        use_drive, previous_file, run_merge = previous_panel(len(uploaded_files or []))

n_files = len(uploaded_files or [])

# 올리기만 하고 아직 분석하지 않은 파일이 있으면 새로고침·창 닫기 때 경고한다.
# (분석이 끝나면 올리기 칸을 비우므로 경고도 꺼진다. 분석 결과는 새로고침해도 되살아난다)
leave_guard(bool(n_files or previous_file))

##################################################
# 분석
##################################################

if (run_new or run_merge) and config.API_URL and n_files:
    # 서버를 쓰는 설정이면, 분석 전에 서버가 켜져 있는지 먼저 확인한다
    alive, why = server_status()
    if not alive:
        st.error(why if not PROD else "분석 서버가 꺼져 있어요. 잠시 후 다시 시도해 주세요.")
        st.stop()

if run_new or run_merge:
    old = work or {}
    current = old.get("latest") if old.get("latest") is not None else old.get("df")

    # 1) 지난 기록: 지금 결과 + 내 드라이브 + 올린 파일
    prev_parts, prev_notes, drive_info = [], [], dict(old.get("drive") or {})
    if current is not None and len(current):
        prev_parts.append(current[COLUMNS + ["_id"]])
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
        prev_parts.append(drive_df.assign(_id=None))
        prev_notes.append(f"내 드라이브 {len(drive_df)}건")
        drive_info = {  # loaded가 있어야 '전체 저장'을 한다 (드라이브 기록을 모르고 덮어쓰지 않게)
            "loaded": True,
            "modified": drive_meta["modifiedTime"] if drive_meta else None,
            "link": drive_meta.get("webViewLink") if drive_meta else None,
        }
    if run_merge and previous_file:
        try:
            file_df = read_previous_file(previous_file.name, previous_file.getvalue())
        except Exception as e:  # noqa: BLE001
            st.error(f"이전 파일을 읽지 못했어요: {e}")
            st.stop()
        prev_parts.append(file_df.assign(_id=None))
        prev_notes.append(f"올린 파일 {len(file_df)}건")
    prev_df = (
        pd.concat(prev_parts, ignore_index=True)[COLUMNS + ["_id"]]
        if prev_parts
        else pd.DataFrame(columns=COLUMNS + ["_id"])
    )

    # 2) 새 영수증 (HEIC → JPG)
    prepared, prep_errors = [], []
    for f in uploaded_files or []:
        name, data, err = prepare_upload(f.name, f.getvalue())
        if err:  # (한 줄짜리 식으로 쓰면 Streamlit이 결과 None을 화면에 찍어서 if문으로 쓴다)
            prep_errors.append(err)
        else:
            prepared.append((name, data))

    batch = old.get("batch", 0) + 1
    new_df, details, originals = pd.DataFrame(columns=COLUMNS + ["_id"]), [], {}
    elapsed = None
    if prepared:
        tracker = AnalysisProgress(len(prepared))
        context = {"purpose": purpose, "categories": categories}
        runner = run_via_api if config.API_URL else None  # 서버가 있으면 서버로, 없으면 직접
        new_df, details, originals = process_receipts(prepared, tracker.update, context, runner)
        elapsed = tracker.finish(len(prepared))
        # 사진 연결용 ID가 앞서 추가한 영수증과 겹치지 않게 묶음 번호를 붙인다
        new_df["_id"] = [f"b{batch}_{i}" for i in new_df["_id"]]
        originals = {f"b{batch}_{k}": v for k, v in originals.items()}

    # 3) 합치고 중복 확인 (새로 올린 영수증만 '중복 의심'으로 표시)
    combined = pd.concat([prev_df, new_df], ignore_index=True)
    combined["결제금액"] = pd.to_numeric(combined["결제금액"], errors="coerce")
    mark = [False] * len(prev_df) + [True] * len(new_df)
    combined, dup_count = detect_duplicates(combined, mark)

    merged_cats = list(old.get("categories") or [])
    merged_cats += [c for c in categories if c not in merged_cats]
    st.session_state.work = {
        "df": add_quarter(combined)[COLUMNS + ["_id"]],
        "details": list(old.get("details") or []) + details,
        "originals": {**(old.get("originals") or {}), **originals},
        "ver": old.get("ver", 0) + 1,
        "batch": batch,
        "prev_count": len(prev_df) - (len(current) if current is not None else 0),
        "prev_notes": prev_notes,
        "drive": drive_info,
        "dup_count": dup_count,
        "prep_errors": prep_errors,
        "elapsed": elapsed,
        "n_new": len(prepared),
        "categories": merged_cats or categories,
    }
    # 올리기 칸을 비우고 결과 화면으로
    st.session_state.upload_nonce = st.session_state.get("upload_nonce", 0) + 1
    sync(owner)
    st.rerun()

work = st.session_state.get("work")
sync(owner)

##################################################
# 화면 2: 결과
##################################################


def reset_all():
    st.session_state.pop("work", None)
    st.session_state.upload_nonce = st.session_state.get("upload_nonce", 0) + 1


@st.dialog("영수증 확인", width="large")
def edit_dialog(idx, review_mode: bool):
    """사진을 보며 한 장을 고친다. review_mode면 '확인 완료' 뒤 다음 검토 건을 바로 연다."""
    w = st.session_state.work
    rows = w["latest"] if w.get("latest") is not None else w["df"]
    if idx not in rows.index:
        st.info("이미 지워진 영수증이에요.")
        return
    row = rows.loc[idx]
    rid = row.get("_id")
    has_photo = isinstance(rid, str) and rid in w["originals"]
    if review_mode:
        left = int((rows["검토여부"] == "검토 필요").sum())
        st.caption(f"검토 남은 영수증 {left}건")

    if has_photo:
        src_name, src_data = w["originals"][rid]
        preview = cached_preview(src_name, src_data)
        if preview:
            st.image(preview, caption=src_name)
        else:
            st.download_button("원본 내려받기", src_data, file_name=src_name)
    else:
        st.caption("원본 사진이 없는 행이에요. (지난 기록에서 불러왔거나 직접 추가한 행)")
    if text(row["사유"]):
        st.warning(text(row["사유"]))

    cats = list(w.get("categories") or CATEGORIES)
    cats += [c for c in [text(row["경비구분"])] if c and c not in cats]
    curs = sorted(set(CURRENCIES) | {text(row["통화"]) or "KRW"})
    with st.form(f"edit_{idx}", border=False):
        with st.container(key="row_dlg_a"):
            a1, a2 = st.columns(2)
        f_date = a1.text_input("사용일자", value=text(row["사용일자"]), placeholder="2026-11-03")
        f_amount = a2.text_input(
            "결제금액", value="" if pd.isna(row["결제금액"]) else f"{row['결제금액']:,.2f}".rstrip("0").rstrip(".")
        )
        f_store = st.text_input("상호명", value=text(row["상호명"]))
        with st.container(key="row_dlg_b"):
            b1, b2 = st.columns(2)
        cat_now = text(row["경비구분"])
        f_cat = b1.selectbox("경비구분", cats, index=cats.index(cat_now) if cat_now in cats else len(cats) - 1)
        cur_now = text(row["통화"]) or "KRW"
        f_cur = b2.selectbox("통화", curs, index=curs.index(cur_now))
        f_purpose = st.text_input("목적", value=text(row["목적"]))
        f_memo = st.text_area("사유 메모 (엑셀 '사유' 칸)", value=text(row["사유"]), height=80)
        done = st.form_submit_button(
            "확인 완료 → 다음" if review_mode else "확인 완료", type="primary", width="stretch"
        )
        s1, s2 = st.columns(2)
        keep = s1.form_submit_button("수정만 저장", width="stretch")
        drop = s2.form_submit_button("이 영수증 빼기", width="stretch")

    if drop:
        new_df = rows.drop(index=idx).reset_index(drop=True)
    elif done or keep:
        date_ok = normalize_date(f_date) if f_date.strip() else ""
        if f_date.strip() and not re.match(r"^\d{4}-\d{2}-\d{2}$", date_ok):
            st.error("사용일자는 2026-11-03 같은 형식으로 입력해 주세요.")
            return
        new_df = rows.copy()
        new_df.at[idx, "사용일자"] = date_ok
        new_df.at[idx, "상호명"] = f_store.strip()
        amount = parse_amount(f_amount)
        new_df.at[idx, "결제금액"] = amount if amount else float("nan")
        new_df.at[idx, "경비구분"] = f_cat
        new_df.at[idx, "목적"] = f_purpose.strip()
        new_df.at[idx, "통화"] = f_cur
        new_df.at[idx, "사유"] = f_memo.strip()
        if done:
            new_df.at[idx, "검토여부"] = "검토 완료"
    else:
        return
    w["df"] = add_quarter(new_df)[COLUMNS + ["_id"]]
    w["latest"] = None
    w["ver"] = w.get("ver", 0) + 1
    st.session_state.review_chain = bool(review_mode and done)
    st.rerun()


if work:
    df, details, originals, ver = work["df"], work["details"], work["originals"], work["ver"]
    base = work.get("latest") if work.get("latest") is not None else df

    # 알림 (파일 오류·분석 오류) — 중복 의심은 아래 검토 목록에서 사유로 보여준다
    for err in work["prep_errors"]:
        st.error(err)
    failed = [d for d in details if d["errors"]]
    if failed:
        st.warning(f"{len(failed)}개 파일에서 분석 오류가 있었어요. 아래 목록의 사유를 확인해 주세요.")

    review_slot = st.container()
    filter_slot = st.container()
    list_slot = st.container(key="receipt_list")

    currency_options = sorted(set(CURRENCIES) | {c for c in df["통화"].dropna() if c})
    # 경비 구분 선택지: 분석할 때 정한 목록 + 지난 기록에만 있던 구분
    cat_options = list(work.get("categories") or CATEGORIES)
    cat_options += sorted({c for c in df["경비구분"].dropna() if c and c not in cat_options})

    # ---------- 표로 보고 고치기 (행 추가·삭제) ----------
    # 목록·합계·내보내기가 이 표의 최신 값을 써야 하므로 코드는 표를 먼저 실행한다.
    with st.expander("표로 보고 고치기 (행 추가·삭제)", icon=":material/table_view:"):
        st.caption("칸을 두 번 눌러 고쳐요. 맨 아래 빈 줄에 행을 추가하고, 왼쪽 체크로 지워요.")
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
        work["latest"] = edited.reindex(columns=COLUMNS + ["_id"])  # 수정 창·새로고침이 쓸 최신 값

    n_pending = int((edited["검토여부"] == "검토 필요").sum())
    n_done = int((edited["검토여부"] == "검토 완료").sum())

    # ---------- 합계 카드 ----------
    with summary_slot:
        with st.container(key="row_summary_head"):
            h_l, h_r = st.columns([2, 1], vertical_alignment="center")
            h_l.markdown('<div class="rc-section">분석 결과</div>', unsafe_allow_html=True)
            h_r.button("처음부터", on_click=reset_all, width="stretch", help="결과를 지우고 새로 시작해요")
        krw = edited.loc[edited["통화"].isin(["KRW", ""]) | edited["통화"].isna(), "결제금액"].sum()
        others = edited[edited["통화"].notna() & ~edited["통화"].isin(["KRW", ""])].groupby("통화")["결제금액"].sum()
        other_txt = " · ".join(f"{c} {v:,.2f}" for c, v in others.items() if v)
        info = []
        if work.get("prev_notes"):
            info.append("지난 기록 포함 (" + ", ".join(work["prev_notes"]) + ")")
        if work.get("elapsed") and work.get("n_new"):
            info.append(
                f"방금 {work['n_new']}장 · {work['elapsed']:.0f}초 (장당 {work['elapsed'] / work['n_new']:.1f}초)"
            )
        st.markdown(
            f'<div class="rc-total"><small>합계</small><b>{krw:,.0f}원</b>'
            + (f"<em>+ {html.escape(other_txt)}</em>" if other_txt else "")
            + "</div>"
            + '<div class="rc-stats">'
            + f"<div>영수증<b>{len(edited)}</b></div>"
            + f'<div class="{"warn" if n_pending else ""}">검토 필요<b>{n_pending}</b></div>'
            + f"<div>검토 완료<b>{n_done}</b></div></div>"
            + (f'<div class="rc-meta">{html.escape(" · ".join(info))}</div>' if info else ""),
            unsafe_allow_html=True,
        )

    # ---------- 검토 안내 ----------
    start_review = False
    with review_slot:
        if n_pending:
            with st.container(key="review_banner"):
                n_dup = int(
                    ((edited["검토여부"] == "검토 필요") & edited["사유"].fillna("").str.contains("중복")).sum()
                )
                st.markdown(
                    f'<div class="rc-banner"><b>검토가 필요한 영수증 {n_pending}건</b>'
                    + (f"<span>그중 {n_dup}건은 중복 의심이에요. </span>" if n_dup else "")
                    + "<span>사진을 보며 하나씩 확인하고 고칠 수 있어요.</span></div>",
                    unsafe_allow_html=True,
                )
                start_review = st.button(
                    "하나씩 확인하기", type="primary", width="stretch", icon=":material/fact_check:"
                )
        elif len(edited):
            st.markdown(
                '<div class="rc-banner ok"><b>모두 확인했어요</b><span>아래에서 파일을 받으세요.</span></div>',
                unsafe_allow_html=True,
            )

    # ---------- 영수증 카드 목록 ----------
    with filter_slot:
        counts = {"all": len(edited), "pending": n_pending, "done": n_done}
        names = {"all": "전체", "pending": "검토 필요", "done": "검토 완료"}
        pick = st.segmented_control(
            "보기",
            ["all", "pending", "done"],
            format_func=lambda k: f"{names[k]} {counts[k]}",
            default="pending" if n_pending else "all",
            key=f"filter_{ver}",
            label_visibility="collapsed",
        ) or "all"
    open_idx = None
    with list_slot:
        if pick == "pending":
            shown = edited[edited["검토여부"] == "검토 필요"]
        elif pick == "done":
            shown = edited[edited["검토여부"] == "검토 완료"]
        else:
            shown = edited
        if shown.empty:
            st.caption("해당하는 영수증이 없어요.")
        for i, r in shown.iterrows():
            status = text(r["검토여부"])
            cls = {"검토 필요": "pending", "검토 완료": "done"}.get(status, "")
            sub = " · ".join(x for x in [text(r["사용일자"]), text(r["경비구분"])] if x)
            reason = text(r["사유"]) if status == "검토 필요" else ""
            with st.container(key=f"rowc_{ver}_{i}"):
                r_l, r_r = st.columns([5, 1.2], vertical_alignment="center")
                r_l.markdown(
                    f'<div class="rc-row {cls}"><div class="rc-row-top">'
                    f'<b>{html.escape(text(r["상호명"]) or "상호 없음")}</b>'
                    f'<span class="rc-amt">{html.escape(money(r["결제금액"], text(r["통화"])))}</span></div>'
                    f'<div class="rc-row-sub">{html.escape(sub)}'
                    + (f'<span class="rc-badge {cls}">{html.escape(status)}</span>' if cls else "")
                    + "</div>"
                    + (f'<div class="rc-row-reason">{html.escape(reason)}</div>' if reason else "")
                    + "</div>",
                    unsafe_allow_html=True,
                )
                if r_r.button("수정", key=f"edit_{ver}_{i}", width="stretch"):
                    open_idx = i

    # 수정 창 열기 (한 화면에 하나만)
    if open_idx is not None:
        edit_dialog(open_idx, review_mode=False)
    elif start_review or st.session_state.pop("review_chain", False):
        pending = edited.index[edited["검토여부"] == "검토 필요"].tolist()
        if pending:
            edit_dialog(pending[0], review_mode=True)

    # ---------- 내보내기 ----------
    with st.container(key="export_card"):
        st.markdown('<div class="rc-section">내보내기</div>', unsafe_allow_html=True)

        # 분기는 여러 개일 때만 고르게 한다
        quarters = sorted({q for q in edited["분기"] if q})
        has_unknown = bool((edited["분기"] == "").any())
        q_options = quarters + (["날짜 없음"] if has_unknown else [])
        picked_q = (
            st.multiselect("내보낼 분기", q_options, default=q_options) if len(q_options) > 1 else q_options
        )

        e1, e2 = st.columns([1.6, 1], vertical_alignment="bottom")
        file_stem = e1.text_input("파일 이름", value="expense_result")
        out_format = e2.segmented_control(
            "파일 형식", ["엑셀", "CSV"], default="엑셀", key="out_format"
        ) or "엑셀"
        as_csv = out_format == "CSV"
        download_slot = st.empty()
        extra_slot = st.container()  # 안내 문구·증빙 zip 버튼 자리

        mask = edited["분기"].isin(picked_q) | (("날짜 없음" in picked_q) & (edited["분기"] == ""))
        export_rows = edited[mask].reset_index(drop=True)

        # 구분별 합계 (원화만 금액 합계)
        summary_df = build_summary_df(export_rows, cat_options)
        summary_df = summary_df[summary_df["건수"] > 0].reset_index(drop=True)
        if not summary_df.empty:
            lines = []
            for _, s in summary_df.iterrows():
                is_total = s["경비구분"] == "합계"
                cur = text(s.get("통화")) if "통화" in summary_df.columns else ""
                amt = f'{s["금액합계"]:,.0f}' + ("원" if cur in ("", "KRW") else f" {cur}")
                lines.append(
                    f'<div class="rc-sum-row{" total" if is_total else ""}">'
                    f'<span>{html.escape(text(s["경비구분"]))}'
                    f'{"" if cur in ("", "KRW") or is_total else f" · {html.escape(cur)}"}</span>'
                    f'<span>{int(s["건수"])}건</span><b>{amt}</b></div>'
                )
            st.markdown('<div class="rc-sum">' + "".join(lines) + "</div>", unsafe_allow_html=True)

        with st.expander("파일 세부 설정 (컬럼 · 집계 시트 · 증빙 사진)", icon=":material/tune:"):
            # (1) 컬럼: 넣을지, 순서, 파일에 표시할 이름을 표 하나에서 정한다
            st.caption("넣지 않을 컬럼은 체크를 끄고, 순서는 숫자로, 이름은 오른쪽 칸을 두 번 눌러 바꿔요.")
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

            include_summary = st.checkbox("집계 시트 포함 (엑셀만)", value=True)
            want_zip = st.checkbox(
                "증빙 사진 zip도 받기",
                value=False,
                help="행 번호에 맞춰 사진 이름을 바꿔 묶어줘요. 파일에 '증빙파일' 컬럼이 추가돼요.",
            )

        zip_items = []
        if want_zip:
            export_rows = export_rows.copy()
            names_ = []
            for no, (_, r) in enumerate(export_rows.iterrows(), start=1):
                rid = r.get("_id")
                if isinstance(rid, str) and rid in originals:
                    src_name, src_data = originals[rid]
                    zname = evidence_filename(no, r["사용일자"], r["상호명"], src_name)
                    zip_items.append((zname, src_data))
                    names_.append(zname)
                else:
                    names_.append("")
            export_rows["증빙파일"] = names_
            selected_cols = selected_cols + ["증빙파일"]

        headers, duplicated = resolve_headers(selected_cols, rename_map)

        if export_rows.empty:
            download_slot.info("선택한 분기에 영수증이 없어요.")
        elif not [c for c in selected_cols if c != "증빙파일"]:
            download_slot.info("넣을 컬럼을 하나 이상 남겨 주세요.")
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
                label=f"{file_label} 받기 ({len(export_rows)}건)",
                data=file_bytes,
                file_name=f"{safe_stem}.{file_ext}",
                mime=file_mime,
                type="primary",
                width="stretch",
                icon=":material/download:",
            )
            with extra_slot:
                notes = []
                pending_left = int((export_rows["검토여부"] == "검토 필요").sum())
                if pending_left:
                    notes.append(
                        f"아직 검토 필요 {pending_left}건이 남아 있어요" + ("" if as_csv else " (엑셀에서 노란색)")
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
                            width="stretch",
                        )
                    else:
                        st.caption("묶을 원본 사진이 없어요.")

        # ---------- 내 구글 드라이브에 저장 ----------
        if user.get("email"):
            st.markdown('<div class="rc-sub">내 구글 드라이브</div>', unsafe_allow_html=True)
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
                        "이전 내용은 드라이브의 '버전 관리'에 남아요. 영수증 사진은 저장하지 않아요."
                    )
                    save_label, save_done = f"드라이브에 저장 (전체 {len(edited)}건)", False
                else:
                    st.caption(
                        f"드라이브의 {RECORD_FILE} 뒤에 이번 결과 {len(edited)}건을 덧붙여요. 영수증 사진은 저장하지 않아요."
                    )
                    save_done = bool(drive_info.get("appended"))
                    save_label = "추가했어요" if save_done else f"드라이브 기록에 {len(edited)}건 추가"
                d1, d2 = st.columns(2)
                if d1.button(
                    save_label, key="drive_save", disabled=save_done or edited.empty, width="stretch",
                    icon=":material/add_to_drive:",
                ):
                    token = access_token()
                    try:
                        rows = edited[COLUMNS]
                        if drive_info.get("loaded"):
                            base_modified, full = drive_info.get("modified"), rows
                        else:
                            old_bytes, old_meta = load_records(token, drive_folder)
                            old_rows = (
                                read_previous_file(RECORD_FILE, old_bytes)[COLUMNS]
                                if old_bytes else pd.DataFrame(columns=COLUMNS)
                            )
                            base_modified = old_meta["modifiedTime"] if old_meta else None
                            full = pd.concat([old_rows, rows], ignore_index=True)
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
                    st.caption("추가한 뒤에 고친 내용은 '지난 기록 불러오기'로 드라이브 기록을 불러와 저장해 주세요.")

    # ---------- 분석 상세 (개발 환경에서만) ----------
    if details and not PROD:
        with st.expander("분석 상세 (Agent 원본 응답·오류)", icon=":material/code:"):
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
