"""Unregistered consumer evidence for the portable EPA Key Contacts package."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from jsonschema import Draft202012Validator

from src.db.models.competition_models import ApplicationForm
from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import _load_banked_form, load_form
from src.form_schema.form_spec.preview import build_preview_form
from src.form_schema.form_spec.runtime_identity import runtime_identity
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context

FORM_ID = "epa-key-contacts"
ROLES = (
    "authorized_representative",
    "payee",
    "administrative_contact",
    "project_manager",
)
ROLE_REQUIRED_LEAVES = {
    "name.first_name",
    "name.last_name",
    "address.street1",
    "address.city",
    "address.country",
    "phone",
}
XSD = Path("src/services/xml_generation/xsds/EPA_KeyContacts_2_0-V2.0.xsd")
XSD_SHA256 = "157a9c8a21cdc39b4c6b5df94c3745ecd4f174cb390187441de862fb35b50b01"
PORTABLE_CI_MAP = ARTIFACTS.parent / "portable-form-ci-map.json"


def _resolved_schema() -> dict:
    projected = _load_banked_form(FORM_ID, project_xml=False)
    return resolve_jsonschema(copy.deepcopy(projected.form_json_schema))


def _complete_role(*, country: str = "URY: URUGUAY") -> dict:
    return {
        "name": {"first_name": "Ada", "last_name": "Lovelace"},
        "address": {
            "street1": "1 Example Street",
            "city": "Montevideo",
            "country": country,
        },
        "phone": "2025550100",
    }


def _required_leaf_paths(role_schema: dict) -> set[str]:
    [base] = role_schema["allOf"]
    required = set(base["required"])
    leaves = {field for field in required if field not in {"name", "address"}}
    for parent in ("name", "address"):
        assert parent in required
        leaves.update(f"{parent}.{field}" for field in base["properties"][parent]["required"])
    return leaves


def test_package_is_banked_for_preview_but_not_registered() -> None:
    manifest = json.loads((ARTIFACTS / "artifact-manifest.json").read_text())
    ci_map = json.loads(PORTABLE_CI_MAP.read_text())

    assert manifest["source"]["revision"] == "7c3be8e32968b49b5ce48f53a832c00220eb5bee"
    assert manifest["selection"]["forms"][-1] == FORM_ID
    assert ci_map["forms"][FORM_ID] == [
        "api/tests/src/form_schema/form_spec/test_epa_key_contacts_portable.py"
    ]
    assert hashlib.sha256(XSD.read_bytes()).hexdigest() == XSD_SHA256
    with pytest.raises(ValueError, match="no SGG runtime identity"):
        runtime_identity(FORM_ID)
    with pytest.raises(ValueError, match="no SGG runtime identity"):
        load_form(FORM_ID)


def test_optional_roles_enforce_the_six_source_required_values() -> None:
    schema = _resolved_schema()
    validator = Draft202012Validator(schema)

    assert validator.is_valid({})
    for role in ROLES:
        role_schema = schema["properties"][role]
        assert _required_leaf_paths(role_schema) == ROLE_REQUIRED_LEAVES
        assert not validator.is_valid({role: {"fax": "2025550199"}})
        assert validator.is_valid({role: _complete_role()})


def test_usa_roles_require_state_and_postal_code_without_changing_timing_claims() -> None:
    validator = Draft202012Validator(_resolved_schema())

    for role in ROLES:
        usa = _complete_role(country="USA: UNITED STATES")
        assert not validator.is_valid({role: usa})
        usa["address"].update({"state": "DC: District of Columbia", "zip_code": "20001"})
        assert validator.is_valid({role: usa})

    evidence = json.loads((ARTIFACTS / "forms" / FORM_ID / "evidence.json").read_text())
    by_status: dict[str, list[dict]] = {}
    for record in evidence["behaviorEvidence"]:
        by_status.setdefault(record["executionStatus"], []).append(record)
    assert len(by_status["compiled"]) == 32
    assert len(by_status["source-bound-uncompiled"]) == 4
    assert all(
        record["authority"] == "unresolved" for record in by_status["source-bound-uncompiled"]
    )
    assert evidence["semanticReview"]["status"] == "proposed"
    assert all(
        mapping["status"] == "proposed" for mapping in evidence["semanticReview"]["mappings"]
    )


def test_initial_preview_processing_does_not_materialize_empty_role_objects() -> None:
    preview = build_preview_form(FORM_ID)
    application_form = cast(
        ApplicationForm,
        SimpleNamespace(
            application_response={},
            application_form_id=uuid.uuid4(),
            form_id=preview.form_id,
            form=preview,
        ),
    )
    context = JsonRuleContext(application_form, JsonRuleConfig(do_field_validation=False))

    process_rule_schema_for_context(context)

    assert context.json_data == {}
    assert all(role not in context.json_data for role in ROLES)
