"""
theme.py

화면 디자인 (CSS). 시안:
  team    : 연회색 바탕 + 흰 카드(얇은 테두리) + 파란 포인트 (팀 디자인, 기본값)
  toss    : 밝은 회색 바탕 + 흰 카드 + 파란 버튼, 큰 글씨 (토스 느낌)
  minimal : 흰 바탕 + 얇은 선 + 검은 버튼, 담백하게 (노션 느낌)
  receipt : 종이 색 바탕 + 점선 + 고정폭 숫자 (영수증 느낌)

기본값은 환경변수 UI_THEME, 주소 끝에 ?theme=receipt 처럼 붙이면 그 시안으로 볼 수 있다.
라이트/다크는 휴대폰·PC 설정을 따라 자동으로 바뀐다.
"""

import os

import streamlit as st

THEMES = ("team", "toss", "minimal", "receipt")

FONT_IMPORTS = """
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');
"""

_SANS = "'Pretendard Variable', Pretendard, -apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif"
_MONO = "'JetBrains Mono', 'Pretendard Variable', Pretendard, monospace"

# 시안별 색·모양 (라이트, 다크)
VARS = {
    "team": (
        dict(bg="#F6F7F9", card="#FFFFFF", text="#17202B", muted="#667085", line="#E3E7EC",
             accent="#2F6FED", on_accent="#FFFFFF", soft="#EEF4FF", warn="#C2410C", ok="#15803D",
             radius="12px", btn_radius="10px", border="1px solid var(--rc-line)",
             font=_SANS, num=_SANS, brand=_SANS, h1="28px", h1_weight="800", btn_h="48px"),
        dict(bg="#0F1115", card="#181B21", text="#E6E9EE", muted="#98A2B3", line="#2A2F38",
             accent="#5B8DEF", on_accent="#FFFFFF", soft="#1B2536", warn="#FB923C", ok="#4ADE80"),
    ),
    "toss": (
        dict(bg="#F2F4F6", card="#FFFFFF", text="#191F28", muted="#6B7684", line="#E5E8EB",
             accent="#3182F6", on_accent="#FFFFFF", soft="#E8F3FF", warn="#F04452", ok="#15803D",
             radius="20px", btn_radius="14px", border="0px solid transparent",
             font=_SANS, num=_SANS, brand=_SANS, h1="32px", h1_weight="700", btn_h="54px"),
        dict(bg="#101013", card="#1D1D22", text="#EDEDF0", muted="#9E9EA7", line="#2C2C33",
             accent="#3182F6", on_accent="#FFFFFF", soft="#1B2A40", warn="#FF6B76", ok="#4ADE80"),
    ),
    "minimal": (
        dict(bg="#FFFFFF", card="#FFFFFF", text="#37352F", muted="#787774", line="#E9E9E7",
             accent="#2F2F2D", on_accent="#FFFFFF", soft="#F7F7F5", warn="#D44C47", ok="#2F7D4F",
             radius="10px", btn_radius="8px", border="1px solid var(--rc-line)",
             font=_SANS, num=_SANS, brand=_SANS, h1="28px", h1_weight="600", btn_h="46px"),
        dict(bg="#191919", card="#191919", text="#E6E6E4", muted="#9B9A97", line="#2F2F2F",
             accent="#E6E6E4", on_accent="#191919", soft="#252525", warn="#FF7369", ok="#6CC38E"),
    ),
    "receipt": (
        dict(bg="#E7E3DA", card="#FFFDF7", text="#1C1B19", muted="#78746B", line="#CBC5B8",
             accent="#1C1B19", on_accent="#FFFDF7", soft="#F4F0E6", warn="#C2410C", ok="#15803D",
             radius="4px", btn_radius="4px", border="1.5px dashed var(--rc-line)",
             font=_SANS, num=_MONO, brand=_MONO, h1="28px", h1_weight="700", btn_h="50px"),
        dict(bg="#121211", card="#1C1B19", text="#EDE9E0", muted="#A29D92", line="#45423B",
             accent="#EDE9E0", on_accent="#121211", soft="#26241F", warn="#FB923C", ok="#4ADE80"),
    ),
}


def current_theme() -> str:
    try:
        q = str(st.query_params.get("theme", "")).lower()
    except Exception:  # noqa: BLE001
        q = ""
    name = q or os.getenv("UI_THEME", "team").lower()
    return name if name in THEMES else "team"


def _vars(d: dict) -> str:
    return "".join(f"--rc-{k.replace('_', '-')}: {v};" for k, v in d.items())


def apply_theme(name: str | None = None) -> str:
    name = name or current_theme()
    light, dark = VARS[name]
    css = f"""
<style>
{FONT_IMPORTS}
:root {{ {_vars(light)} }}
@media (prefers-color-scheme: dark) {{ :root {{ {_vars(dark)} }} }}

/* 기본: Streamlit 메뉴·장식 숨기기, 당겨서 새로고침 막기 */
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {{ visibility: hidden; }}
header[data-testid="stHeader"] {{ background: transparent; }}
html, body, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{ overscroll-behavior-y: contain; }}
html {{ -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }}
.stApp button, .stApp a, .stApp summary {{ -webkit-tap-highlight-color: transparent; touch-action: manipulation; }}

.stApp {{ background: var(--rc-bg); color: var(--rc-text); }}
.stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp textarea, .stApp button,
.stApp h1, .stApp h2, .stApp h3, .stApp summary, .stApp [data-testid="stTab"] p {{
  font-family: var(--rc-font) !important; letter-spacing: -0.01em;
}}
.stApp [data-testid="stIconMaterial"] {{ font-family: 'Material Symbols Rounded' !important; letter-spacing: 0; }}
[data-testid="stMainBlockContainer"] {{ max-width: 760px; padding-top: 1.6rem; padding-bottom: 5rem; }}
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p {{ color: var(--rc-muted); }}

/* 머리글 */
.rc-brand {{ font-family: var(--rc-brand); font-weight: 700; font-size: 17px; color: var(--rc-text); }}
.rc-hero {{ font-size: var(--rc-h1); font-weight: var(--rc-h1-weight); line-height: 1.3;
  color: var(--rc-text); margin: 28px 0 22px; letter-spacing: -0.03em; }}
.rc-hero span {{ color: var(--rc-muted); }}
.rc-section {{ font-size: 20px; font-weight: 700; color: var(--rc-text); margin: 8px 0 4px; }}

/* 카드 */
.st-key-upload_card, .st-key-summary_card, .st-key-export_card, .st-key-login_card {{
  background: var(--rc-card); border-radius: var(--rc-radius) !important;
  border: var(--rc-border) !important; padding: 22px 22px 20px;
}}

/* 버튼 */
.stApp button[data-testid^="stBaseButton-primary"] {{
  background: var(--rc-accent); color: var(--rc-on-accent); border: none;
  border-radius: var(--rc-btn-radius); min-height: var(--rc-btn-h); font-weight: 600; font-size: 16px;
}}
.stApp button[data-testid^="stBaseButton-primary"]:hover {{ filter: brightness(1.06); color: var(--rc-on-accent); }}
.stApp button[data-testid^="stBaseButton-primary"]:disabled {{ background: var(--rc-line); color: var(--rc-muted); }}
.stApp button[data-testid^="stBaseButton-secondary"], .stApp [data-testid="stPopover"] button {{
  background: var(--rc-soft); color: var(--rc-text); border: 1px solid transparent;
  border-radius: var(--rc-btn-radius); font-weight: 500;
}}
.stApp a[data-testid="stBaseLinkButton-secondary"] {{ border-radius: var(--rc-btn-radius); }}

/* 입력칸 */
.stApp [data-testid="stTextInputRootElement"], .stApp [data-baseweb="select"] > div,
.stApp [data-testid="stTextArea"] textarea {{
  border-radius: var(--rc-btn-radius) !important; border-color: var(--rc-line) !important;
}}

/* 업로드 칸: 한글로 */
.stApp [data-testid="stFileUploaderDropzone"] {{
  background: var(--rc-soft); border: 1.5px dashed var(--rc-line); border-radius: var(--rc-btn-radius);
  padding: 18px 16px;
}}
.stApp [data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p {{ font-size: 0; }}
.stApp [data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after {{
  content: "파일 고르기"; font-size: 14px; font-weight: 600;
}}
.stApp [class*="st-key-files_"] [data-testid="stFileUploaderDropzone"] button [data-testid="stMarkdownContainer"] p::after {{
  content: "영수증 사진 고르기";
}}
.stApp [data-testid="stFileUploaderDropzoneInstructions"] span {{ font-size: 0; }}
.stApp [data-testid="stFileUploaderDropzoneInstructions"] span::after {{
  content: "엑셀(.xlsx)·CSV"; font-size: 13px; color: var(--rc-muted);
}}
.stApp [class*="st-key-files_"] [data-testid="stFileUploaderDropzoneInstructions"] span::after {{
  content: "사진·PDF · 여러 장 한 번에";
}}

/* 탭 */
.stApp [data-testid="stTab"] {{ padding: 10px 4px; }}
.stApp [data-testid="stTab"] p {{ font-weight: 600; font-size: 15px; }}
.stApp [data-testid="stTab"][aria-selected="true"] {{ color: var(--rc-accent); }}
.stApp [data-testid="stTab"][aria-selected="false"] {{ color: var(--rc-muted); }}
.stApp .react-aria-SelectionIndicator {{ background: var(--rc-accent) !important; }}

/* 펼치기 */
.stApp [data-testid="stExpander"] details {{
  border: 1px solid var(--rc-line); border-radius: var(--rc-radius); background: var(--rc-card);
}}
.stApp [data-testid="stExpander"] summary p {{ font-size: 14px; color: var(--rc-text); font-weight: 600; }}

/* 누를 때·고를 때 반응 */
.stApp [data-testid="stFileUploaderDropzone"] {{ transition: border-color .15s ease, background .15s ease; }}
.stApp [data-testid="stFileUploaderDropzone"]:hover {{ border-color: var(--rc-accent); }}
.stApp [data-testid="stTextInputRootElement"]:focus-within,
.stApp [data-baseweb="select"] > div:focus-within,
.stApp [data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within {{
  border-color: var(--rc-accent) !important; box-shadow: 0 0 0 3px var(--rc-soft);
}}
.stApp button:focus-visible, .stApp a:focus-visible, .stApp summary:focus-visible {{
  outline: 3px solid var(--rc-accent); outline-offset: 2px;
}}
.stApp button[data-testid^="stBaseButton-secondary"]:hover, .stApp [data-testid="stPopover"] button:hover {{
  border-color: var(--rc-accent); color: var(--rc-accent);
}}
.stApp [data-testid="stImage"] img {{ border: 1px solid var(--rc-line); border-radius: var(--rc-radius); }}
.stApp [data-testid="stMarkdownContainer"] p, .stApp [data-testid="stMarkdownContainer"] li {{ line-height: 1.65; }}
.stApp [data-testid="stAlert"] {{ border-radius: var(--rc-radius); }}

/* 단계 안내 */
.rc-steps {{ display: flex; gap: 8px; margin: 14px 0 6px; }}
.rc-step {{ flex: 1 1 0; min-width: 0; display: flex; gap: 10px; align-items: center;
  background: var(--rc-card); border: 1px solid var(--rc-line); border-radius: var(--rc-radius);
  padding: 10px 12px; color: var(--rc-muted); }}
.rc-step .n {{ flex: none; width: 26px; height: 26px; border-radius: 50%; display: flex; align-items: center;
  justify-content: center; font-weight: 800; font-size: 13px; background: var(--rc-bg); color: var(--rc-muted); }}
.rc-step b {{ display: block; font-size: 14px; font-weight: 700; color: var(--rc-muted); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }}
.rc-step small {{ display: block; font-size: 12px; color: var(--rc-muted); line-height: 1.4; }}
.rc-step.active {{ border-color: var(--rc-accent); }}
.rc-step.active .n {{ background: var(--rc-accent); color: var(--rc-on-accent); }}
.rc-step.active b {{ color: var(--rc-text); }}
.rc-step.done .n {{ background: var(--rc-soft); color: var(--rc-accent); }}
.rc-step.done b {{ color: var(--rc-text); }}

/* 한 줄 고정: 휴대폰에서도 칸이 아래로 떨어지지 않게 (키가 row 로 시작하는 묶음) */
[class*="st-key-row"] [data-testid="stHorizontalBlock"] {{ flex-wrap: nowrap !important; gap: 10px; }}
[class*="st-key-row"] [data-testid="stColumn"] {{ min-width: 0 !important; width: auto !important; }}

/* 경비 구분: 입력칸처럼 보이는 버튼 */
.rc-field-label {{ font-size: 14px; line-height: 1.6; color: var(--rc-text); margin: 4px 0 0; }}
.rc-field-label span {{ font-size: 12px; color: var(--rc-muted); margin-left: 6px; }}
.st-key-cats_field {{ margin-bottom: 6px; }}
.stApp .st-key-cats_field [data-testid="stPopover"] button {{
  background: var(--rc-card); border: 1px solid var(--rc-line); border-radius: var(--rc-btn-radius);
  min-height: 42px; padding: 0 14px; font-weight: 400; color: var(--rc-muted);
}}
.stApp .st-key-cats_field [data-testid="stPopover"] button > div {{
  width: 100%; justify-content: space-between;
}}
.stApp .st-key-cats_field [data-testid="stPopover"] button > div > div:first-child {{
  justify-content: flex-start; min-width: 0;
}}
.stApp .st-key-cats_field [data-testid="stPopover"] button > div > div:first-child span {{
  justify-content: flex-start; min-width: 0;
}}
.stApp .st-key-cats_field [data-testid="stPopover"] button p {{
  font-size: 15px; color: var(--rc-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}}
.stApp [data-testid="stButtonGroup"] {{ margin-top: 4px; }}
.rc-sub {{ font-size: 14px; font-weight: 700; color: var(--rc-text); margin: 14px 0 2px; }}

/* 경비 구분 칩 */
.rc-chips {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
.rc-chips-label {{ font-size: 13px; color: var(--rc-muted); margin-right: 2px; }}
.rc-chip {{ font-size: 13px; padding: 4px 10px; border-radius: 999px; background: var(--rc-soft);
  color: var(--rc-text); }}

/* 검토 안내 */
.st-key-review_banner {{ background: var(--rc-card); border-radius: var(--rc-radius); border: var(--rc-border);
  padding: 16px 18px; border-left: 4px solid var(--rc-warn) !important; }}
.rc-banner b {{ display: block; font-size: 16px; color: var(--rc-text); }}
.rc-banner span {{ font-size: 13px; color: var(--rc-muted); }}
.rc-banner.ok {{ background: var(--rc-card); border-radius: var(--rc-radius); padding: 14px 18px;
  border: var(--rc-border); border-left: 4px solid var(--rc-ok); }}

/* 영수증 카드 목록 */
.st-key-receipt_list {{ gap: 8px; }}
[class*="st-key-rowc_"] {{ background: var(--rc-card); border-radius: calc(var(--rc-radius) * 0.7);
  border: var(--rc-border); padding: 14px 12px 14px 16px; }}
.rc-row-top {{ display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }}
.rc-row-top b {{ font-size: 15px; color: var(--rc-text); overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; }}
.rc-amt {{ font-family: var(--rc-num); font-weight: 700; font-size: 15px; color: var(--rc-text);
  white-space: nowrap; }}
.rc-row-sub {{ font-size: 13px; color: var(--rc-muted); margin-top: 2px; display: flex; gap: 8px;
  align-items: center; flex-wrap: wrap; }}
.rc-badge {{ font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; }}
.rc-badge.pending {{ color: var(--rc-warn); background: var(--rc-soft); }}
.rc-badge.done {{ color: var(--rc-ok); background: var(--rc-soft); }}
@supports (background: color-mix(in srgb, red 10%, transparent)) {{
.rc-badge.pending {{ background: color-mix(in srgb, var(--rc-warn) 12%, transparent); }}
.rc-badge.done {{ background: color-mix(in srgb, var(--rc-ok) 12%, transparent); }}
}}
.rc-row-reason {{ font-size: 12.5px; color: var(--rc-muted); margin: 6px 0 2px; line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
[class*="st-key-rowc_"] button {{ min-height: 36px; padding: 0 10px; font-size: 13px; }}

/* 구분별 합계 */
.rc-sum {{ margin: 6px 0 4px; }}
.rc-sum-row {{ display: grid; grid-template-columns: 1fr auto auto; gap: 14px; padding: 8px 2px;
  border-bottom: 1px solid var(--rc-line); font-size: 14px; color: var(--rc-text); }}
.rc-sum-row span:nth-child(2) {{ color: var(--rc-muted); }}
.rc-sum-row b {{ font-family: var(--rc-num); min-width: 90px; text-align: right; }}
.rc-sum-row.total {{ border-bottom: none; font-weight: 700; }}

/* 휴대폰 */
@media (max-width: 640px) {{
  [data-testid="stPopoverBody"] {{ max-width: calc(100vw - 24px) !important; }}
  [data-testid="stMainBlockContainer"] {{ padding: 1rem 0.9rem 4rem; }}
  .rc-hero {{ font-size: calc(var(--rc-h1) * 0.82); margin: 18px 0 16px; }}
  .st-key-upload_card, .st-key-summary_card, .st-key-export_card, .st-key-login_card {{ padding: 16px 14px; }}
  .rc-total b {{ font-size: 30px; }}
  .stApp [data-testid="stFileUploaderDropzone"] {{ padding: 14px 12px; }}
  div[role="dialog"] {{ width: 100vw !important; max-width: 100vw !important; margin: 0 !important;
    border-radius: 16px 16px 0 0 !important; }}
  /* 아이폰: 16px보다 작은 입력칸을 누르면 화면을 확대한다 */
  .stApp input, .stApp textarea {{ font-size: 16px !important; }}
  /* 손가락으로 누르기 쉬운 크기 */
  .stApp button[data-testid^="stBaseButton"], .stApp [data-testid="stPopover"] button {{ min-height: 48px; }}
  [class*="st-key-rowc_"] button {{ min-height: 40px !important; }}
  .stApp [data-testid="stFileUploaderDropzone"] button {{ width: 100%; }}
  /* 아이폰 아래쪽 홈 막대만큼 여백 */
  [data-testid="stMainBlockContainer"] {{ padding-bottom: calc(4rem + env(safe-area-inset-bottom, 0px)); }}
  /* 단계 안내: 설명 숨기고 한 줄 3칸 */
  .rc-steps {{ gap: 6px; margin: 8px 0 2px; }}
  .rc-step {{ flex-direction: column; gap: 4px; padding: 8px 4px; text-align: center; }}
  .rc-step small {{ display: none; }}
  .rc-step b {{ font-size: 12px; }}
  /* 좁은 화면에서 보기 필터가 넘치면 옆으로 밀기 */
  .stApp [data-testid="stButtonGroup"] {{ overflow-x: auto; scrollbar-width: none; }}
}}

/* 결과 요약 */
.rc-total {{ margin: 2px 0 8px; }}
.rc-summary {{ display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between;
  gap: 8px 24px; margin: 4px 0 10px; }}
.rc-total small {{ display: block; font-size: 14px; color: var(--rc-muted); font-weight: 500; }}
.rc-total b {{ font-family: var(--rc-num); font-size: 34px; font-weight: 700; letter-spacing: -0.02em;
  color: var(--rc-text); }}
.rc-total em {{ font-style: normal; font-size: 15px; color: var(--rc-muted); margin-left: 8px; }}
.rc-stats {{ display: flex; gap: 18px; font-size: 14px; color: var(--rc-muted); }}
.rc-stats b {{ display: block; font-family: var(--rc-num); font-size: 20px; color: var(--rc-text); }}
.rc-stats .warn b {{ color: var(--rc-warn); }}
.rc-stats .ok b {{ color: var(--rc-ok); }}
.rc-meta {{ font-size: 13px; color: var(--rc-muted); margin-bottom: 6px; }}
"""
    if name == "receipt":
        css += """
.rc-brand { font-family: var(--rc-font); letter-spacing: -0.01em; }
.rc-brand::after { content: "RECEIPT → XLSX"; font-family: var(--rc-num); font-size: 11px;
  font-weight: 600; letter-spacing: 0.12em; color: var(--rc-muted); margin-left: 10px; }
.rc-hero { padding-bottom: 18px; border-bottom: 1.5px dashed var(--rc-line); }
.st-key-upload_card, .st-key-login_card {
  border: none !important; border-radius: 2px 2px 0 0 !important; position: relative; margin-bottom: 14px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.06);
}
.st-key-upload_card::after, .st-key-login_card::after {
  content: ""; position: absolute; left: 0; right: 0; bottom: -10px; height: 10px;
  background: linear-gradient(-45deg, transparent 6px, var(--rc-card) 0) 0 0 / 14px 10px repeat-x,
              linear-gradient(45deg, transparent 6px, var(--rc-card) 0) 0 0 / 14px 10px repeat-x;
}
.rc-summary { border-top: 1.5px dashed var(--rc-line); border-bottom: 1.5px dashed var(--rc-line);
  padding: 14px 0; }
.rc-total b, .rc-stats b { letter-spacing: 0; }
.rc-total small, .rc-stats { font-family: var(--rc-num); text-transform: uppercase; font-size: 12px;
  letter-spacing: 0.06em; }
.stApp [data-testid="stFileUploaderDropzone"] { background: transparent; }
"""
    if name == "team":
        css += """
.st-key-upload_card, .st-key-summary_card, .st-key-export_card, .st-key-login_card,
[class*="st-key-rowc_"] { box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04); }
"""
    if name == "toss":
        css += """
.st-key-upload_card, .st-key-result_card, .st-key-login_card { box-shadow: 0 1px 2px rgba(0,0,0,0.03); }
"""
    st.markdown(css + "\n</style>", unsafe_allow_html=True)
    return name
