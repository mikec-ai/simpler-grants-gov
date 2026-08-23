"""Portable SF-424B family canaries against the existing base-form oracle."""

from __future__ import annotations

import copy
import json

import pytest
from jsonschema import Draft202012Validator

from src.form_schema.form_spec.bank import ARTIFACTS, verify_artifacts
from src.form_schema.form_spec.loader import build_runtime_form, load_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from src.form_schema.form_spec.runtime_identity import runtime_identity
from src.form_schema.forms.sf424b import SF424b_v1_1
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from tests.src.form_schema.form_spec.lifecycle import (
    ValidationCase,
    assert_json_round_trip,
    assert_validation_case,
    submit_form,
)

RELEASABLE_PROFILES = ("sf424b", "mandatory-sf424b", "individual-sf424b")
VALID_RESPONSE = {
    "title": "Executive Director",
    "applicant_organization": "Example Research Organization",
}


def _walk(nodes: list[object]):
    for node in nodes:
        if not isinstance(node, dict):
            continue
        yield node
        children = node.get("children", [])
        if isinstance(children, list):
            yield from _walk(children)


def _resolved(form_id: str) -> dict:
    return resolve_jsonschema(copy.deepcopy(load_form(form_id).form_json_schema))


def test_base_form_uses_the_legacy_runtime_identity_and_source_identity() -> None:
    runtime = build_runtime_form("sf424b")
    portable = load_form("sf424b")

    assert portable.meta == {
        "id": "sf424b",
        "legacyFormId": 240,
        "formName": "Assurances for Non-Construction Programs (SF-424B)",
        "shortFormName": "SF424B",
        "formVersion": "1.1",
        "agencyCode": "SGG",
        "ombNumber": "4040-0007",
    }
    assert runtime.form_id == SF424b_v1_1.form_id
    assert runtime.form_type == SF424b_v1_1.form_type
    assert runtime.sgg_version == SF424b_v1_1.sgg_version


def test_base_schema_matches_oracle_constraints_and_classifies_source_correct_deltas() -> None:
    portable = _resolved("sf424b")
    oracle = resolve_jsonschema(copy.deepcopy(SF424b_v1_1.form_json_schema))

    assert portable["required"] == oracle["required"] == ["title", "applicant_organization"]
    for name in ("signature", "title", "applicant_organization", "date_signed"):
        portable_leaf = portable["properties"][name]["allOf"][0]
        oracle_leaf = oracle["properties"][name]["allOf"][0]
        for keyword in ("type", "format", "minLength", "maxLength"):
            assert portable_leaf.get(keyword) == oracle_leaf.get(keyword), (name, keyword)

    # Official data-element rules say these values come from the application cover.
    # The legacy oracle exposed both as editable fields; the portable profile corrects that
    # ownership while retaining identical validation constraints and response names.
    assert portable["properties"]["title"]["readOnly"] is True
    assert portable["properties"]["applicant_organization"]["readOnly"] is True
    assert "readOnly" not in oracle["properties"]["title"]
    assert "readOnly" not in oracle["properties"]["applicant_organization"]

    acceptance = load_form("sf424b").form_ui_schema[-1]
    oracle_acceptance = SF424b_v1_1.form_ui_schema[-1]
    assert acceptance["name"] == oracle_acceptance["name"] == "signature"
    assert [row["definition"] for row in acceptance["children"]] == [
        row["definition"] for row in oracle_acceptance["children"]
    ]
    assert [row["type"] for row in acceptance["children"]] == ["null", "null", "null", "null"]
    assert [row["type"] for row in oracle_acceptance["children"]] == [
        "null",
        "field",
        "field",
        "null",
    ]


def test_one_static_policy_bundle_drives_all_profiles_without_response_fields() -> None:
    policy = json.loads((ARTIFACTS / "forms/sf424b/policy-content.json").read_text())
    assert policy["contract"] == "policy-content/v1"
    assert policy["id"] == "grants-gov/nonconstruction-assurances"
    assert policy["version"] == "1.1"
    assert len(policy["sections"][1]["items"]) == 19
    assert policy["sections"][1]["presentationOrder"] == ["note", "preamble", "items"]

    for form_id in RELEASABLE_PROFILES:
        root = ARTIFACTS / "forms" / form_id
        assert json.loads((root / "policy-content.json").read_text()) == policy
        binding = json.loads((root / "policy-binding.json").read_text())
        assert binding["policy"] == {"id": policy["id"], "version": "1.1"}
        assert binding["acceptance"]["event"] == "submission"
        assert binding["acceptance"]["attestsTo"] == ["assurances"]
        schema = load_form(form_id).form_json_schema
        assert set(schema["properties"]) == {
            "signature",
            "title",
            "applicant_organization",
            "date_signed",
        }


@pytest.mark.parametrize("form_id", RELEASABLE_PROFILES)
def test_acceptance_allows_missing_submission_values_then_populates_them(form_id: str) -> None:
    assert_validation_case(
        form_id,
        ValidationCase("pre-submit acceptance envelope", VALID_RESPONSE, frozenset()),
    )
    submitted = submit_form(form_id, VALID_RESPONSE)
    assert submitted.application_response["signature"] == "reviewer@example.gov"
    assert len(submitted.application_response["date_signed"].split("-")) == 3
    assert_json_round_trip(submitted.application_response)


def test_missing_required_identity_matches_the_legacy_oracle() -> None:
    portable = Draft202012Validator(_resolved("sf424b"))
    oracle_schema = resolve_jsonschema(copy.deepcopy(SF424b_v1_1.form_json_schema))
    oracle = Draft202012Validator(oracle_schema)

    for validator in (portable, oracle):
        assert list(validator.iter_errors(VALID_RESPONSE)) == []
        missing_title = [
            error.json_path
            for error in validator.iter_errors({
                "applicant_organization": "Example Research Organization"
            })
        ]
        assert missing_title == ["$"]


def test_rules_and_version_match_the_legacy_oracle() -> None:
    portable = load_form("sf424b")
    assert (
        portable.form_rule_schema
        == SF424b_v1_1.form_rule_schema
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
    for form_id in ("sf424b", "mandatory-sf424b"):
        schema = load_form(form_id).form_json_schema
        assert schema["properties"]["title"]["readOnly"] is True
        assert schema["properties"]["applicant_organization"]["readOnly"] is True
        assert [row["type"] for row in load_form(form_id).form_ui_schema[-1]["children"]] == [
            "null",
            "null",
            "null",
            "null",
        ]

    individual = load_form("individual-sf424b")
    assert "readOnly" not in individual.form_json_schema["properties"]["title"]
    assert "readOnly" not in individual.form_json_schema["properties"]["applicant_organization"]
    assert [row["type"] for row in individual.form_ui_schema[-1]["children"]] == [
        "null",
        "field",
        "field",
        "null",
    ]


def test_print_shape_and_artifact_lock_are_generic() -> None:
    verify_artifacts()
    for form_id in RELEASABLE_PROFILES:
        loaded = load_form(form_id)
        for section in loaded.form_ui_schema:
            assert section["type"] == "section"
            for field in section["children"]:
                assert field["type"] in {"field", "null"}
                name = field["definition"].removeprefix("/properties/")
                assert name in loaded.form_json_schema["properties"]


def test_profiles_remain_unregistered_and_rr_is_banked_only() -> None:
    registrations = json.loads(REGISTRATIONS.read_text())["forms"]
    selected = json.loads((ARTIFACTS / "artifact-manifest.json").read_text())["selection"]["forms"]
    for form_id in RELEASABLE_PROFILES:
        assert form_id not in registrations
        runtime_identity(form_id)

    assert "rr-sf424b" in selected
    release = json.loads((ARTIFACTS / "forms/rr-sf424b/policy-binding.json").read_text())["release"]
    xsd_gate = next(
        gate for gate in release["gates"] if gate["id"] == "official-xsd-version-consistency"
    )
    assert release["status"] == "draft"
    assert xsd_gate["status"] == "passed"
    assert "upstream metadata defect" in xsd_gate["note"]
    assert {gate["id"] for gate in release["gates"] if gate["status"] == "pending"} == {
        "policy-owner-review",
        "accessibility-review",
        "instructions-review",
        "production-registration",
    }
    with pytest.raises(ValueError, match="no SGG runtime identity"):
        runtime_identity("rr-sf424b")
