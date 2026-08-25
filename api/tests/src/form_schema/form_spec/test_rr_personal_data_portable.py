"""Technical closure evidence for the unregistered R&R Personal Data package."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import _load_banked_form, load_form
from src.form_schema.form_spec.preview import build_preview_form, preview_form_id
from src.form_schema.form_spec.runtime_identity import runtime_identity
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.services.applications.apply_initial_population import (
    apply_initial_population_from_source_update,
)
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator

FORM_ID = "rr-personal-data"
XSD_NAME = "RR_PersonalData_1_2-V1.2.xsd"
XSD_SHA256 = "5f766d46d573da1f6bb326bcbc13338439ba75399ad09dee2380f65e892402cb"
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
PROTECTED_NAME_PATHS = (
    "/project_director/name/prefix",
    "/project_director/name/first_name",
    "/project_director/name/middle_name",
    "/project_director/name/last_name",
    "/project_director/name/suffix",
)


def _resolved_schema() -> dict:
    return resolve_jsonschema(copy.deepcopy(build_preview_form(FORM_ID).form_json_schema))


def _single_all_of(schema: dict) -> dict:
    [resolved] = schema["allOf"]
    return resolved


def _mock_session(*modified_target_ids: uuid.UUID):
    from unittest.mock import Mock

    session = Mock()
    session.execute.return_value.scalars.return_value.all.return_value = list(modified_target_ids)
    return session


def test_exact_package_is_preview_only_and_preserves_review_boundaries() -> None:
    manifest = json.loads((ARTIFACTS / "artifact-manifest.json").read_text())
    evidence = json.loads((ARTIFACTS / "forms" / FORM_ID / "evidence.json").read_text())

    assert FORM_ID in manifest["selection"]["forms"]
    assert evidence["semanticReview"]["status"] == "proposed"
    assert all(
        mapping["status"] == "proposed" for mapping in evidence["semanticReview"]["mappings"]
    )
    assert len(evidence["behaviorEvidence"]) == 4
    assert len(evidence["operationalBehaviorEvidence"]) == 5
    assert all(
        record["executionStatus"] == "compiled"
        for record in (
            *evidence["behaviorEvidence"],
            *evidence["operationalBehaviorEvidence"],
        )
    )
    with pytest.raises(ValueError, match="no SGG runtime identity"):
        runtime_identity(FORM_ID)
    with pytest.raises(ValueError, match="no SGG runtime identity"):
        load_form(FORM_ID)


def test_five_source_bound_name_prefills_are_protected_and_execute() -> None:
    projected = _load_banked_form(FORM_ID, project_xml=False)
    assert tuple(behavior.path for behavior in projected.operational_behavior) == (
        PROTECTED_NAME_PATHS
    )
    assert all(behavior.editability == "protected" for behavior in projected.operational_behavior)

    source = SimpleNamespace(
        application_form_id=uuid.uuid4(),
        form_id=preview_form_id("rr-sf424"),
        application_response={
            "principal_investigator": {
                "name": {
                    "prefix": "Dr.",
                    "first_name": "Ada",
                    "middle_name": "M",
                    "last_name": "Lovelace",
                    "suffix": "Ph.D.",
                }
            }
        },
    )
    target = SimpleNamespace(
        application_form_id=uuid.uuid4(),
        form_id=preview_form_id(FORM_ID),
        application_response={},
    )
    application = SimpleNamespace(application_id=uuid.uuid4(), application_forms=[source, target])

    changed = apply_initial_population_from_source_update(_mock_session(), application, source)

    assert changed == (target,)
    assert target.application_response == {
        "project_director": {
            "name": {
                "prefix": "Dr.",
                "first_name": "Ada",
                "middle_name": "M",
                "last_name": "Lovelace",
                "suffix": "Ph.D.",
            }
        }
    }
    project_director = _single_all_of(_resolved_schema()["properties"]["project_director"])
    name_schema = _single_all_of(project_director["properties"]["name"])
    assert all(
        name_schema["properties"][field]["readOnly"] is True
        for field in ("prefix", "first_name", "middle_name", "last_name", "suffix")
    )


def test_all_four_exact_exclusivity_contracts_validate() -> None:
    schema = _resolved_schema()
    project_director = _single_all_of(schema["properties"]["project_director"])
    co_project_director = _single_all_of(schema["properties"]["co_project_directors"]["items"])

    for role in (project_director, co_project_director):
        race = role["properties"]["race"]
        disability = role["properties"]["disability_status"]
        assert race["x-exclusive-values"] == ["Do Not Wish to Provide"]
        assert disability["x-exclusive-values"] == [
            "None",
            "Do Not Wish to Provide",
        ]
        assert Draft202012Validator(race).is_valid(["Asian", "White"])
        assert not Draft202012Validator(race).is_valid(["Asian", "Do Not Wish to Provide"])
        assert not Draft202012Validator(disability).is_valid(["Hearing", "None"])
        assert not Draft202012Validator(disability).is_valid(["Hearing", "Do Not Wish to Provide"])


def test_representative_xml_preserves_wire_values_and_validates_exact_xsd() -> None:
    projected = _load_banked_form(FORM_ID, project_xml=True)
    response = {
        "project_director": {
            "name": {"first_name": "Ada", "last_name": "Lovelace"},
            "sex": "Female",
            "race": ["Asian"],
            "ethnicity": "Non-Hispanic or Latino",
            "disability_status": ["None"],
            "citizenship": "US Citizen",
        },
        "co_project_directors": [
            {
                "name": {"first_name": "Grace", "last_name": "Hopper"},
                "race": ["Do Not Wish to Provide"],
                "ethnicity": "Do Not Wish to Provide",
                "disability_status": ["Do Not Wish to Provide"],
                "citizenship": "Do Not Wish to Provide",
            }
        ],
    }

    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=response,
            transform_config=projected.json_to_xml_schema,
        )
    )

    assert generated.success, generated.error_message
    assert generated.xml_data is not None
    assert "Not Hispanic or Latino" in generated.xml_data
    assert "Do Not Wish To Provide" in generated.xml_data
    xsd = XSD_DIRECTORY / XSD_NAME
    assert hashlib.sha256(xsd.read_bytes()).hexdigest() == XSD_SHA256
    validation = XSDValidator(XSD_DIRECTORY).validate_xml_for_form(
        generated.xml_data, XSD_NAME.removesuffix(".xsd")
    )
    assert validation["valid"], validation
