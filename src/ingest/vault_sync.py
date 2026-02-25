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

    # Ensure filename is useful even if subject is empty/all-special-chars
    safe_subject = _safe_filename(subject or doc_id)
    if not safe_subject or len(safe_subject.strip()) == 0:
        safe_subject = f"doc-{doc_id[:12]}"
    fname = safe_subject[:60] + f"_{doc_id[:8]}.md"
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


def update_document_wikilinks(
    vault_sync_path: str,
    doc_id: str,
    mentions: list[str],
) -> Path | None:
    """Append [[Person/Name]] Wikilinks to a document note from :MENTIONS edges.

    Reads the existing document note (any file matching *_<doc_id[:8]>.md),
    rewrites the Wikilinks section, and re-sets chmod 444.

    Args:
        vault_sync_path: Root of vault-sync directory.
        doc_id:          Document UUID.
        mentions:        List of person display_names from FalkorDB :MENTIONS edges.

    Returns:
        Path to the updated file, or None if not found.
    """
    docs_dir = Path(vault_sync_path) / "documents"
    suffix = f"_{doc_id[:8]}.md"
    matches = list(docs_dir.glob(f"*{suffix}"))
    if not matches:
        log.warning("vault_doc_not_found_for_wikilinks", doc_id=doc_id)
        return None
    if len(matches) > 1:
        log.warning("vault_doc_multiple_matches", doc_id=doc_id, count=len(matches), paths=[str(p) for p in matches])

    path = matches[0]
    # chmod +w temporarily
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

    existing = path.read_text(encoding="utf-8")
    # Strip any existing Wikilinks section
    marker = "\n## Mentions\n"
    if marker in existing:
        existing = existing[: existing.index(marker)]

    if mentions:
        wikilinks = "\n".join(
            f"- [[persons/{_safe_filename(name)}]]" for name in sorted(mentions)
        )
        existing = existing.rstrip("\n") + f"\n{marker}{wikilinks}\n"

    path.write_text(existing, encoding="utf-8")
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 444
    log.debug("vault_wikilinks_updated", doc_id=doc_id, count=len(mentions))
    return path
