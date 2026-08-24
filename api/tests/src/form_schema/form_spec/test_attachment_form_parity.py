"""Portable attachment packages preserve their existing Simpler behavior."""

import copy
from pathlib import Path

import pytest

import src.form_schema.forms as forms_package
from src.form_schema.form_spec.loader import _load_banked_form, load_form
from src.form_schema.forms._loader import load_versioned_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from tests.src.form_schema.form_spec import parity
from tests.src.form_schema.form_spec.attachment_form_vectors import DIFFERENTIAL_RESPONSES

FORMS = [
    ("project_narrative_attachment", "project-narrative-attachments"),
    ("budget_narrative_attachment", "budget-narrative-attachments"),
    ("other_narrative_attachment", "other-narrative-attachments"),
]

VALID_ID = "00000000-0000-4000-8000-000000000000"


def _without_descriptions(value):
    if isinstance(value, dict):
        return {
            key: _without_descriptions(child)
            for key, child in value.items()
            if key != "description"
        }
    if isinstance(value, list):
        return [_without_descriptions(child) for child in value]
    return value


def test_ordered_attachment_form_matches_the_legacy_oracle() -> None:
    """Compare the banked package without granting it a production identity."""

    golden = load_versioned_form(Path(forms_package.__file__).parent / "attachment_form", "1.0")
    projected = _load_banked_form("attachment-form", project_xml=False)
    resolved_golden = resolve_jsonschema(copy.deepcopy(golden.FORM_JSON_SCHEMA))
    resolved_projected = resolve_jsonschema(copy.deepcopy(projected.form_json_schema))

    # The only raw-schema differences are portable documentation attached to the
    # reusable slot mechanism and form package. They do not change the rendered or
    # validation contracts proven below; keep the classification mechanically bounded.
    assert projected.form_json_schema["description"] == (
        "Attachment Form, Grants.gov FID 540, version 1.2."
    )
    assert _without_descriptions(resolved_projected) == _without_descriptions(resolved_golden)

    assert projected.form_ui_schema == golden.FORM_UI_SCHEMA
    assert projected.form_rule_schema == golden.FORM_RULE_SCHEMA
    assert (
        parity.rendered_differences(resolved_projected, resolved_golden, golden.FORM_UI_SCHEMA)
        == []
    )
    assert (
        parity.behavioral_differences(
            resolved_projected,
            resolved_golden,
            list(DIFFERENTIAL_RESPONSES),
        )
        == []
    )


@pytest.mark.parametrize("directory,form_id", FORMS)
def test_attachment_form_matches_existing_simpler_behavior(directory: str, form_id: str) -> None:
    golden = load_versioned_form(Path(forms_package.__file__).parent / directory, "1.0")
    projected = load_form(form_id)
    resolved_golden = resolve_jsonschema(copy.deepcopy(golden.FORM_JSON_SCHEMA))
    resolved_projected = resolve_jsonschema(copy.deepcopy(projected.form_json_schema))

    assert projected.form_ui_schema == golden.FORM_UI_SCHEMA
    assert projected.form_rule_schema == golden.FORM_RULE_SCHEMA
    assert (
        parity.rendered_differences(resolved_projected, resolved_golden, golden.FORM_UI_SCHEMA)
        == []
    )

    payloads = [
        {},
        {"attachments": []},
        {"attachments": [VALID_ID]},
        {"attachments": ["not-a-file-id"]},
        {"attachments": [VALID_ID] * 101},
    ]
    assert parity.behavioral_differences(resolved_projected, resolved_golden, payloads) == []
