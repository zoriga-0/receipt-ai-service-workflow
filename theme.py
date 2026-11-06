"""
theme.py

화면 디자인 (CSS). 시안 3가지:
  toss    : 밝은 회색 바탕 + 흰 카드 + 파란 버튼, 큰 글씨 (토스 느낌)
  minimal : 흰 바탕 + 얇은 선 + 검은 버튼, 담백하게 (노션 느낌)
  receipt : 종이 색 바탕 + 점선 + 고정폭 숫자 (영수증 느낌)

기본값은 환경변수 UI_THEME, 주소 끝에 ?theme=receipt 처럼 붙이면 그 시안으로 볼 수 있다.
라이트/다크는 휴대폰·PC 설정을 따라 자동으로 바뀐다.
"""

import os

import streamlit as st

THEMES = ("toss", "minimal", "receipt")

FONT_IMPORTS = """
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&display=swap');
"""

_SANS = "'Pretendard Variable', Pretendard, -apple-system, 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif"
_MONO = "'JetBrains Mono', 'Pretendard Variable', Pretendard, monospace"

# 시안별 색·모양 (라이트, 다크)
VARS = {
    "toss": (
        dict(bg="#F2F4F6", card="#FFFFFF", text="#191F28", muted="#6B7684", line="#E5E8EB",
             accent="#3182F6", on_accent="#FFFFFF", soft="#E8F3FF", warn="#F04452",
             radius="20px", btn_radius="14px", border="0px solid transparent",
             font=_SANS, num=_SANS, brand=_SANS, h1="32px", h1_weight="700", btn_h="54px"),
        dict(bg="#101013", card="#1D1D22", text="#EDEDF0", muted="#9E9EA7", line="#2C2C33",
             accent="#3182F6", on_accent="#FFFFFF", soft="#1B2A40", warn="#FF6B76"),
    ),
    "minimal": (
        dict(bg="#FFFFFF", card="#FFFFFF", text="#37352F", muted="#787774", line="#E9E9E7",
             accent="#2F2F2D", on_accent="#FFFFFF", soft="#F7F7F5", warn="#D44C47",
             radius="10px", btn_radius="8px", border="1px solid var(--rc-line)",
             font=_SANS, num=_SANS, brand=_SANS, h1="28px", h1_weight="600", btn_h="46px"),
        dict(bg="#191919", card="#191919", text="#E6E6E4", muted="#9B9A97", line="#2F2F2F",
             accent="#E6E6E4", on_accent="#191919", soft="#252525", warn="#FF7369"),
    ),
    "receipt": (
        dict(bg="#E7E3DA", card="#FFFDF7", text="#1C1B19", muted="#78746B", line="#CBC5B8",
             accent="#1C1B19", on_accent="#FFFDF7", soft="#F4F0E6", warn="#C2410C",
             radius="4px", btn_radius="4px", border="1.5px dashed var(--rc-line)",
             font=_SANS, num=_MONO, brand=_MONO, h1="28px", h1_weight="700", btn_h="50px"),
        dict(bg="#121211", card="#1C1B19", text="#EDE9E0", muted="#A29D92", line="#45423B",
             accent="#EDE9E0", on_accent="#121211", soft="#26241F", warn="#FB923C"),
    ),
}


def current_theme() -> str:
    try:
        q = str(st.query_params.get("theme", "")).lower()
    except Exception:  # noqa: BLE001
        q = ""
    name = q or os.getenv("UI_THEME", "toss").lower()
    return name if name in THEMES else "toss"


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
html, body {{ overscroll-behavior-y: none; }}

.stApp {{ background: var(--rc-bg); color: var(--rc-text); }}
.stApp, .stApp p, .stApp label, .stApp li, .stApp input, .stApp textarea, .stApp button,
.stApp h1, .stApp h2, .stApp h3, .stApp summary, .stApp [data-testid="stTab"] p {{
  font-family: var(--rc-font) !important; letter-spacing: -0.01em;
}}
.stApp [data-testid="stIconMaterial"] {{ font-family: 'Material Symbols Rounded' !important; letter-spacing: 0; }}
[data-testid="stMainBlockContainer"] {{ max-width: 980px; padding-top: 2.2rem; padding-bottom: 5rem; }}
.stApp [data-testid="stCaptionContainer"], .stApp [data-testid="stCaptionContainer"] p {{ color: var(--rc-muted); }}

/* 머리글 */
.rc-brand {{ font-family: var(--rc-brand); font-weight: 700; font-size: 17px; color: var(--rc-text); }}
.rc-hero {{ font-size: var(--rc-h1); font-weight: var(--rc-h1-weight); line-height: 1.3;
  color: var(--rc-text); margin: 28px 0 22px; letter-spacing: -0.03em; }}
.rc-hero span {{ color: var(--rc-muted); }}
.rc-section {{ font-size: 20px; font-weight: 700; color: var(--rc-text); margin: 8px 0 4px; }}

/* 카드 */
.st-key-upload_card, .st-key-result_card, .st-key-login_card {{
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
  content: "사진 고르기"; font-size: 14px; font-weight: 600;
}}
.stApp [data-testid="stFileUploaderDropzoneInstructions"] span {{ font-size: 0; }}
.stApp [data-testid="stFileUploaderDropzoneInstructions"] span::after {{
  content: "사진·PDF·아이폰 HEIC · 여러 장 한 번에"; font-size: 13px; color: var(--rc-muted);
}}

/* 탭 */
.stApp [data-testid="stTab"] {{ padding: 10px 4px; }}
.stApp [data-testid="stTab"] p {{ font-weight: 600; font-size: 15px; }}
.stApp [data-testid="stTab"][aria-selected="true"] {{ color: var(--rc-accent); }}
.stApp [data-testid="stTab"][aria-selected="false"] {{ color: var(--rc-muted); }}
.stApp .react-aria-SelectionIndicator {{ background: var(--rc-accent) !important; }}

/* 펼치기 */
.stApp [data-testid="stExpander"] details {{
  border: 1px solid var(--rc-line); border-radius: var(--rc-btn-radius); background: transparent;
}}
.stApp [data-testid="stExpander"] summary p {{ font-size: 14px; color: var(--rc-muted); font-weight: 500; }}

/* 결과 요약 */
.rc-summary {{ display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between;
  gap: 8px 24px; margin: 4px 0 10px; }}
.rc-total small {{ display: block; font-size: 14px; color: var(--rc-muted); font-weight: 500; }}
.rc-total b {{ font-family: var(--rc-num); font-size: 34px; font-weight: 700; letter-spacing: -0.02em;
  color: var(--rc-text); }}
.rc-total em {{ font-style: normal; font-size: 15px; color: var(--rc-muted); margin-left: 8px; }}
.rc-stats {{ display: flex; gap: 18px; font-size: 14px; color: var(--rc-muted); }}
.rc-stats b {{ display: block; font-family: var(--rc-num); font-size: 20px; color: var(--rc-text); }}
.rc-stats .warn b {{ color: var(--rc-warn); }}
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
    if name == "toss":
        css += """
.st-key-upload_card, .st-key-result_card, .st-key-login_card { box-shadow: 0 1px 2px rgba(0,0,0,0.03); }
"""
    st.markdown(css + "\n</style>", unsafe_allow_html=True)
    return name
