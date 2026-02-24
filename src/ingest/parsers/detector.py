"""Content-type detection: extension-first with magika fallback."""
from __future__ import annotations

import functools
from pathlib import Path


_EXT_MAP = {
    "mbox": "mbox", "mbx": "mbox",
    "pdf": "pdf",
    "md": "markdown", "markdown": "markdown",
    "eml": "mbox",
}


@functools.lru_cache(maxsize=1)
def _get_magika():
    try:
        from magika import Magika
        return Magika()
    except ImportError:
        return None


def detect_type(path: str) -> str:
    """Return 'mbox' | 'pdf' | 'markdown' | 'unknown'."""
    ext = Path(path).suffix.lstrip(".").lower()
    if ext in _EXT_MAP:
        return _EXT_MAP[ext]

    # Magika fallback for ambiguous/missing extensions
    magika = _get_magika()
    if magika is not None:
        try:
            result = magika.identify_path(path)
            label = result.dl.ct_label   # magika 1.0.x API
            if label == "email":
                return "mbox"
            if label == "pdf":
                return "pdf"
            if label in ("markdown", "txt"):
                return "markdown"
        except Exception:
            pass

    return "unknown"
