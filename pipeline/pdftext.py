"""Download a PDF once, keep it on disk, and read its text page by page."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pymupdf

from .common import RAW, session

PDF_DIR = RAW / "pdfs"


def _path(url: str) -> Path:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    return PDF_DIR / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".pdf")


def download(url: str, s=None) -> Path:
    p = _path(url)
    if p.exists() and p.stat().st_size > 0:
        return p
    s = s or session()
    r = s.get(url, timeout=60)
    r.raise_for_status()
    if not r.content.startswith(b"%PDF"):
        raise ValueError(f"not a PDF: {url}")
    p.write_bytes(r.content)
    return p


def pages(url: str, s=None, max_pages: int | None = None) -> list[str]:
    """Text of each page. Empty strings for scanned pages (no OCR on purpose)."""
    p = download(url, s)
    txt_cache = p.with_suffix(f".{max_pages or 'all'}.txt")
    if txt_cache.exists():
        return txt_cache.read_text().split("\f")
    with pymupdf.open(p) as doc:
        n = len(doc) if max_pages is None else min(max_pages, len(doc))
        out = [doc[i].get_text() for i in range(n)]
    txt_cache.write_text("\f".join(out))
    return out


def readable(page_texts: list[str]) -> bool:
    return sum(len(t.strip()) for t in page_texts) > 500
