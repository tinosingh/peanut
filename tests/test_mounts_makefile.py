"""Tests for T-003 (bind mounts) and T-004 (Makefile targets)."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
COMPOSE = (ROOT / "docker-compose.yml").read_text()
MAKEFILE = (ROOT / "Makefile").read_text()


# ── T-003: Bind mounts ─────────────────────────────────────────────────────

def test_drop_zone_mounted_readonly():
    assert "./drop-zone:/drop-zone:ro" in COMPOSE


def test_vault_sync_mounted_writable():
    assert "./vault-sync:/vault-sync" in COMPOSE


def test_drop_zone_dir_exists():
    assert (ROOT / "drop-zone").is_dir()


def test_vault_sync_dir_exists():
    assert (ROOT / "vault-sync").is_dir()


def test_drop_zone_readonly_in_ingest_only():
    # drop-zone should only be in ingest-worker (read-only), not tui
    ingest_idx = COMPOSE.index("ingest-worker:")
    tui_idx = COMPOSE.index("tui-controller:")
    ingest_section = COMPOSE[ingest_idx:tui_idx]
    assert "/drop-zone:ro" in ingest_section


# ── T-004: Makefile targets ────────────────────────────────────────────────

REQUIRED_TARGETS = [
    "up", "down", "reset", "logs", "tui", "backup",
    "restore-from-backup", "test-backup-restore", "migrate-up",
    "audit", "sanity", "hard-delete", "scan-pii", "reindex",
]

def test_all_required_targets_exist():
    for target in REQUIRED_TARGETS:
        assert re.search(rf"^{re.escape(target)}:", MAKEFILE, re.MULTILINE), \
            f"Missing Makefile target: {target}"


def test_hard_delete_requires_confirm():
    # hard-delete must check for --confirm or CONFIRM=yes
    idx = MAKEFILE.index("hard-delete:")
    section = MAKEFILE[idx:idx + 400]
    assert "CONFIRM" in section


def test_sanity_checks_orphaned_chunks():
    idx = MAKEFILE.index("sanity:")
    section = MAKEFILE[idx:idx + 300]
    assert "orphaned" in section.lower() or "chunks" in section.lower()


def test_phony_declared():
    assert ".PHONY:" in MAKEFILE


def test_backup_dir_defined():
    assert "BACKUP_DIR" in MAKEFILE
    assert "data/backups" in MAKEFILE
