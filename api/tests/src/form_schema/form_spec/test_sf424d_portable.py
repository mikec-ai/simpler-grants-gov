"""Portable SF-424D family canaries against the existing base-form oracle."""

from __future__ import annotations

import copy
import json

from jsonschema import Draft202012Validator

from src.form_schema.form_spec.bank import ARTIFACTS, verify_artifacts
from src.form_schema.form_spec.loader import build_runtime_form, load_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from src.form_schema.form_spec.runtime_identity import runtime_identity
from src.form_schema.forms.sf424d import SF424d_v1_1
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from tests.src.form_schema.form_spec.lifecycle import (
    ValidationCase,
    assert_json_round_trip,
    assert_validation_case,
    submit_form,
)

RELEASABLE_PROFILES = ("sf424d", "mandatory-sf424d", "individual-sf424d")
VALID_RESPONSE = {
    "title": "Executive Director",
    "applicant_organization": "Example Research Organization",
}


def _resolved(form_id: str) -> dict:
    return resolve_jsonschema(copy.deepcopy(load_form(form_id).form_json_schema))


def test_base_form_uses_the_legacy_runtime_identity_and_source_identity() -> None:
    runtime = build_runtime_form("sf424d")
    portable = load_form("sf424d")

    assert portable.meta == {
        "id": "sf424d",
        "legacyFormId": 238,
        "formName": "Assurances for Construction Programs (SF-424D)",
        "shortFormName": "SF424D",
        "formVersion": "1.1",
        "agencyCode": "SGG",
        "ombNumber": "4040-0009",
    }
    assert runtime.form_id == SF424d_v1_1.form_id
    assert runtime.form_type == SF424d_v1_1.form_type
    assert runtime.sgg_version == SF424d_v1_1.sgg_version


def test_base_schema_matches_oracle_constraints_and_source_correct_ownership() -> None:
    portable = _resolved("sf424d")
    oracle = resolve_jsonschema(copy.deepcopy(SF424d_v1_1.form_json_schema))

    assert portable["required"] == oracle["required"] == ["title", "applicant_organization"]
    for name in ("signature", "title", "applicant_organization", "date_signed"):
        portable_leaf = portable["properties"][name]["allOf"][0]
        oracle_leaf = oracle["properties"][name]["allOf"][0]
        for keyword in ("type", "format", "minLength", "maxLength"):
            assert portable_leaf.get(keyword) == oracle_leaf.get(keyword), (name, keyword)

    assert portable["properties"]["title"]["readOnly"] is True
    assert portable["properties"]["applicant_organization"]["readOnly"] is True
    assert "readOnly" not in oracle["properties"]["title"]
    assert "readOnly" not in oracle["properties"]["applicant_organization"]

    acceptance = load_form("sf424d").form_ui_schema[-1]
    oracle_acceptance = SF424d_v1_1.form_ui_schema[-1]
    assert acceptance["name"] == oracle_acceptance["name"] == "signature"
    assert [row["definition"] for row in acceptance["children"]] == [
        row["definition"] for row in oracle_acceptance["children"]
    ]
    assert [row["type"] for row in acceptance["children"]] == ["null"] * 4
    assert [row["type"] for row in oracle_acceptance["children"]] == [
        "null",
        "field",
        "field",
        "null",
    ]


def test_one_static_policy_bundle_drives_all_profiles_without_response_fields() -> None:
    policy = json.loads((ARTIFACTS / "forms/sf424d/policy-content.json").read_text())
    assert policy["contract"] == "policy-content/v1"
    assert policy["id"] == "grants-gov/construction-assurances"
    assert policy["version"] == "1.1"
    assert len(policy["sections"][1]["items"]) == 20
    assert policy["sections"][1]["presentationOrder"] == ["note", "preamble", "items"]

    for form_id in RELEASABLE_PROFILES:
        root = ARTIFACTS / "forms" / form_id
        assert json.loads((root / "policy-content.json").read_text()) == policy
        binding = json.loads((root / "policy-binding.json").read_text())
        assert binding["policy"] == {"id": policy["id"], "version": "1.1"}
        assert binding["acceptance"]["event"] == "submission"
        assert binding["acceptance"]["attestsTo"] == ["assurances"]
        assert set(load_form(form_id).form_json_schema["properties"]) == {
            "signature",
            "title",
            "applicant_organization",
            "date_signed",
        }


def test_acceptance_allows_missing_submission_values_then_populates_them() -> None:
    for form_id in RELEASABLE_PROFILES:
        assert_validation_case(
            form_id,
            ValidationCase("pre-submit acceptance envelope", VALID_RESPONSE, frozenset()),
        )
        submitted = submit_form(form_id, VALID_RESPONSE)
        assert submitted.application_response["signature"] == "reviewer@example.gov"
        assert len(submitted.application_response["date_signed"].split("-")) == 3
        assert_json_round_trip(submitted.application_response)


def test_missing_required_identity_matches_the_legacy_oracle() -> None:
    portable = Draft202012Validator(_resolved("sf424d"))
    oracle = Draft202012Validator(resolve_jsonschema(copy.deepcopy(SF424d_v1_1.form_json_schema)))

    for validator in (portable, oracle):
        assert list(validator.iter_errors(VALID_RESPONSE)) == []
        missing_title = [
            error.json_path
            for error in validator.iter_errors(
                {"applicant_organization": "Example Research Organization"}
            )
        ]
        assert missing_title == ["$"]


def test_rules_and_version_match_the_legacy_oracle() -> None:
    portable = load_form("sf424d")
    assert (
        portable.form_rule_schema
        == SF424d_v1_1.form_rule_schema
        == {
            "signature": {"gg_post_population": {"rule": "signature"}},
            "date_signed": {"gg_post_population": {"rule": "current_date"}},
        }
    )
    assert portable.meta["formVersion"] == "1.1"
    assert portable.json_to_xml_schema is not None
    assert portable.json_to_xml_schema["form_version_identifier"]["xml_transform"] == {
        "target": "FormVersionIdentifier",
        "namespace": "glob",
        "static_value": "1.1",
    }


def test_individual_editability_is_the_only_response_ownership_delta() -> None:
    for form_id in ("sf424d", "mandatory-sf424d"):
        loaded = load_form(form_id)
        assert loaded.form_json_schema["properties"]["title"]["readOnly"] is True
        assert loaded.form_json_schema["properties"]["applicant_organization"]["readOnly"] is True
        assert [row["type"] for row in loaded.form_ui_schema[-1]["children"]] == ["null"] * 4

    individual = load_form("individual-sf424d")
    assert "readOnly" not in individual.form_json_schema["properties"]["title"]
    assert "readOnly" not in individual.form_json_schema["properties"]["applicant_organization"]
    assert [row["type"] for row in individual.form_ui_schema[-1]["children"]] == [
        "null",
        "field",
        "field",
        "null",
    ]


def test_print_shape_artifact_lock_and_absent_registration_are_generic() -> None:
    manifest = verify_artifacts()
    assert set(RELEASABLE_PROFILES) <= set(manifest["selection"]["forms"])
    registrations = json.loads(REGISTRATIONS.read_text())["forms"]
    for form_id in RELEASABLE_PROFILES:
        runtime_identity(form_id)
        assert form_id not in registrations
        assert build_runtime_form(form_id).form_type.value == "SF424D"
        loaded = load_form(form_id)
        for section in loaded.form_ui_schema:
            assert section["type"] == "section"
            for field in section["children"]:
                assert field["type"] in {"field", "null"}
                name = field["definition"].removeprefix("/properties/")
                assert name in loaded.form_json_schema["properties"]
