import json
import os
import subprocess
import sys

import pytest

from src.form_schema.form_spec.browser_plan import (
    PLAN_CONTRACT,
    SEED_COMPETITION_ID,
    SEED_OPPORTUNITY_ID,
    _resolve_schema_pointer,
    browser_seed_ids,
    build_browser_plan,
)
from src.form_schema.form_spec.preview import BROWSER_FORM_IDS, banked_form_ids, preview_form_id


@pytest.fixture(autouse=True)
def _enable_portable_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ENABLE_PORTABLE_FORM_PREVIEW", "true")


def test_browser_plan_follows_live_manifest_and_discovers_capabilities() -> None:
    plan = build_browser_plan()

    assert plan["contract"] == PLAN_CONTRACT
    assert [form["portableFormId"] for form in plan["forms"]] == list(banked_form_ids())
    assert [form["previewFormId"] for form in plan["forms"]] == [
        str(preview_form_id(form_id)) for form_id in banked_form_ids()
    ]
    assert all(form["artifactDigests"] for form in plan["forms"])
    assert all(form["counts"]["uiNodes"] > 0 for form in plan["forms"])

    capability_names = {
        capability
        for form in plan["forms"]
        for capability, declaration in form["capabilities"].items()
        if declaration["applicability"] == "applicable"
    }
    assert capability_names == {
        "attachment",
        "calculation",
        "conditional",
        "editableScalar",
        "readOnly",
        "repeater",
        "requiredField",
    }


@pytest.mark.parametrize("form_id", ["sf424", "sf424-short"])
def test_browser_plan_can_target_a_family_member_without_a_second_harness(
    monkeypatch: pytest.MonkeyPatch, form_id: str
) -> None:
    monkeypatch.setenv(BROWSER_FORM_IDS, form_id)

    plan = build_browser_plan()

    assert [form["portableFormId"] for form in plan["forms"]] == [form_id]
    assert plan["forms"][0]["previewFormId"] == str(preview_form_id(form_id))
    assert plan["consumerSeed"] == {
        "opportunityId": browser_seed_ids((form_id,))[0],
        "competitionId": browser_seed_ids((form_id,))[1],
    }


def test_browser_seed_ids_preserve_full_catalog_and_isolate_canaries() -> None:
    assert browser_seed_ids(banked_form_ids()) == (SEED_OPPORTUNITY_ID, SEED_COMPETITION_ID)
    assert browser_seed_ids(("sf424",)) == browser_seed_ids(("sf424",))
    assert browser_seed_ids(("sf424",)) != browser_seed_ids(("sf424a",))


def test_browser_plan_cli_writes_json_and_structured_stdout(tmp_path) -> None:
    output = tmp_path / "plan.json"
    result = subprocess.run(
        [
            sys.executable,
            "bin/build_portable_browser_plan.py",
            "--out",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "ENVIRONMENT": "test",
            "ENABLE_PORTABLE_FORM_PREVIEW": "true",
        },
    )

    assert result.returncode == 0
    assert result.stdout.startswith("browser_plan:\n  contract:")
    assert result.stderr == ""
    assert json.loads(output.read_text())["contract"] == PLAN_CONTRACT


@pytest.mark.parametrize("form_id", ["sf424", "sf424-short"])
def test_browser_plan_cli_honors_one_form_selection(tmp_path, form_id: str) -> None:
    output = tmp_path / "plan.json"
    result = subprocess.run(
        [sys.executable, "bin/build_portable_browser_plan.py", "--out", str(output)],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "ENVIRONMENT": "test",
            "ENABLE_PORTABLE_FORM_PREVIEW": "true",
            BROWSER_FORM_IDS: form_id,
        },
    )

    assert result.returncode == 0
    assert "forms: 1" in result.stdout
    assert [form["portableFormId"] for form in json.loads(output.read_text())["forms"]] == [form_id]


def test_browser_plan_cli_rejects_unknown_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "bin/build_portable_browser_plan.py",
            "--out",
            "unused.json",
            "--unknown",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "unrecognized arguments: --unknown" in result.stderr


def test_browser_plan_cli_requires_preview_gate(tmp_path) -> None:
    environment = dict(os.environ)
    environment.pop("ENVIRONMENT", None)
    environment.pop("ENABLE_PORTABLE_FORM_PREVIEW", None)
    result = subprocess.run(
        [
            sys.executable,
            "bin/build_portable_browser_plan.py",
            "--out",
            str(tmp_path / "plan.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "ENVIRONMENT=local|test|dev" in result.stderr


def test_browser_plan_fails_closed_without_preview_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENABLE_PORTABLE_FORM_PREVIEW")

    with pytest.raises(ValueError, match="ENVIRONMENT=local\\|test\\|dev"):
        build_browser_plan()


def test_schema_pointer_resolution_fails_closed() -> None:
    schema = {"properties": {"name": {"type": "string"}}}

    assert _resolve_schema_pointer(schema, "/properties/name") == {"type": "string"}
    with pytest.raises(ValueError, match="does not resolve"):
        _resolve_schema_pointer(schema, "/properties/missing")
