"""A source-neutral workbench package crosses the real Simpler package loader boundary."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.form_schema.form_spec.loader import _load_banked_form

EXPORTED_ARTIFACTS = Path(__file__).parents[3] / "fixtures" / "workbench-sgg-export"
FORM_ROOT = EXPORTED_ARTIFACTS / "forms" / "attachment-form"


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def test_workbench_export_loads_as_the_existing_sgg_attachment_form() -> None:
    exported = _load_banked_form(
        "attachment-form",
        artifacts=EXPORTED_ARTIFACTS,
        project_xml=False,
    )
    canonical = _load_banked_form("attachment-form", project_xml=False)

    assert exported.form_json_schema == canonical.form_json_schema
    assert exported.form_ui_schema == canonical.form_ui_schema
    assert exported.form_rule_schema == canonical.form_rule_schema


def test_workbench_export_receipt_binds_every_loaded_artifact() -> None:
    receipt = json.loads((FORM_ROOT / "sgg" / "authoring-receipt.json").read_text())
    manifest = json.loads((FORM_ROOT / "manifest.json").read_text())
    schema = json.loads((FORM_ROOT / "schema.json").read_text())
    ui_schema = json.loads((FORM_ROOT / "sgg" / "ui-schema.json").read_text())
    rule_schema = json.loads((FORM_ROOT / "sgg" / "rule-schema.json").read_text())

    assert receipt["contract"] == "portable-form-sgg-adapter-receipt/v1"
    assert receipt["input"]["contract"] == "resolved-form-package/v1"
    assert receipt["input"]["formId"] == manifest["form"]["id"] == "attachment-form"
    assert receipt["output"] == {
        "schemaSha256": _canonical_sha256(schema),
        "uiSchemaSha256": _canonical_sha256(ui_schema),
        "ruleSchemaSha256": _canonical_sha256(rule_schema),
    }
    assert receipt["semanticReview"] == {
        "accepted": 0,
        "proposed": 0,
        "rejected": 0,
        "unreviewed": 15,
    }
    assert manifest["artifacts"]["sgg/authoring-receipt.json"] == "passthrough"
