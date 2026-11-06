"""
ui_extras.py

화면 보조 기능
  - is_production(): https로 접속했으면 배포 사이트로 보고, 개발용 정보를 숨긴다.
  - leave_guard(): 분석 결과가 있을 때 새로고침·창 닫기를 하면 브라우저 경고를 띄운다.
  - AnalysisProgress: 분석 중 몇 장째인지, 걸린 시간, 남은 시간, 끝난 영수증 요약을 보여준다.
"""

import os
import time

import streamlit as st
import streamlit.components.v1 as components


##################################################
# http / https 분기
##################################################

def is_production() -> bool:
    """
    https로 접속했으면 배포 사이트(True), http(로컬)면 개발 환경(False).
    배포 사이트에서도 개발용 정보를 보고 싶으면 환경변수 SHOW_DEBUG=1.
    """
    if os.getenv("SHOW_DEBUG", "").strip().lower() in ("1", "true", "yes"):
        return False
    try:
        url = str(getattr(st.context, "url", "") or "")
        headers = st.context.headers
        proto = headers.get("X-Forwarded-Proto") or headers.get("x-forwarded-proto") or ""
    except Exception:  # noqa: BLE001  확인할 수 없으면 개발 환경으로 본다
        return False
    return url.startswith("https://") or proto.lower().startswith("https")


##################################################
# 새로고침·창 닫기 경고
##################################################

def leave_guard(active: bool) -> None:
    """
    active=True: 새로고침·창 닫기·뒤로 가기 때 브라우저가 '나가시겠습니까?' 경고를 띄운다.
    active=False: 경고를 끈다.

    - 경고 함수는 페이지 본문(window.parent)에 한 번만 심는다. 이 작은 iframe 안에서 만든 함수는
      Streamlit이 iframe을 다시 그리면 동작하지 않아서, 켜고 끄는 값(__receiptGuardOn)만 여기서 바꾼다.
    - 문구는 브라우저가 정한다(보안상 직접 바꿀 수 없음).
    - 아이폰 사파리는 이 경고를 지원하지 않는다. 그래서 분석 결과는 session_keep으로 되살린다.
    """
    flag = "true" if active else "false"
    components.html(
        f"""<script>
(function () {{
  const w = window.parent;
  if (!w.__receiptGuardInstalled) {{
    const s = w.document.createElement('script');
    s.textContent = "window.addEventListener('beforeunload', function (e) {{" +
      " if (window.__receiptGuardOn) {{ e.preventDefault(); e.returnValue = ''; return ''; }} }});";
    w.document.head.appendChild(s);
    w.__receiptGuardInstalled = true;
  }}
  w.__receiptGuardOn = {flag};
}})();
</script>""",
        height=0,
    )


##################################################
# 분석 진행 표시
##################################################

class AnalysisProgress:
    """process_receipts(on_progress=...)에 update를 넘겨 쓴다."""

    def __init__(self, total: int):
        self.start = time.monotonic()
        self.box = st.status(
            f"영수증 {total}장 분석 시작 · 첫 결과까지 20초 정도 걸려요", expanded=True
        )
        self.bar = self.box.progress(0.0)
        self.box.caption("분석이 끝날 때까지 새로고침하거나 창을 닫지 마세요.")

    def update(self, done: int, total: int, name: str, row: dict | None = None) -> None:
        elapsed = time.monotonic() - self.start
        label = f"{done}/{total}장 완료 · {elapsed:.0f}초 경과"
        if done < total:
            label += f" · 약 {elapsed / done * (total - done):.0f}초 남음"
        self.bar.progress(done / total)
        self.box.update(label=label)

        if row:
            amount = row.get("결제금액")
            amount_txt = (
                f"{amount:,.0f} {row.get('통화') or ''}".strip()
                if isinstance(amount, (int, float))
                else "금액 없음"
            )
            flag = " · 검토 필요" if row.get("검토여부") == "검토 필요" else ""
            self.box.write(f"{name} — {row.get('상호명') or '상호 없음'} {amount_txt}{flag}")
        else:
            self.box.write(f"{name} 완료")

    def finish(self, total: int) -> float:
        """끝난 시간(초)을 돌려준다."""
        elapsed = time.monotonic() - self.start
        per = elapsed / total if total else 0
        self.box.update(
            label=f"분석 완료 · {total}장 · {elapsed:.0f}초 (장당 평균 {per:.1f}초)",
            state="complete",
            expanded=False,
        )
        return elapsed