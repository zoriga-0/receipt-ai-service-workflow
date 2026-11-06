"""
session_keep.py

새로고침해도 분석 결과가 남게 한다.

- 처음 들어오면 주소 끝에 임의 키(?s=...)를 붙이고, 분석 결과를 그 키로 Mac 메모리에 보관한다.
- 새로고침하면 주소의 키로 결과를 되찾는다. (Streamlit은 새로고침하면 화면 상태를 모두 잊는다)
- 메모리에만 두고 파일로 저장하지 않는다. 마지막 사용 후 1시간이 지나거나 앱을 다시 켜면 사라진다.
- 구글로 로그인했으면 같은 계정일 때만 되찾는다. (주소가 다른 사람에게 넘어가도 못 보게)

올리기만 하고 분석하지 않은 사진은 브라우저 규칙상 되살릴 수 없다 → 그때는 새로고침 경고(leave_guard)로 막는다.
"""

import secrets
import threading
import time

import streamlit as st

PARAM = "s"
TTL_SEC = 60 * 60
MAX_ITEMS = 50


@st.cache_resource
def _store() -> dict:
    return {"lock": threading.Lock(), "items": {}}


def _sweep(items: dict) -> None:
    now = time.time()
    for key in [k for k, v in items.items() if now - v["at"] > TTL_SEC]:
        items.pop(key, None)
    while len(items) > MAX_ITEMS:  # 오래된 것부터 지운다
        items.pop(min(items, key=lambda k: items[k]["at"]), None)


def restore(owner: str = "") -> bool:
    """
    화면이 처음 열릴 때(새로고침 포함) 한 번 부른다.
    보관해 둔 결과가 있으면 st.session_state.work로 되살리고 True를 돌려준다.
    """
    if "keep_key" in st.session_state:
        return False
    key = str(st.query_params.get(PARAM, ""))
    store = _store()
    with store["lock"]:
        _sweep(store["items"])
        item = store["items"].get(key) if key else None
    restored = bool(item and item["owner"] == owner and item.get("work"))
    if restored:
        work = item["work"]
        latest = work.pop("latest", None)  # 표에서 고친 값까지 되살린다
        if latest is not None:
            work["df"] = latest
        work["ver"] = work.get("ver", 0) + 1  # 표 위젯을 새로 그리게
        st.session_state.work = work
        st.session_state.restored = True
    else:
        key = secrets.token_urlsafe(16)
    st.session_state.keep_key = key
    st.query_params[PARAM] = key
    return restored


def sync(owner: str = "") -> None:
    """지금 결과(st.session_state.work)를 보관한다. 결과가 없으면 보관한 것도 지운다."""
    key = st.session_state.get("keep_key")
    if not key:
        return
    work = st.session_state.get("work")
    store = _store()
    with store["lock"]:
        if work:
            # 같은 dict를 가리키므로, 이후 화면에서 고친 내용도 그대로 따라간다
            store["items"][key] = {"owner": owner, "work": work, "at": time.time()}
        else:
            store["items"].pop(key, None)
