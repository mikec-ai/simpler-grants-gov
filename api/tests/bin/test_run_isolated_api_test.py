from __future__ import annotations

import json
import shutil
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[2]
CHECKOUT_ROOT = API_ROOT.parent
RUNNER_WRAPPER = CHECKOUT_ROOT / "bin" / "run-isolated-api-test"
RUNNER_MODULE = API_ROOT / "bin" / "run_isolated_api_test.py"
RUNNER_COMMAND = (
    [str(RUNNER_WRAPPER)] if RUNNER_WRAPPER.is_file() else [sys.executable, str(RUNNER_MODULE)]
)
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
        [*RUNNER_COMMAND, "plan", "--stack-id", "agent-one"],
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
        [*RUNNER_COMMAND, "plan", "--unknown"],
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
        API_ROOT / "docker-compose.yml",
        CHECKOUT_ROOT / "backend" / "docker-compose.db.yml",
        CHECKOUT_ROOT / "frontend" / "docker-compose.yml",
    )

    for compose_file in compose_files:
        if not compose_file.is_file():
            continue
        assert "container_name:" not in compose_file.read_text()


def test_compose_files_keep_backwards_compatible_port_defaults() -> None:
    api_compose = (API_ROOT / "docker-compose.yml").read_text()
    db_compose_path = CHECKOUT_ROOT / "backend" / "docker-compose.db.yml"

    assert "${API_HOST_PORT:-8080}:8080" in api_compose
    assert "${OPENSEARCH_HOST_PORT:-9200}:9200" in api_compose
    assert "${LOCAL_DB_NETWORK_NAME:-local_db}" in api_compose
    if db_compose_path.is_file():
        db_compose = db_compose_path.read_text()
        assert "${DB_HOST_PORT:-5432}:5432" in db_compose
        assert "${LOCAL_DB_NETWORK_NAME:-local_db}" in db_compose


def test_s3mock_uses_a_compose_scoped_volume() -> None:
    api_compose = (API_ROOT / "docker-compose.yml").read_text()

    assert "COM_ADOBE_TESTING_S3MOCK_STORE_ROOT=/containers3root" in api_compose
    assert "s3mock-data:/containers3root" in api_compose
    assert "s3mock-data:/api/locals3root" in api_compose
    assert "./locals3root:/containers3root" not in api_compose

    if shutil.which("docker") is None:
        pytest.skip("Docker Compose is required to inspect the effective configuration")

    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "docker-compose.ci.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=API_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    config = json.loads(result.stdout)
    s3mock = config["services"]["s3mock"]
    grants_api = config["services"]["grants-api"]

    store_root = s3mock["environment"]["COM_ADOBE_TESTING_S3MOCK_STORE_ROOT"]
    s3mock_volume = next(volume for volume in s3mock["volumes"] if volume["target"] == store_root)
    api_volume = next(
        volume for volume in grants_api["volumes"] if volume["target"] == "/api/locals3root"
    )

    assert store_root == "/containers3root"
    assert s3mock_volume["type"] == "volume"
    assert api_volume["type"] == "volume"
    assert s3mock_volume["source"] == api_volume["source"] == "s3mock-data"


def test_hosted_browser_stack_starts_single_process_file_scanner() -> None:
    ci_compose = (API_ROOT / "docker-compose.ci.yml").read_text()
    e2e_workflow_path = CHECKOUT_ROOT / ".github" / "workflows" / "ci-frontend-e2e.yml"

    assert 'LOCAL_FILE_SCANNER_RUN_WITHOUT_RELOADER: "TRUE"' in ci_compose
    if e2e_workflow_path.is_file():
        assert "LOCAL_FILE_SCANNER_RUN_WITHOUT_RELOADER=TRUE" not in e2e_workflow_path.read_text()
