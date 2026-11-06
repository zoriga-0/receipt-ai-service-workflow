"""
media.py

영수증 파일 처리: 아이폰 사진(HEIC) 변환, 화면 미리보기, 증빙 사진 zip 만들기.
"""

import hashlib
import io
import re
import zipfile

HEIC_EXT = (".heic", ".heif")
# 화면에서 받는 파일 형식 (안드로이드에서 자주 나오는 webp 포함)
UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp", "pdf", "heic", "heif"]
MAX_SIDE = 3500             # 이보다 큰 사진은 줄인다 (요즘 폰 카메라는 4000~8000px)
MAX_BYTES = 6 * 1024 * 1024  # 이보다 큰 사진은 다시 저장한다 (삼성 '모션 포토'는 영상이 붙어 커진다)


def file_hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _stem(name: str) -> str:
    return name.rsplit(".", 1)[0] if "." in name else name


def prepare_upload(name: str, data: bytes) -> tuple[str, bytes, str]:
    """
    업로드 파일을 분석하기 좋은 JPG/PNG로 맞춘다. 반환: (파일명, 바이트, 오류메시지)
      - 아이폰 HEIC, 안드로이드 WEBP → JPG
      - 옆으로 누운 사진(EXIF 회전 정보만 있는 사진, 안드로이드에 많음) → 똑바로 세워서 저장
      - 너무 큰 사진 → 긴 변 3500px로 줄여서 저장
      - PDF와 이미 괜찮은 JPG/PNG는 그대로 둔다
    """
    lower = name.lower()
    if lower.endswith(".pdf") or data[:5] == b"%PDF-":
        return name, data, ""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return name, data, ""
    try:
        if lower.endswith(HEIC_EXT):
            from pillow_heif import register_heif_opener

            register_heif_opener()
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "").upper()
        try:
            orientation = img.getexif().get(0x0112, 1)
        except Exception:  # noqa: BLE001
            orientation = 1
        needs = (
            fmt not in ("JPEG", "PNG")
            or orientation not in (None, 1)
            or max(img.size) > MAX_SIDE
            or len(data) > MAX_BYTES
        )
        if not needs:
            return name, data, ""
        img = ImageOps.exif_transpose(img)
        if fmt == "PNG" and img.mode in ("RGBA", "LA", "P"):
            # 투명 배경 스크린샷은 흰 바탕으로
            bg = Image.new("RGB", img.size, "white")
            bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
            img = bg
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=90)
        return _stem(name) + ".jpg", out.getvalue(), ""
    except ImportError:
        return name, data, f"{name}: HEIC 변환 패키지(pillow-heif)가 설치되어 있지 않아요."
    except Exception as e:  # noqa: BLE001
        if lower.endswith((".jpg", ".jpeg", ".png")):
            return name, data, ""  # 읽기만 실패한 일반 사진은 그대로 보내 본다
        return name, data, f"{name}: 사진 파일을 읽지 못했어요 ({type(e).__name__})"


def make_preview(name: str, data: bytes, max_side: int = 1600) -> bytes | None:
    """화면에 보여줄 이미지(JPEG). PDF는 첫 페이지를 그린다. 실패하면 None."""
    try:
        from PIL import Image, ImageOps

        if name.lower().endswith(".pdf"):
            import pypdfium2 as pdfium

            pdf = pdfium.PdfDocument(data)
            img = pdf[0].render(scale=2).to_pil()
        else:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        img = img.convert("RGB")
        img.thumbnail((max_side, max_side))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=88)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return None


def _safe(text, limit: int = 30) -> str:
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", str(text or "").strip()).strip("_")
    return s[:limit]


def evidence_filename(no: int, date, store, src_name: str) -> str:
    """엑셀 행 번호에 맞춘 증빙 파일명. 예) 01_2022-02-21_생선회관.jpg"""
    ext = "." + src_name.rsplit(".", 1)[-1].lower() if "." in src_name else ""
    parts = [f"{no:02d}", _safe(date, 10), _safe(store)]
    return "_".join(p for p in parts if p) + ext


def build_zip(items: list[tuple[str, bytes]]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for zip_name, data in items:
            z.writestr(zip_name, data)
    return out.getvalue()