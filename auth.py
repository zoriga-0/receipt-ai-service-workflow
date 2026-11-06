"""
auth.py

들어오는 문: 구글 로그인 + (선택) 접속 비밀번호

- 구글 로그인은 Streamlit 내장 기능(st.login)을 쓴다. 설정은 .streamlit/secrets.toml [auth].
  로그인 정보는 브라우저 쿠키에 30일 남아서 새로고침해도 다시 로그인하지 않는다.
- 접속 비밀번호(APP_PASSWORD)를 정해 두면 로그인 화면에 '비밀번호로 들어가기'가 같이 나온다.
  (내 Mac에서 시험할 때, 발표장에서 구글 로그인이 안 될 때 쓰는 비상구. 드라이브 저장은 안 된다)
- 둘 다 설정하지 않으면 그냥 열린다.
"""

import hmac

import streamlit as st

import config

PROVIDER = "google"
_PLACEHOLDERS = ("여기에", "xxxx")


def google_configured() -> bool:
    """secrets.toml에 구글 로그인 키가 실제로 채워져 있는지."""
    try:
        auth = st.secrets["auth"]
        google = auth.get(PROVIDER) or {}
        values = [
            str(auth.get("redirect_uri") or ""),
            str(auth.get("cookie_secret") or ""),
            str(google.get("client_id") or ""),
            str(google.get("client_secret") or ""),
        ]
    except Exception:  # noqa: BLE001  secrets.toml이 없으면 오류가 난다
        return False
    return all(v and not any(p in v for p in _PLACEHOLDERS) for v in values)


def _user_field(key: str) -> str:
    try:
        return str(st.user[key] or "")
    except Exception:  # noqa: BLE001
        return ""


def google_user() -> dict | None:
    """구글로 로그인했으면 {name, email}, 아니면 None."""
    if not google_configured():
        return None
    try:
        if not st.user.is_logged_in:
            return None
    except Exception:  # noqa: BLE001
        return None
    return {"name": _user_field("name"), "email": _user_field("email")}


def access_token() -> str:
    """구글 드라이브를 부를 때 쓰는 토큰 (secrets.toml에 expose_tokens = ["access"] 필요)."""
    try:
        return st.user.tokens["access"] or ""
    except Exception:  # noqa: BLE001
        return ""


def _password_form() -> None:
    with st.form("password_login", border=False):
        pw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("들어가기", width="stretch"):
            if hmac.compare_digest(pw, config.APP_PASSWORD):
                st.session_state.authed = True
                st.rerun()
            st.error("비밀번호가 맞지 않아요.")


def gate() -> dict:
    """
    들어올 수 있으면 사용자 정보를 돌려준다.
      구글 로그인: {"name": ..., "email": ...}
      비밀번호로 들어왔거나 문이 없으면: {}
    들어올 수 없으면 로그인 화면을 그리고 여기서 멈춘다(st.stop).
    """
    user = google_user()
    if user:
        if config.ALLOWED_EMAILS and user["email"].lower() not in config.ALLOWED_EMAILS:
            st.error(f"{user['email']} 계정으로는 쓸 수 없어요.")
            st.button("다른 계정으로 로그인", on_click=st.logout)
            st.stop()
        return user

    use_google = google_configured()
    if st.session_state.get("authed") or not (use_google or config.APP_PASSWORD):
        return {}

    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        if use_google:
            st.button("Google 계정으로 로그인", type="primary", width="stretch",
                      on_click=st.login, args=(PROVIDER,))
            st.caption("정리한 기록은 내 구글 드라이브에만 저장돼요. 영수증 사진은 저장하지 않아요.")
            if config.APP_PASSWORD:
                with st.expander("비밀번호로 들어가기"):
                    _password_form()
        else:
            _password_form()
    st.stop()
