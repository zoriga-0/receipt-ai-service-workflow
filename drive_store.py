"""
drive_store.py

구글 로그인한 사용자의 '본인 구글 드라이브'에 경비 기록을 저장하고 불러온다.
이 서비스(Mac mini)에는 아무것도 저장하지 않는다 (DB 없음).

- 권한(scope)은 drive.file 하나만 쓴다.
  → 이 앱이 만든 파일·폴더만 보고 고칠 수 있다. 사용자의 다른 드라이브 파일은 볼 수 없다.
- 내 드라이브 / 영수증 콜렉터 / 경비기록.xlsx 한 파일에 모든 기록을 모은다.
  같은 파일을 덮어쓰지만, 구글 드라이브가 이전 버전을 자동으로 보관한다.
- 영수증 사진은 올리지 않는다. 정리된 표만 저장한다.
- 별도 라이브러리 없이 requests로 Drive REST API를 직접 부른다.
"""

import json
import uuid

import requests

DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"

FOLDER_NAME = "영수증 콜렉터"
RECORD_FILE = "경비기록.xlsx"
FOLDER_MIME = "application/vnd.google-apps.folder"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_FIELDS = "id,name,webViewLink,modifiedTime"


class DriveError(Exception):
    """드라이브 요청 실패 (화면에 그대로 보여줄 수 있는 문장)."""


class DriveAuthError(DriveError):
    """로그인 만료 또는 드라이브 권한 없음 → 다시 로그인해야 함."""


class DriveConflict(DriveError):
    """불러온 뒤 다른 창에서 먼저 저장해서, 그대로 저장하면 그 내용을 덮어쓰게 됨."""


def _req(method: str, url: str, token: str, headers: dict | None = None, **kw) -> requests.Response:
    h = {"Authorization": f"Bearer {token}"}
    h.update(headers or {})
    try:
        r = requests.request(method, url, headers=h, timeout=30, **kw)
    except requests.RequestException as e:
        raise DriveError(f"구글 드라이브에 연결하지 못했어요 ({type(e).__name__}).") from e

    if r.status_code == 401:
        raise DriveAuthError("구글 로그인이 만료됐어요. 로그아웃한 뒤 다시 로그인해 주세요.")
    if r.status_code == 403 and "insufficient" in r.text.lower():
        raise DriveAuthError(
            "드라이브 권한이 없어요. 다시 로그인할 때 '구글 드라이브' 항목에 체크해 주세요."
        )
    if not r.ok:
        raise DriveError(f"구글 드라이브 요청이 실패했어요 ({r.status_code}): {r.text[:200]}")
    return r


def _q(value: str) -> str:
    """검색어 안의 따옴표·역슬래시 처리."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find(token: str, name: str, mime: str = "", parent: str = "") -> dict | None:
    q = [f"name = '{_q(name)}'", "trashed = false"]
    if mime:
        q.append(f"mimeType = '{mime}'")
    if parent:
        q.append(f"'{_q(parent)}' in parents")
    r = _req("GET", DRIVE_FILES, token, params={
        "q": " and ".join(q),
        "spaces": "drive",
        "fields": f"files({_FIELDS})",
        "orderBy": "modifiedTime desc",
        "pageSize": 10,
    })
    files = r.json().get("files", [])
    return files[0] if files else None


def get_folder(token: str) -> str:
    """'영수증 콜렉터' 폴더 ID. 없으면 만든다. (로그인 직후 권한 확인용으로도 쓴다)"""
    found = _find(token, FOLDER_NAME, mime=FOLDER_MIME)
    if found:
        return found["id"]
    r = _req("POST", DRIVE_FILES, token, params={"fields": "id"},
             json={"name": FOLDER_NAME, "mimeType": FOLDER_MIME})
    return r.json()["id"]


def load_records(token: str, folder_id: str) -> tuple[bytes | None, dict | None]:
    """
    경비기록.xlsx 내용을 돌려준다.
    반환: (파일 바이트, 파일 정보{id, webViewLink, modifiedTime}) / 아직 없으면 (None, None)
    """
    info = _find(token, RECORD_FILE, parent=folder_id)
    if not info:
        return None, None
    r = _req("GET", f"{DRIVE_FILES}/{info['id']}", token, params={"alt": "media"})
    return r.content, info


def _multipart(meta: dict, data: bytes, mime: str) -> tuple[bytes, str]:
    boundary = "receipt_" + uuid.uuid4().hex
    head = (
        f"--{boundary}\r\n"
        "Content-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(meta, ensure_ascii=False)}\r\n"
        f"--{boundary}\r\n"
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return head + data + tail, f"multipart/related; boundary={boundary}"


def save_records(token: str, folder_id: str, data: bytes, loaded_modified: str | None) -> dict:
    """
    경비기록.xlsx를 저장한다. 없으면 새로 만들고, 있으면 같은 파일을 새 버전으로 덮어쓴다.

    loaded_modified: 불러올 때의 수정 시각 (불러올 때 파일이 없었으면 None).
    그 사이 다른 창에서 저장했으면 DriveConflict를 내서 덮어쓰지 않는다.
    반환: 저장된 파일 정보 {id, name, webViewLink, modifiedTime}
    """
    current = _find(token, RECORD_FILE, parent=folder_id)
    now_modified = current["modifiedTime"] if current else None
    if now_modified != loaded_modified:
        raise DriveConflict(
            "불러온 뒤 다른 창에서 드라이브 기록이 바뀌었어요. 덮어쓰지 않도록 저장을 멈췄어요. "
            "드라이브 기록을 다시 불러와서 저장해 주세요."
        )

    params = {"uploadType": "multipart", "fields": _FIELDS}
    if current:
        body, ctype = _multipart({"name": RECORD_FILE}, data, XLSX_MIME)
        r = _req("PATCH", f"{DRIVE_UPLOAD}/{current['id']}", token,
                 params=params, data=body, headers={"Content-Type": ctype})
    else:
        body, ctype = _multipart({"name": RECORD_FILE, "parents": [folder_id]}, data, XLSX_MIME)
        r = _req("POST", DRIVE_UPLOAD, token,
                 params=params, data=body, headers={"Content-Type": ctype})
    return r.json()
