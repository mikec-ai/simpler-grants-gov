from __future__ import annotations

import subprocess
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "bin" / "run-isolated-api-test"
RUNNER_MODULE = REPO_ROOT / "api" / "bin" / "run_isolated_api_test.py"
loader = SourceFileLoader("run_isolated_api_test", str(RUNNER_MODULE))
spec = spec_from_loader(loader.name, loader)
assert spec is not None
runner = module_from_spec(spec)
loader.exec_module(runner)


def test_stack_environment_is_stable_and_disjoint() -> None:
    first = runner.stack_environment("first-worktree")
    first_again = runner.stack_environment("first-worktree")
    second = runner.stack_environment("second-worktree")

    assert first == first_again
    for key in (
        "API_COMPOSE_PROJECT",
        "DB_COMPOSE_PROJECT",
        "LOCAL_DB_NETWORK_NAME",
        "API_BACKEND_NETWORK_NAME",
        "API_HOST_PORT",
        "DB_HOST_PORT",
    ):
        assert first[key] != second[key]


def test_plan_emits_compact_toon() -> None:
    result = subprocess.run(
        [RUNNER, "plan", "--stack-id", "agent-one"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stderr == ""
    assert 'id: "agent-one"' in result.stdout
    assert "status: planned" in result.stdout
    assert 'api_project: "sgg-agent-one-api"' in result.stdout


def test_unknown_flag_fails_with_structured_usage_error() -> None:
    result = subprocess.run(
        [RUNNER, "plan", "--unknown"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stderr == ""
    assert "error:" in result.stdout
    assert "help:" in result.stdout


def test_compose_files_have_no_global_container_names() -> None:
    compose_files = (
        REPO_ROOT / "api" / "docker-compose.yml",
        REPO_ROOT / "backend" / "docker-compose.db.yml",
        REPO_ROOT / "frontend" / "docker-compose.yml",
    )

    for compose_file in compose_files:
        assert "container_name:" not in compose_file.read_text()


def test_compose_files_keep_backwards_compatible_port_defaults() -> None:
    api_compose = (REPO_ROOT / "api" / "docker-compose.yml").read_text()
    db_compose = (REPO_ROOT / "backend" / "docker-compose.db.yml").read_text()

    assert "${API_HOST_PORT:-8080}:8080" in api_compose
    assert "${OPENSEARCH_HOST_PORT:-9200}:9200" in api_compose
    assert "${DB_HOST_PORT:-5432}:5432" in db_compose
    assert "${LOCAL_DB_NETWORK_NAME:-local_db}" in api_compose
    assert "${LOCAL_DB_NETWORK_NAME:-local_db}" in db_compose


def test_s3mock_uses_a_compose_scoped_volume() -> None:
    api_compose = (REPO_ROOT / "api" / "docker-compose.yml").read_text()

    assert "s3mock-data:/containers3root" in api_compose
    assert "s3mock-data:/api/locals3root" in api_compose
    assert "./locals3root:/containers3root" not in api_compose
