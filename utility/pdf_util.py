"""PDF helpers (moved verbatim from gui/downloader.py)."""
import os


def _pdf_page_count(pdf_path: str) -> int:
    """只取页数，不把每页内容写进提示词。"""
    import fitz

    pdf_path = (pdf_path or "").strip()
    if not pdf_path or not os.path.isfile(pdf_path):
        return 0
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return 0
    try:
        return len(doc)
    finally:
        doc.close()


def _images_to_temp_pdf(paths: list[str]) -> str:
    """按给定顺序把图片合成一份临时 PDF。"""
    import tempfile
    from io import BytesIO

    import fitz
    from PIL import Image

    fd, dest = tempfile.mkstemp(prefix="aicomposer_slide_", suffix=".pdf")
    os.close(fd)
    doc = fitz.open()
    try:
        for src in paths:
            with Image.open(src) as im:
                rgb = im.convert("RGB")
                width, height = rgb.size
                buf = BytesIO()
                rgb.save(buf, "JPEG", quality=85, optimize=True)
            page = doc.new_page(width=width, height=height)
            page.insert_image(page.rect, stream=buf.getvalue())
        doc.save(dest, deflate=True, garbage=4)
    except Exception:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise
    finally:
        doc.close()
    return dest


def pdf_text_content(pdf_path: str) -> dict:
    """读 PDF 里真正的文字（PyMuPDF），给「分析」用。

    返回 {"text", "pages", "image_pages", "scanned", "error"}：
    ``scanned`` = 有页但读不出文字、而且页上有图片（多半是扫描件，要先 OCR）。
    注意：``_pdf_pages_as_scene_source`` 只给场景生成写文件名 + 页数（让模型自己看 PDF），不读文字。
    """
    import fitz

    out = {"text": "", "pages": 0, "image_pages": 0, "scanned": False, "error": ""}
    pdf_path = (pdf_path or "").strip()
    if not pdf_path or not os.path.isfile(pdf_path):
        out["error"] = "找不到文件"
        return out
    try:
        doc = fitz.open(pdf_path)
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return out
    try:
        if doc.needs_pass:
            out["error"] = "PDF 有密码"
            return out
        parts = []
        for page in doc:
            out["pages"] += 1
            t = (page.get_text("text") or "").strip()
            if t:
                parts.append(t)
            elif page.get_images(full=False):
                out["image_pages"] += 1
        out["text"] = "\n\n".join(parts).strip()
        out["scanned"] = not out["text"] and out["image_pages"] > 0
        return out
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)
        return out
    finally:
        doc.close()
