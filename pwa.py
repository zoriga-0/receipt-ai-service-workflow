"""
pwa.py

아이폰에서 '홈 화면에 추가'했을 때 앱처럼 보이게 한다.
  - 아이콘: 영수증(🧾) 모양 이미지
  - 이름: 영수증 콜렉터
  - 상단 색, 전체 화면 실행

Streamlit은 페이지의 <head>를 직접 고칠 수 없어서,
Streamlit 기본 페이지(index.html)에 필요한 태그를 끼워 넣는다.
여러 번 실행해도 한 번만 들어간다.

사용법: 앱을 켜기 전에 `python pwa.py` 를 한 번 실행한다.
"""

import os
import re

APP_NAME = "영수증 콜렉터"
THEME_COLOR = "#F3F4F6"  # 라이트 테마 배경색과 맞춘 상단 색
THEME_COLOR_DARK = "#0E1117"  # 다크 테마 배경색과 맞춘 상단 색
ICON_BG = "#2563EB"  # 아이콘 바탕색
ICON_FILE = "apple-touch-icon.png"
MARK = "<!-- receipt-pwa v2 -->"
END_MARK = "<!-- /receipt-pwa -->"
# 예전 버전이 넣은 태그 묶음 (지우고 새로 넣기 위해)
OLD_BLOCK = re.compile(r"<!-- receipt-pwa -->.*?<meta name=\"theme-color\"[^>]*>\n?", re.S)
NEW_BLOCK = re.compile(re.escape(MARK) + r".*?" + re.escape(END_MARK) + r"\n?", re.S)

HEAD_TAGS = f"""{MARK}
<link rel="apple-touch-icon" href="/{ICON_FILE}">
<meta name="apple-mobile-web-app-title" content="{APP_NAME}">
<meta name="application-name" content="{APP_NAME}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="{THEME_COLOR}">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="{THEME_COLOR_DARK}">
{END_MARK}
"""


def streamlit_static_dir() -> str:
    import streamlit

    return os.path.join(os.path.dirname(streamlit.__file__), "static")


def make_icon(path: str, size: int = 180) -> None:
    """영수증 모양 아이콘을 그린다. (크게 그린 뒤 줄여서 테두리를 매끄럽게)"""
    from PIL import Image, ImageDraw

    s = 4  # 4배로 그린 뒤 축소
    W = size * s
    img = Image.new("RGB", (W, W), ICON_BG)
    d = ImageDraw.Draw(img)

    # 종이: 가운데 세로로 긴 흰 사각형, 위아래는 톱니 모양
    left, right = int(W * 0.26), int(W * 0.74)
    top, bottom = int(W * 0.16), int(W * 0.84)
    teeth = 6
    tw = (right - left) / teeth
    th = tw * 0.55
    poly = []
    for i in range(teeth + 1):  # 위쪽 톱니 (왼→오)
        x = left + i * tw
        poly.append((x, top + th))
        if i < teeth:
            poly.append((x + tw / 2, top))
    for i in range(teeth, -1, -1):  # 아래쪽 톱니 (오→왼)
        x = left + i * tw
        poly.append((x, bottom - th))
        if i > 0:
            poly.append((x - tw / 2, bottom))
    d.polygon(poly, fill="#FFFFFF")

    # 글줄: 회색 짧은 줄들 + 맨 아래 굵은 합계 줄
    line_l, line_r = left + int(W * 0.07), right - int(W * 0.07)
    lh = int(W * 0.028)
    y = top + int(W * 0.13)
    for ratio in (1.0, 0.75, 0.9, 0.6):
        d.rounded_rectangle(
            (line_l, y, line_l + (line_r - line_l) * ratio, y + lh), radius=lh // 2, fill="#CBD5E1"
        )
        y += int(W * 0.075)
    y += int(W * 0.02)
    d.rounded_rectangle((line_l, y, line_r, y + int(lh * 1.6)), radius=lh, fill="#1E3A8A")

    img = img.resize((size, size), Image.LANCZOS)
    img.save(path, "PNG")


def patch_index(static_dir: str) -> str:
    """index.html에 태그를 넣고 아이콘 파일을 만든다. 결과를 한 줄로 돌려준다."""
    index = os.path.join(static_dir, "index.html")
    if not os.path.exists(index):
        return f"index.html을 찾지 못함: {index}"

    make_icon(os.path.join(static_dir, ICON_FILE))

    with open(index, encoding="utf-8") as f:
        html = f.read()
    # 예전에 넣은 태그가 있으면 지우고 새로 넣는다 (설정을 바꿔도 반영되게)
    html = NEW_BLOCK.sub("", OLD_BLOCK.sub("", html))
    if "</head>" not in html:
        return "index.html에서 </head>를 찾지 못함"
    html = html.replace("</head>", HEAD_TAGS + "</head>", 1)
    with open(index, "w", encoding="utf-8") as f:
        f.write(html)
    return "적용 완료"


def setup() -> str:
    """앱 안에서 불러도 실패로 앱이 멈추지 않게 한다."""
    try:
        return patch_index(streamlit_static_dir())
    except Exception as e:  # noqa: BLE001
        return f"홈 화면 설정 실패: {type(e).__name__}: {e}"


if __name__ == "__main__":
    print("[pwa]", setup())