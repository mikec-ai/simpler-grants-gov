"""Portable CD-511 conformance canary against the existing SGG oracle."""

from __future__ import annotations

import copy
import json

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import load_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from tests.src.form_schema.form_spec.lifecycle import (
    ValidationCase,
    assert_json_round_trip,
    assert_validation_case,
    submit_form,
)


VALID_RESPONSE = {
    "applicant_name": "Example Research Institute",
    "project_name": "Portable Grants Forms",
    "contact_person": {"first_name": "Ada", "last_name": "Lovelace"},
    "contact_person_title": "Authorized Representative",
}


def test_cd511_loads_without_a_form_specific_projection_profile() -> None:
    projected = load_form("cd511")

    assert projected.meta == {
        "id": "cd511",
        "legacyFormId": 276,
        "formName": "CD511",
        "shortFormName": "CD511",
        "formVersion": "1.1",
        "agencyCode": "SGG",
        "ombNumber": "",
    }
    assert len(projected.form_ui_schema) == 7
    assert [section["name"] for section in projected.form_ui_schema[:4]] == [
        "directions1", "directions2", "directions3", "directions4",
    ]


def test_cd511_executes_the_portable_award_or_project_constraint() -> None:
    assert_validation_case(
        "cd511",
        ValidationCase("project name", VALID_RESPONSE, frozenset()),
    )
    award = copy.deepcopy(VALID_RESPONSE)
    award.pop("project_name")
    award["award_number"] = "AWARD-123"
    assert_validation_case(
        "cd511",
        ValidationCase("award number", award, frozenset()),
    )
    missing = copy.deepcopy(VALID_RESPONSE)
    missing.pop("project_name")
    assert_validation_case(
        "cd511",
        ValidationCase("neither identifier", missing, frozenset({"$"})),
    )


def test_cd511_preserves_source_limits_and_aor_name_requiredness() -> None:
    schema = resolve_jsonschema(copy.deepcopy(load_form("cd511").form_json_schema))

    assert schema["properties"]["award_number"]["maxLength"] == 25
    assert schema["properties"]["project_name"]["maxLength"] == 60
    assert schema["properties"]["contact_person"]["required"] == [
        "first_name", "last_name",
    ]


def test_cd511_submit_populates_signature_and_date_through_generic_rules() -> None:
    application_form = submit_form("cd511", VALID_RESPONSE)
    response = application_form.application_response

    assert response["signature"] == "reviewer@example.gov"
    assert len(response["submitted_date"].split("-")) == 3
    assert_json_round_trip(response)


def test_cd511_keeps_policy_and_evidence_pins_with_the_runtime_selection() -> None:
    root = ARTIFACTS / "forms/cd511"
    policy = json.loads((root / "policy-content.json").read_text())
    binding = json.loads((root / "policy-binding.json").read_text())
    evidence = json.loads((root / "evidence.json").read_text())

    assert policy["sources"][0]["sha256"] == (
        "9c77e249ecb0755f6e000eaa0becd9f6a459fe91adf766f2c64e898d6253d92e"
    )
    assert binding["release"]["status"] == "draft"
    assert evidence["semanticReview"]["status"] == "proposed"


def test_cd511_canary_is_not_registered_before_release_review() -> None:
    registrations = json.loads(REGISTRATIONS.read_text())

    assert "cd511" not in registrations["forms"]
