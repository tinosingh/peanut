"""Tests for T-005: TUI skeleton structural verification (no display required)."""
import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent
SRC_TUI = ROOT / "src" / "tui"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def _names(module: ast.Module) -> set[str]:
    return {node.name for node in ast.walk(module) if isinstance(node, ast.ClassDef)}


def test_app_module_exists():
    assert (SRC_TUI / "app.py").exists()


def test_pkgapp_class_defined():
    module = _parse(SRC_TUI / "app.py")
    assert "PKGApp" in _names(module)


def test_pkgapp_has_help_binding():
    content = (SRC_TUI / "app.py").read_text()
    assert '"?"' in content or "'?'" in content
    assert "toggle_help" in content


def test_pkgapp_has_quit_binding():
    content = (SRC_TUI / "app.py").read_text()
    assert '"q"' in content or "'q'" in content


def test_help_overlay_is_modal_screen():
    content = (SRC_TUI / "screens" / "help.py").read_text()
    assert "ModalScreen" in content
    assert "HelpOverlay" in content


def test_help_overlay_dismissable_by_escape():
    content = (SRC_TUI / "screens" / "help.py").read_text()
    assert "escape" in content.lower()
    assert "dismiss" in content


def test_welcome_screen_exists():
    assert (SRC_TUI / "screens" / "welcome.py").exists()


def test_welcome_screen_polls_for_documents():
    content = (SRC_TUI / "screens" / "welcome.py").read_text()
    assert "documents" in content
    assert "set_interval" in content or "interval" in content


def test_welcome_screen_has_drop_zone_text():
    content = (SRC_TUI / "screens" / "welcome.py").read_text()
    assert "drop-zone" in content or "drop_zone" in content


def test_dashboard_screen_exists():
    assert (SRC_TUI / "screens" / "dashboard.py").exists()


def test_screens_have_footer():
    for screen in ["welcome.py", "dashboard.py"]:
        content = (SRC_TUI / "screens" / screen).read_text()
        assert "Footer" in content, f"{screen} missing Footer widget"


def test_shared_db_pool_module():
    db_path = ROOT / "src" / "shared" / "db.py"
    assert db_path.exists()
    content = db_path.read_text()
    assert "get_pool" in content
    assert "AsyncConnectionPool" in content
    assert "register_vector" in content
