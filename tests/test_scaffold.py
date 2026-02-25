"""Smoke tests: verify project scaffold integrity for T-000."""
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_docker_compose_exists():
    assert (ROOT / "docker-compose.yml").exists()


def test_docker_compose_no_ollama_service():
    content = (ROOT / "docker-compose.yml").read_text()
    assert "ollama" not in content.lower().split("services:")[1].split("volumes:")[0], \
        "Ollama must NOT be a Docker service — it runs on the host"


def test_dockerfiles_exist():
    assert (ROOT / "Dockerfile.ingest").exists()
    assert (ROOT / "Dockerfile.tui").exists()


def test_env_example_has_ollama_url():
    content = (ROOT / ".env.example").read_text()
    assert "OLLAMA_URL" in content
    assert "host.docker.internal" in content


def test_src_layout():
    for pkg in ["src/ingest", "src/tui", "src/api", "src/shared"]:
        assert (ROOT / pkg / "__init__.py").exists(), f"Missing {pkg}/__init__.py"


def test_pyproject_has_extras():
    content = (ROOT / "pyproject.toml").read_text()
    for extra in ["ingest", "tui", "test"]:
        assert f'[project.optional-dependencies]\n' in content or extra in content


def test_test_compose_exists():
    assert (ROOT / "docker-compose.test.yml").exists()


def test_host_gateway_in_compose():
    """Linux compat: host.docker.internal must resolve inside containers."""
    content = (ROOT / "docker-compose.yml").read_text()
    assert "host-gateway" in content
