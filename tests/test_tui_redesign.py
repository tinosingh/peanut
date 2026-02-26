"""Tests for Apple UX redesigned TUI screens."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SRC_TUI = ROOT / "src" / "tui"


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def _class_names(module: ast.Module) -> set[str]:
    return {node.name for node in ast.walk(module) if isinstance(node, ast.ClassDef)}


def _method_names(module: ast.Module, class_name: str) -> set[str]:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                n.name
                for n in node.body
                if isinstance(n, ast.FunctionDef) or isinstance(n, ast.AsyncFunctionDef)
            }
    return set()


# ════════════════════════════════════════════════════════════════════════════════
# APP.PY TESTS
# ════════════════════════════════════════════════════════════════════════════════


def test_app_has_metric_card_widget():
    """MetricCard should be a Static subclass for rendering big numbers."""
    module = _parse(SRC_TUI / "app.py")
    assert "MetricCard" in _class_names(module)
    content = (SRC_TUI / "app.py").read_text()
    assert "Static" in content
    assert "def render" in content


def test_app_metric_card_has_update_method():
    """MetricCard should have update_metric() to change value and color."""
    module = _parse(SRC_TUI / "app.py")
    methods = _method_names(module, "MetricCard")
    assert "update_metric" in methods


def test_pkgapp_has_tabbed_content():
    """App should use TabbedContent for tab-based navigation."""
    content = (SRC_TUI / "app.py").read_text()
    assert "TabbedContent" in content
    assert "TabPane" in content


def test_pkgapp_has_all_six_tabs():
    """Should have Dashboard, Intake, Search, Entities, Settings, Graph tabs."""
    content = (SRC_TUI / "app.py").read_text()
    tabs = ["Dashboard", "Intake", "Search", "Entities", "Settings", "Graph"]
    for tab in tabs:
        assert tab in content, f"Missing {tab} tab"


def test_pkgapp_has_number_key_bindings():
    """Numbers 1–6 should switch between tabs."""
    content = (SRC_TUI / "app.py").read_text()
    for i in range(1, 7):
        assert f'"{i}"' in content or f"'{i}'" in content


def test_app_has_tab_activation_action():
    """Should have action_activate_tab(tab_id) method."""
    module = _parse(SRC_TUI / "app.py")
    methods = _method_names(module, "PKGApp")
    assert "action_activate_tab" in methods


def test_app_tab_activation_event_handler():
    """Should have on_tabbed_content_tab_activated() to notify active view."""
    module = _parse(SRC_TUI / "app.py")
    methods = _method_names(module, "PKGApp")
    assert "on_tabbed_content_tab_activated" in methods


# ════════════════════════════════════════════════════════════════════════════════
# WELCOME SCREEN TESTS
# ════════════════════════════════════════════════════════════════════════════════


def test_welcome_screen_exists():
    assert (SRC_TUI / "screens" / "welcome.py").exists()


def test_welcome_screen_is_screen_class():
    module = _parse(SRC_TUI / "screens" / "welcome.py")
    assert "WelcomeScreen" in _class_names(module)
    content = (SRC_TUI / "screens" / "welcome.py").read_text()
    assert "Screen" in content


def test_welcome_screen_has_poll_method():
    """Should poll for documents every 5 seconds."""
    module = _parse(SRC_TUI / "screens" / "welcome.py")
    methods = _method_names(module, "WelcomeScreen")
    assert "_poll" in methods or "on_mount" in methods
    content = (SRC_TUI / "screens" / "welcome.py").read_text()
    assert "set_interval" in content


# ════════════════════════════════════════════════════════════════════════════════
# DASHBOARD SCREEN TESTS
# ════════════════════════════════════════════════════════════════════════════════


def test_dashboard_view_exists():
    assert (SRC_TUI / "screens" / "dashboard.py").exists()


def test_dashboard_view_is_widget_class():
    module = _parse(SRC_TUI / "screens" / "dashboard.py")
    assert "DashboardView" in _class_names(module)
    content = (SRC_TUI / "screens" / "dashboard.py").read_text()
    assert "Widget" in content


def test_dashboard_view_has_metric_cards():
    """Should import MetricCard from app.py."""
    content = (SRC_TUI / "screens" / "dashboard.py").read_text()
    assert "MetricCard" in content
    assert "from src.tui.app import" in content


def test_dashboard_view_has_load_method():
    """Should have async _load() to fetch chunk counts."""
    module = _parse(SRC_TUI / "screens" / "dashboard.py")
    methods = _method_names(module, "DashboardView")
    assert "_load" in methods


def test_dashboard_view_has_refresh_action():
    """Should have action_refresh() bound to 'r' key."""
    content = (SRC_TUI / "screens" / "dashboard.py").read_text()
    assert "action_refresh" in content
    assert '"r"' in content or "'r'" in content


def test_dashboard_has_on_activated_hook():
    """Should have on_activated() to reload data when tab selected."""
    module = _parse(SRC_TUI / "screens" / "dashboard.py")
    methods = _method_names(module, "DashboardView")
    assert "on_activated" in methods


# ════════════════════════════════════════════════════════════════════════════════
# INTAKE SCREEN TESTS
# ════════════════════════════════════════════════════════════════════════════════


def test_intake_view_exists():
    assert (SRC_TUI / "screens" / "intake.py").exists()


def test_intake_view_is_widget_class():
    module = _parse(SRC_TUI / "screens" / "intake.py")
    assert "IntakeView" in _class_names(module)


def test_intake_view_has_data_table():
    """Should use DataTable to display file ingest progress."""
    content = (SRC_TUI / "screens" / "intake.py").read_text()
    assert "DataTable" in content


def test_intake_view_monitors_file_progress():
    """Should query documents + chunks with status grouping."""
    content = (SRC_TUI / "screens" / "intake.py").read_text()
    assert "documents" in content.lower()
    assert "chunks" in content.lower()
    assert "embedding_status" in content


def test_intake_has_pause_action():
    """Should have action_pause() to create/remove .pause sentinel."""
    module = _parse(SRC_TUI / "screens" / "intake.py")
    methods = _method_names(module, "IntakeView")
    assert "action_pause" in methods
    content = (SRC_TUI / "screens" / "intake.py").read_text()
    assert '".pause"' in content or "'.pause'" in content


def test_intake_has_retry_action():
    """Should have action_retry() to reset failed chunks."""
    module = _parse(SRC_TUI / "screens" / "intake.py")
    methods = _method_names(module, "IntakeView")
    assert "action_retry" in methods


# ════════════════════════════════════════════════════════════════════════════════
# SEARCH SCREEN TESTS
# ════════════════════════════════════════════════════════════════════════════════


def test_search_view_exists():
    assert (SRC_TUI / "screens" / "search.py").exists()


def test_search_view_is_widget_class():
    module = _parse(SRC_TUI / "screens" / "search.py")
    assert "SearchView" in _class_names(module)


def test_search_view_has_input_field():
    """Should have Input widget for search query."""
    content = (SRC_TUI / "screens" / "search.py").read_text()
    assert "Input" in content


def test_search_view_calls_post_search_api():
    """Should call POST /search endpoint."""
    content = (SRC_TUI / "screens" / "search.py").read_text()
    assert "/search" in content
    assert "httpx" in content or "AsyncClient" in content


def test_search_view_displays_scores():
    """Should display BM25, vector, and rerank scores."""
    content = (SRC_TUI / "screens" / "search.py").read_text()
    assert "bm25" in content.lower()
    assert "vector" in content.lower()
    assert "rerank" in content.lower()


# ════════════════════════════════════════════════════════════════════════════════
# ENTITIES SCREEN TESTS
# ════════════════════════════════════════════════════════════════════════════════


def test_entities_view_exists():
    assert (SRC_TUI / "screens" / "entities.py").exists()


def test_entities_view_is_widget_class():
    module = _parse(SRC_TUI / "screens" / "entities.py")
    assert "EntitiesView" in _class_names(module)


def test_entities_view_has_merge_action():
    """Should have action_merge() with two-stage confirmation."""
    module = _parse(SRC_TUI / "screens" / "entities.py")
    methods = _method_names(module, "EntitiesView")
    assert "action_merge" in methods


def test_entities_view_tracks_armed_state():
    """Should track _merge_armed and _armed_row for two-stage confirmation."""
    content = (SRC_TUI / "screens" / "entities.py").read_text()
    assert "_merge_armed" in content
    assert "_armed_row" in content


def test_entities_calls_merge_endpoint():
    """Should POST to /entities/merge endpoint."""
    content = (SRC_TUI / "screens" / "entities.py").read_text()
    assert "/entities/merge" in content


def test_entities_displays_jaro_winkler_scores():
    """Should show Jaro-Winkler similarity scores."""
    content = (SRC_TUI / "screens" / "entities.py").read_text()
    assert "jw" in content.lower() or "jaro" in content.lower()


# ════════════════════════════════════════════════════════════════════════════════
# SETTINGS SCREEN TESTS
# ════════════════════════════════════════════════════════════════════════════════


def test_settings_view_exists():
    assert (SRC_TUI / "screens" / "settings.py").exists()


def test_settings_view_is_widget_class():
    module = _parse(SRC_TUI / "screens" / "settings.py")
    assert "SettingsView" in _class_names(module)


def test_settings_view_has_weight_inputs():
    """Should have Input fields for BM25 and vector weights."""
    content = (SRC_TUI / "screens" / "settings.py").read_text()
    assert "bm25" in content.lower()
    assert "vector" in content.lower()
    assert "Input" in content


def test_settings_view_has_save_weights_action():
    """Should have action_save_weights() to POST /config."""
    module = _parse(SRC_TUI / "screens" / "settings.py")
    methods = _method_names(module, "SettingsView")
    assert "action_save_weights" in methods


def test_settings_view_displays_pii_report():
    """Should fetch and display PII report."""
    content = (SRC_TUI / "screens" / "settings.py").read_text()
    assert "/pii/report" in content


def test_settings_view_has_bulk_redact_action():
    """Should have action_bulk_redact() to POST /pii/bulk-redact."""
    module = _parse(SRC_TUI / "screens" / "settings.py")
    methods = _method_names(module, "SettingsView")
    assert "action_bulk_redact" in methods


# ════════════════════════════════════════════════════════════════════════════════
# GRAPH SCREEN TESTS
# ════════════════════════════════════════════════════════════════════════════════


def test_graph_view_exists():
    assert (SRC_TUI / "screens" / "graph.py").exists()


def test_graph_view_is_widget_class():
    module = _parse(SRC_TUI / "screens" / "graph.py")
    assert "GraphView" in _class_names(module)


def test_graph_view_uses_tree_widget():
    """Should use Tree widget for hierarchical graph display."""
    content = (SRC_TUI / "screens" / "graph.py").read_text()
    assert "Tree" in content


def test_graph_view_imports_falkordb():
    """Should import falkordb SDK for Cypher queries."""
    content = (SRC_TUI / "screens" / "graph.py").read_text()
    assert "falkordb" in content


def test_graph_view_has_drill_in_action():
    """Should have action_drill_in() to set new root and push to history."""
    module = _parse(SRC_TUI / "screens" / "graph.py")
    methods = _method_names(module, "GraphView")
    assert "action_drill_in" in methods


def test_graph_view_has_go_back_action():
    """Should have action_go_back() to pop from history stack."""
    module = _parse(SRC_TUI / "screens" / "graph.py")
    methods = _method_names(module, "GraphView")
    assert "action_go_back" in methods


def test_graph_view_maintains_history_stack():
    """Should track _history stack for breadcrumb navigation."""
    content = (SRC_TUI / "screens" / "graph.py").read_text()
    assert "_history" in content


def test_graph_view_colors_nodes_by_type():
    """Should color nodes based on type (Person cyan, Document green, etc.)."""
    content = (SRC_TUI / "screens" / "graph.py").read_text()
    assert "_COLOR" in content or "color" in content.lower()


# ════════════════════════════════════════════════════════════════════════════════
# HELP SCREEN TESTS
# ════════════════════════════════════════════════════════════════════════════════


def test_help_overlay_exists():
    assert (SRC_TUI / "screens" / "help.py").exists()


def test_help_overlay_is_modal_screen():
    """Help should be a ModalScreen that can be dismissed."""
    module = _parse(SRC_TUI / "screens" / "help.py")
    assert "HelpOverlay" in _class_names(module)
    content = (SRC_TUI / "screens" / "help.py").read_text()
    assert "ModalScreen" in content


def test_help_overlay_dismissable():
    """Should be dismissable by Escape or ctrl+h."""
    content = (SRC_TUI / "screens" / "help.py").read_text()
    assert "escape" in content.lower()
    assert "dismiss" in content


# ════════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ════════════════════════════════════════════════════════════════════════════════


def test_all_screens_are_widgets_or_screens():
    """All screen modules should export Widget or Screen subclass."""
    for screen_file in (SRC_TUI / "screens").glob("*.py"):
        if screen_file.name in ["__init__.py", "graph_export.py"]:
            continue
        file_content = screen_file.read_text()
        assert "Widget" in file_content or "Screen" in file_content, f"{screen_file.name} missing Widget/Screen"


def test_all_screens_have_compose_method():
    """All View classes should have compose() for building widgets."""
    for screen_file in (SRC_TUI / "screens").glob("*.py"):
        if screen_file.name in ["__init__.py", "graph_export.py"]:
            continue
        module = _parse(screen_file)
        for class_name in _class_names(module):
            if "View" in class_name or "Screen" in class_name:
                methods = _method_names(module, class_name)
                assert "compose" in methods, f"{class_name} missing compose()"


def test_color_scheme_consistency():
    """All screens should use the same color palette from theme."""
    colors = ["#1c1c1e", "#2c2c2e", "#f2f2f7", "#636366", "#30d158", "#ff9f0a", "#ff453a", "#0a84ff"]
    app_content = (SRC_TUI / "app.py").read_text()
    for color in colors:
        assert color in app_content, f"Missing color {color} in theme"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
