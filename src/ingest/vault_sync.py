"""Vault sync — writes Markdown + YAML frontmatter to ./vault-sync/.

Files are created with chmod 444 (read-only for Obsidian).
Subdirectories: vault-sync/persons/ and vault-sync/documents/

Called after successful document ingest. Does not depend on FalkorDB
(that relationship data comes in Epic 3 via Wikilinks).
"""
from __future__ import annotations

import os
import stat
from datetime import datetime
from pathlib import Path

import structlog

log = structlog.get_logger()


def _safe_filename(name: str) -> str:
    """Sanitise a string for use as a filename."""
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip()


def write_person_note(vault_sync_path: str, *, email: str, display_name: str) -> Path:
    """Write vault-sync/persons/<email>.md and chmod 444."""
    persons_dir = Path(vault_sync_path) / "persons"
    persons_dir.mkdir(parents=True, exist_ok=True)

    fname = _safe_filename(email) + ".md"
    path = persons_dir / fname

    content = f"""---
email: "{email}"
display_name: "{display_name}"
type: person
---

# {display_name or email}

- **Email:** {email}
"""
    path.write_text(content, encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 444
    log.debug("vault_person_written", path=str(path))
    return path


def write_document_note(
    vault_sync_path: str,
    *,
    doc_id: str,
    source_path: str,
    source_type: str,
    sender_email: str,
    subject: str,
    ingested_at: datetime,
) -> Path:
    """Write vault-sync/documents/<doc_id>.md and chmod 444."""
    docs_dir = Path(vault_sync_path) / "documents"
    docs_dir.mkdir(parents=True, exist_ok=True)

    fname = _safe_filename(subject or doc_id)[:60] + f"_{doc_id[:8]}.md"
    path = docs_dir / fname

    content = f"""---
doc_id: "{doc_id}"
source_path: "{source_path}"
source_type: "{source_type}"
sender: "[[persons/{_safe_filename(sender_email)}]]"
ingested_at: "{ingested_at.isoformat()}"
---

# {subject or source_path}

- **Source:** `{source_path}`
- **Type:** {source_type}
- **Sender:** [[persons/{_safe_filename(sender_email)}]]
- **Ingested:** {ingested_at.strftime('%Y-%m-%d %H:%M')} UTC
"""
    path.write_text(content, encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 444
    log.debug("vault_document_written", path=str(path))
    return path
