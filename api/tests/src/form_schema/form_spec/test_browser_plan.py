import json
import subprocess
import sys

import pytest

from src.form_schema.form_spec.browser_plan import (
    PLAN_CONTRACT,
    _resolve_schema_pointer,
    build_browser_plan,
)
from src.form_schema.form_spec.preview import banked_form_ids, preview_form_id


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
    )

    assert result.returncode == 0
    assert result.stdout.startswith("browser_plan:\n  contract:")
    assert result.stderr == ""
    assert json.loads(output.read_text())["contract"] == PLAN_CONTRACT


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


def test_schema_pointer_resolution_fails_closed() -> None:
    schema = {"properties": {"name": {"type": "string"}}}

    assert _resolve_schema_pointer(schema, "/properties/name") == {"type": "string"}
    with pytest.raises(ValueError, match="does not resolve"):
        _resolve_schema_pointer(schema, "/properties/missing")
