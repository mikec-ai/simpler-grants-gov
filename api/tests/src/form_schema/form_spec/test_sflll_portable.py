"""Portable SF-LLL conformance canary against the existing SGG oracle."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.browser_plan import build_browser_plan
from src.form_schema.form_spec.loader import load_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator
from tests.src.form_schema.form_spec.lifecycle import (
    ValidationCase,
    assert_json_round_trip,
    assert_validation_case,
    submit_form,
)

VALID_RESPONSE = {
    "federal_action_type": "Grant",
    "federal_action_status": "InitialAward",
    "report_type": "InitialFiling",
    "reporting_entity_type": "Prime",
    "reporting_organization": {
        "organization_name": "Example Research Institute",
        "address": {
            "street1": "1 Research Way",
            "city": "Bethesda",
            "state": "MD: Maryland",
            "zip_code": "20852",
        },
        "congressional_district": "MD-008",
    },
    "federal_agency_department": "Department of Health",
    "federal_program": {
        "name": "Health Research",
        "assistance_listing_number": "93.000",
    },
    "federal_action_number": "RFA-2026-001",
    "award_amount": "125000.00",
    "lobbying_registrant": {
        "name": {"first_name": "Ada", "last_name": "Lovelace"},
        "address": {
            "street1": "2 Main Street",
            "city": "Annapolis",
            "state": "MD: Maryland",
            "zip_code": "21401",
        },
    },
    "individuals_performing_services": [{"name": {"first_name": "Grace", "last_name": "Hopper"}}],
    "signature_block": {
        "name": {"first_name": "Alan", "last_name": "Turing"},
        "title": "Certifying Official",
        "phone": "202-555-0100",
    },
}
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
XSD_NAME = "SFLLL_2_0-V2.0.xsd"
XSD_SHA256 = "fff7449d00c715efb79d83b572bc7b1ef3e8171f6a9ba841436b26242e883664"


def _walk(nodes: list[object]):
    for node in nodes:
        if not isinstance(node, dict):
            continue
        yield node
        children = node.get("children", [])
        if isinstance(children, list):
            yield from _walk(children)


def test_sflll_loads_as_a_complete_structural_canary() -> None:
    projected = load_form("sflll")
    nodes = list(_walk(projected.form_ui_schema))

    assert projected.meta == {
        "id": "sflll",
        "legacyFormId": 670,
        "formName": "Disclosure of Lobbying Activities (SF-LLL)",
        "shortFormName": "SFLLL_2_0",
        "formVersion": "2.0",
        "agencyCode": "SGG",
        "ombNumber": "4040-0013",
    }
    assert len(projected.form_json_schema["properties"]) == 15
    assert len(projected.form_ui_schema) == 12
    assert sum(node.get("type") in {"field", "null"} for node in nodes) == 56
    assert sum("conditional" in node for node in nodes) == 11


def test_sflll_preserves_source_constraints_and_corrects_legacy_oracle_gaps() -> None:
    schema = resolve_jsonschema(copy.deepcopy(load_form("sflll").form_json_schema))

    assert schema["properties"]["tier"] == {
        "type": "integer",
        "minimum": 0,
        "maximum": 99,
        "title": "Tier",
    }
    assert schema["properties"]["federal_action_number"]["allOf"][0]["maxLength"] == 110
    services = schema["properties"]["individuals_performing_services"]
    assert services["minItems"] == 1
    assert services["maxItems"] == 10


def test_sflll_conditionals_cross_the_adapter_naming_boundary() -> None:
    projected = load_form("sflll")
    conditional_nodes = [node for node in _walk(projected.form_ui_schema) if "conditional" in node]

    pointers = {node["conditional"]["when"]["ref"]["pointer"] for node in conditional_nodes}
    assert pointers == {"/report_type", "/reporting_entity_type"}
    assert projected.form_json_schema["allOf"][-1]["then"] == {"required": ["prime_organization"]}


def test_sflll_evidence_is_pinned_to_the_factory_and_exact_xsd() -> None:
    evidence = json.loads((ARTIFACTS / "forms" / "sflll" / "evidence.json").read_text())

    assert evidence["extraction"] == {
        "artifact": "artifacts/proof/grantsgov-SFLLL.jsonl.manifest.json",
        "extractedAt": "2026-08-18T17:10:53.925323Z",
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "4312f6504b060e2b9ffdbd2307fc41130c3123a0",
        "sourceSetSha256": "86c5849f65a3f3d8fcdc7da17cfa6070c185008eae9916184e7d6c32cd098b05",
    }
    assert evidence["semanticReview"]["status"] == "proposed"
    assert [
        (source["type"], source["uri"], source["sha256"]) for source in evidence["sources"]
    ] == [
        (
            "xsd",
            "https://apply07.grants.gov/apply/forms/schemas/SFLLL_2_0-V2.0.xsd",
            "fff7449d00c715efb79d83b572bc7b1ef3e8171f6a9ba841436b26242e883664",
        ),
        (
            "xsd",
            "https://apply07.grants.gov/apply/system/schemas/Global-V1.0.xsd",
            "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb",
        ),
        (
            "xsd",
            "https://apply07.grants.gov/apply/system/schemas/GlobalLibrary-V2.0.xsd",
            "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8",
        ),
        (
            "xsd",
            "https://apply07.grants.gov/apply/system/schemas/UniversalCodes-V2.0.xsd",
            "78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a",
        ),
    ]


def test_sflll_executes_conditional_submission_requirements() -> None:
    assert_validation_case("sflll", ValidationCase("initial filing", VALID_RESPONSE, frozenset()))

    material_change = copy.deepcopy(VALID_RESPONSE)
    material_change["report_type"] = "MaterialChange"
    assert_validation_case(
        "sflll",
        ValidationCase(
            "material change without details",
            material_change,
            frozenset({"$.material_change"}),
        ),
    )
    material_change["material_change"] = {
        "year": "2026",
        "quarter": "2",
        "last_report_date": "2026-04-01",
    }
    assert_validation_case(
        "sflll", ValidationCase("complete material change", material_change, frozenset())
    )

    subawardee = copy.deepcopy(VALID_RESPONSE)
    subawardee["reporting_entity_type"] = "SubAwardee"
    assert_validation_case(
        "sflll",
        ValidationCase(
            "subawardee without prime organization",
            subawardee,
            frozenset({"$.prime_organization"}),
        ),
    )


def test_sflll_submit_populates_signature_and_date_through_generic_rules() -> None:
    application_form = submit_form("sflll", VALID_RESPONSE)
    signature = application_form.application_response["signature_block"]

    assert signature["signature"] == "reviewer@example.gov"
    assert len(signature["signed_date"].split("-")) == 3
    assert_json_round_trip(application_form.application_response)


def test_sflll_submitter_output_emits_exact_xsd_valid_xml() -> None:
    application_form = submit_form("sflll", VALID_RESPONSE)
    projected = load_form("sflll")
    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=application_form.application_response,
            transform_config=projected.json_to_xml_schema,
        )
    )

    assert generated.success, generated.error_message
    assert generated.xml_data is not None
    assert "<SFLLL_2_0:Signature>reviewer@example.gov</" in generated.xml_data
    xsd = XSD_DIRECTORY / XSD_NAME
    assert hashlib.sha256(xsd.read_bytes()).hexdigest() == XSD_SHA256
    validation = XSDValidator(XSD_DIRECTORY).validate_xml(generated.xml_data, xsd)
    assert validation["valid"], validation


def test_sflll_browser_plan_uses_only_generic_declared_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ENABLE_PORTABLE_FORM_PREVIEW", "true")
    monkeypatch.setenv("PORTABLE_BROWSER_FORM_IDS", "sflll")

    capabilities = build_browser_plan()["forms"][0]["capabilities"]

    assert len(capabilities["conditional"]["declarations"]) == 11
    assert capabilities["repeater"]["declarations"] == [
        {
            "definition": "/properties/individuals_performing_services",
            "name": "individuals_performing_services",
        }
    ]
    assert {
        declaration["responsePath"] for declaration in capabilities["readOnly"]["declarations"]
    } == {"/signature_block/signature", "/signature_block/signed_date"}
    assert len(capabilities["calculation"]["declarations"]) == 3
    assert capabilities["staticContent"]["applicability"] == "not_applicable"


def test_sflll_canary_is_not_registered_before_release_review() -> None:
    registrations = json.loads(REGISTRATIONS.read_text())

    assert "sflll" not in registrations["forms"]
