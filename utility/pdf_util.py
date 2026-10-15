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
