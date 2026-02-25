"""POST /ingest/text — accept raw text and queue it via the drop zone.

Used by the MCP add_document tool. Writes text to a temp .md file in the
drop zone; the ingest watcher picks it up and processes it normally.
"""
from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

log = structlog.get_logger()

router = APIRouter()


class IngestTextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestTextResponse(BaseModel):
    queued: bool
    doc_id: str
    file: str


@router.post("/ingest/text", response_model=IngestTextResponse)
async def ingest_text(body: IngestTextRequest) -> IngestTextResponse:
    """Write raw text to the drop zone as a Markdown file for ingest."""
    drop_zone = Path(os.getenv("DROP_ZONE_PATH", "/drop-zone"))
    if not drop_zone.is_dir():
        raise HTTPException(status_code=503, detail="Drop zone not available")

    doc_id = str(uuid.uuid4())

    # Build YAML-safe frontmatter from metadata
    fm_lines = ["---", f"doc_id: {doc_id}"]
    for key, val in body.metadata.items():
        safe_key = str(key)[:64].replace(":", "_")
        safe_val = str(val)[:1000].replace("\n", " ")
        fm_lines.append(f"{safe_key}: {safe_val!r}")
    fm_lines.append("---\n")
    frontmatter = "\n".join(fm_lines)

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            dir=drop_zone,
            delete=False,
            prefix="ingest_",
            encoding="utf-8",
        ) as f:
            f.write(frontmatter)
            f.write(body.text)
            fname = f.name
    except OSError as exc:
        log.error("ingest_text_write_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to write to drop zone") from exc

    log.info("ingest_text_queued", doc_id=doc_id, file=fname, text_len=len(body.text))
    return IngestTextResponse(queued=True, doc_id=doc_id, file=Path(fname).name)
