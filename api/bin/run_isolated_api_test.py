#!/usr/bin/env python3
"""Run repository-native API tests in a worktree-scoped Compose stack."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Never

VERSION = "0.1.0"
REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "api"
STACK_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def stdout(line: str) -> None:
    sys.stdout.write(f"{line}\n")


def stderr(line: str) -> None:
    sys.stderr.write(f"{line}\n")


class ToonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        stdout(f"error: {json.dumps(message)}")
        stdout(f"help: {json.dumps(f'{self.prog} --help')}")
        raise SystemExit(2)


def default_stack_id() -> str:
    basename = re.sub(r"[^a-z0-9]+", "-", REPO_ROOT.name.lower()).strip("-") or "worktree"
    digest = hashlib.sha256(str(REPO_ROOT).encode()).hexdigest()[:8]
    return f"{basename[:28]}-{digest}"


def stack_environment(stack_id: str) -> dict[str, str]:
    if not STACK_PATTERN.fullmatch(stack_id):
        raise ValueError("stack id must match [a-z0-9][a-z0-9-]*")

    offset = 10_000 + (int(hashlib.sha256(stack_id.encode()).hexdigest()[:8], 16) % 10_000)
    prefix = f"sgg-{stack_id}"
    port_bases = {
        "API_HOST_PORT": 8080,
        "DB_HOST_PORT": 5432,
        "DEBUG_HOST_PORT": 5678,
        "DYNAMODB_HOST_PORT": 8000,
        "FRONTEND_HOST_PORT": 3000,
        "MAILPIT_SMTP_HOST_PORT": 1025,
        "MAILPIT_UI_HOST_PORT": 8025,
        "OAUTH_HOST_PORT": 5001,
        "OPENSEARCH_ANALYZER_HOST_PORT": 9600,
        "OPENSEARCH_DASHBOARDS_HOST_PORT": 5601,
        "OPENSEARCH_HOST_PORT": 9200,
        "S3MOCK_HOST_PORT": 9090,
        "SOAP_MOCK_HOST_PORT": 8082,
        "SQSMOCK_HOST_PORT": 9324,
        "STORYBOOK_HOST_PORT": 6006,
    }
    values = {name: str(base + offset) for name, base in port_bases.items()}
    values.update(
        {
            "API_BACKEND_NETWORK_NAME": f"{prefix}-api-backend",
            "API_COMPOSE_PROJECT": f"{prefix}-api",
            "DB_COMPOSE_PROJECT": f"{prefix}-db",
            "FRONTEND_COMPOSE_PROJECT": f"{prefix}-frontend",
            "LOCAL_DB_NETWORK_NAME": f"{prefix}-local-db",
            "WAIT_FOR_API_URL": f"http://127.0.0.1:{values['API_HOST_PORT']}/health",
        }
    )
    return values


def emit_plan(stack_id: str, values: dict[str, str], *, status: str = "planned") -> None:
    stdout("stack:")
    stdout(f"  id: {json.dumps(stack_id)}")
    stdout(f"  status: {status}")
    stdout(f"  api_project: {json.dumps(values['API_COMPOSE_PROJECT'])}")
    stdout(f"  db_project: {json.dumps(values['DB_COMPOSE_PROJECT'])}")
    stdout(f"  api_port: {values['API_HOST_PORT']}")
    stdout(f"  db_port: {values['DB_HOST_PORT']}")
    stdout(f"  local_db_network: {json.dumps(values['LOCAL_DB_NETWORK_NAME'])}")
    stdout(f"  api_backend_network: {json.dumps(values['API_BACKEND_NETWORK_NAME'])}")


def run_make(target: str, values: dict[str, str], *, test_args: list[str] | None = None) -> None:
    env = os.environ.copy()
    env.update(values)
    command = ["make", target]
    if test_args is not None:
        command.append(f"args={' '.join(test_args)}")
    stderr(f"running: {' '.join(command)}")
    subprocess.run(command, cwd=API_DIR, env=env, check=True, stdout=sys.stderr)


def build_parser() -> ToonArgumentParser:
    parser = ToonArgumentParser(
        prog="bin/run-isolated-api-test",
        description="Run API tests in a worktree-scoped Docker Compose stack.",
    )
    subparsers = parser.add_subparsers(dest="command")

    for name in ("plan", "down"):
        child = subparsers.add_parser(name)
        child.add_argument("--stack-id", default=default_stack_id())

    test = subparsers.add_parser("test")
    test.add_argument("--stack-id", default=default_stack_id())
    test.add_argument("--keep", action="store_true")
    test.add_argument("pytest_args", nargs=argparse.REMAINDER)
    return parser


def home() -> None:
    executable = str(Path(__file__).resolve()).replace(str(Path.home()), "~", 1)
    stack_id = default_stack_id()
    stdout(f"bin: {json.dumps(executable)}")
    stdout("description: Run repository-native API tests in an isolated worktree stack")
    emit_plan(stack_id, stack_environment(stack_id))
    stdout("help[3]:")
    stdout('  "bin/run-isolated-api-test plan --stack-id <id>"')
    stdout('  "bin/run-isolated-api-test test --stack-id <id> -- <pytest-args>"')
    stdout('  "bin/run-isolated-api-test down --stack-id <id>"')


def main(argv: list[str]) -> int:
    if len(argv) == 1 and argv[0] in {"-v", "-V", "--version"}:
        stdout(VERSION)
        return 0
    if not argv:
        home()
        return 0

    args = build_parser().parse_args(argv)
    if args.command is None:
        build_parser().error("a command is required: plan, test, or down")

    try:
        values = stack_environment(args.stack_id)
    except ValueError as error:
        stdout(f"error: {json.dumps(str(error))}")
        stdout('help: "use --stack-id with lowercase letters, numbers, and hyphens"')
        return 2

    if args.command == "plan":
        emit_plan(args.stack_id, values)
        return 0
    if args.command == "down":
        run_make("stop", values)
        emit_plan(args.stack_id, values, status="stopped")
        return 0

    pytest_args = args.pytest_args
    if pytest_args[:1] == ["--"]:
        pytest_args = pytest_args[1:]

    interrupted = False

    def mark_interrupted(_signum: int, _frame: object) -> None:
        nonlocal interrupted
        interrupted = True
        raise KeyboardInterrupt

    old_handlers = {
        signum: signal.signal(signum, mark_interrupted)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        run_make("init", values)
        run_make("test", values, test_args=pytest_args)
        emit_plan(args.stack_id, values, status="passed")
        return 0
    except (subprocess.CalledProcessError, KeyboardInterrupt) as error:
        reason = (
            "interrupted"
            if interrupted
            else f"command failed with exit {getattr(error, 'returncode', 1)}"
        )
        stdout("error:")
        stdout(f"  stack_id: {json.dumps(args.stack_id)}")
        stdout(f"  reason: {json.dumps(reason)}")
        stdout(f"  cleanup: {'kept' if args.keep else 'attempted'}")
        return 130 if interrupted else 1
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        if not args.keep:
            try:
                run_make("stop", values)
            except subprocess.CalledProcessError:
                stderr("cleanup failed; run the scoped down command shown by --help")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
