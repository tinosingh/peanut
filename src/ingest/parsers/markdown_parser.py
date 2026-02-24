"""Markdown parser — strips markup and returns plain text."""
from __future__ import annotations

import re
from pathlib import Path


def parse_markdown(path: str) -> str:
    """Read a markdown file and return plain text (markup stripped)."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    # Strip YAML frontmatter
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            raw = raw[end + 4:]
    # Strip markdown syntax: headers, bold, italic, links, code
    text = re.sub(r"^#{1,6}\s+", "", raw, flags=re.MULTILINE)  # headers
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)         # bold/italic
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)              # inline code
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)                 # images
    text = re.sub(r"\[(.+?)\]\(.*?\)", r"\1", text)             # links
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)  # bullets
    return text.strip()
