"""R&R SF-424 conformance canary for the portable form specification.

The package is intentionally not registered as a runtime form yet. Exact XML output and
the remaining source-review gates must become declarative before it can replace a
production implementation.
"""

import copy
import json

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import load_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from tests.src.form_schema.form_spec.lifecycle import (
    ValidationCase,
    assert_json_round_trip,
    assert_validation_case,
    submit_form,
)


VALID_RESPONSE = {
    "submission_type_code": "Application",
    "applicant_info": {
        "organization_info": {
            "organization_name": "Example Research Institute",
            "address": {
                "street1": "1 Research Way",
                "city": "Bethesda",
                "state": "MD: Maryland",
                "zip_code": "20852",
                "country": "USA: UNITED STATES",
            },
            "sam_uei": "EXAMPLE12345",
        },
        "contact_person_info": {
            "name": {"first_name": "Casey", "last_name": "Contact"},
            "address": {
                "street1": "1 Research Way",
                "city": "Bethesda",
                "state": "MD: Maryland",
                "zip_code": "20852",
                "country": "USA: UNITED STATES",
            },
            "phone": "301-555-0100",
            "email": "casey@example.gov",
        },
    },
    "employer_id": "123456789",
    "applicant_type": {
        "applicant_type_code": (
            "M: Nonprofit with 501C3 IRS Status (Other than Institution of Higher Education)"
        )
    },
    "application_type": {
        "application_type_code": "New",
        "is_other_agency_submission": "N: No",
    },
    "federal_agency_name": "Example Federal Agency",
    "project_title": "Example research project",
    "proposed_project_period": {
        "proposed_start_date": "2026-10-01",
        "proposed_end_date": "2029-09-30",
    },
    "applicant_congressional_district": "MD-008",
    "principal_investigator": {
        "name": {"first_name": "Parker", "last_name": "Investigator"},
        "organization_name": "Example Research Institute",
        "address": {
            "street1": "1 Research Way",
            "city": "Bethesda",
            "state": "MD: Maryland",
            "zip_code": "20852",
            "country": "USA: UNITED STATES",
        },
        "phone": "301-555-0101",
        "email": "parker@example.gov",
    },
    "estimated_project_funding": {
        "total_estimated_amount": 100000,
        "total_non_federal_requested": 0,
        "total_federal_non_federal_requested": 100000,
        "estimated_program_income": 0,
    },
    "state_review": {"state_review_code_type": "Program is not covered by E.O. 12372"},
    "trust_agree": "Y: Yes",
    "authorized_representative": {
        "name": {"first_name": "Avery", "last_name": "Representative"},
        "title": "Authorized Organizational Representative",
        "organization_name": "Example Research Institute",
        "address": {
            "street1": "1 Research Way",
            "city": "Bethesda",
            "state": "MD: Maryland",
            "zip_code": "20852",
            "country": "USA: UNITED STATES",
        },
        "phone": "301-555-0102",
        "email": "avery@example.gov",
    },
}


def _walk(nodes: list[object]):
    for node in nodes:
        if not isinstance(node, dict):
            continue
        yield node
        children = node.get("children", [])
        if isinstance(children, list):
            yield from _walk(children)


def test_rr_sf424_loads_as_a_complete_structural_canary() -> None:
    projected = load_form("rr-sf424")
    nodes = list(_walk(projected.form_ui_schema))

    assert projected.meta == {
        "id": "rr-sf424",
        "formId": "98f03cc4-5cd8-455b-a318-ba5abd0cf572",
        "legacyFormId": 768,
        "formName": "[Draft] Research & Related Application for Federal Assistance (SF424 R&R)",
        "shortFormName": "RR_SF424_5_0",
        "formVersion": "5.0",
        "agencyCode": "GRANTS_GOV",
        "ombNumber": "4040-0001",
        "formType": "RRSF424",
        "sggVersion": "1.0",
    }
    assert len(projected.form_json_schema["properties"]) == 28
    assert len(projected.form_json_schema["allOf"]) == 4
    assert len(projected.form_ui_schema) == 21
    assert sum(node.get("type") in {"field", "null"} for node in nodes) == 106


def test_rr_sf424_conditionals_cross_the_adapter_naming_boundary() -> None:
    projected = load_form("rr-sf424")
    conditional_nodes = [node for node in _walk(projected.form_ui_schema) if "conditional" in node]

    assert len(conditional_nodes) == 8
    pointers = {node["conditional"]["when"]["ref"]["pointer"] for node in conditional_nodes}
    assert "/submission_type_code" in pointers
    assert "/applicant_type/applicant_type_code" in pointers
    assert "/application_type/application_type_code" in pointers
    assert "/state_review/state_review_code_type" in pointers
    assert all("_" in segment for pointer in pointers for segment in pointer.split("/") if segment)


def test_rr_sf424_revision_choices_preserve_the_encoded_wire_contract() -> None:
    projected = load_form("rr-sf424")
    revision = projected.form_json_schema["properties"]["application_type"]["properties"][
        "revision_code"
    ]
    revision_enum = projected.form_json_schema["$defs"]["ResearchRevisionCode"]["enum"]

    assert revision_enum == ["A", "B", "C", "D", "E", "AC", "AD", "BC", "BD"]
    assert revision["x-encoded-checkbox-group"] == {
        "choices": [
            {"code": "A", "label": "A. Increase Award"},
            {"code": "B", "label": "B. Decrease Award"},
            {"code": "C", "label": "C. Increase Duration"},
            {"code": "D", "label": "D. Decrease Duration"},
            {"code": "E", "label": "E. Other"},
        ],
        "combinations": [
            {"value": "A", "members": ["A"]},
            {"value": "B", "members": ["B"]},
            {"value": "C", "members": ["C"]},
            {"value": "D", "members": ["D"]},
            {"value": "E", "members": ["E"]},
            {"value": "AC", "members": ["A", "C"]},
            {"value": "AD", "members": ["A", "D"]},
            {"value": "BC", "members": ["B", "C"]},
            {"value": "BD", "members": ["B", "D"]},
        ],
    }


def test_rr_sf424_evidence_stays_source_bound_and_semantically_unaccepted() -> None:
    evidence = json.loads((ARTIFACTS / "forms" / "rr-sf424" / "evidence.json").read_text())

    assert evidence["extraction"] == {
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "dfe9e47ffd6a25c967b8ed38703480ccdc15a8ef",
        "artifact": "artifacts/proof/grantsgov-RRSF424.jsonl.manifest.json",
        "sourceSetSha256": "81ad602bf94391d4a7db80558802288452848aef97e68d4ca4ad1fe3d4b7e035",
        "extractedAt": "2026-08-18T16:54:29.252851Z",
    }
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}
    assert [(source["type"], source["sha256"]) for source in evidence["sources"]] == [
        ("dat", "532938a75c587bdc8813fd3af625be4338281d0491999fc39aeaaac51b79c9c1"),
        ("xsd", "f140f32afed9d7efbe30fc8f299542bbbc3121dbc87a79aa351fcf096163d3bc"),
        ("xsd", "ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d"),
        ("xsd", "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb"),
        ("xsd", "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8"),
        ("xsd", "78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a"),
    ]


def test_rr_sf424_response_survives_save_and_reload_without_loss() -> None:
    assert_json_round_trip(VALID_RESPONSE)


def test_rr_sf424_executes_conditional_submission_requirements() -> None:
    valid = copy.deepcopy(VALID_RESPONSE)
    assert_validation_case(
        "rr-sf424",
        ValidationCase("ordinary new application", valid, frozenset()),
    )

    corrected = copy.deepcopy(valid)
    corrected["submission_type_code"] = "Change/Corrected Application"
    assert_validation_case(
        "rr-sf424",
        ValidationCase(
            "corrected application without a Grants.gov tracking ID",
            corrected,
            frozenset({"$.grants_gov_tracking_id"}),
        ),
    )
    corrected["grants_gov_tracking_id"] = "GRANT12345678"
    assert_validation_case(
        "rr-sf424",
        ValidationCase("corrected application with its tracking ID", corrected, frozenset()),
    )

    renewal = copy.deepcopy(valid)
    renewal["application_type"]["application_type_code"] = "Renewal"
    assert_validation_case(
        "rr-sf424",
        ValidationCase(
            "renewal without its federal identifier",
            renewal,
            frozenset({"$.federal_id"}),
        ),
    )
    renewal["federal_id"] = "R01EXAMPLE"
    assert_validation_case(
        "rr-sf424",
        ValidationCase("renewal with its federal identifier", renewal, frozenset()),
    )


def test_rr_sf424_submit_populates_the_aor_signature_and_dates() -> None:
    application_form = submit_form("rr-sf424", VALID_RESPONSE)
    response = application_form.application_response

    assert response["aor_signature"] == "reviewer@example.gov"
    assert response["aor_signed_date"] == response["submitted_date"]
    assert len(response["submitted_date"].split("-")) == 3


def test_rr_sf424_xml_is_declarative_but_registration_awaits_source_review() -> None:
    manifest = json.loads((ARTIFACTS / "forms" / "rr-sf424" / "manifest.json").read_text())
    registrations = json.loads(REGISTRATIONS.read_text())

    assert manifest["artifacts"]["targets/grants-gov-xml.json"] == "generated"
    assert "rr-sf424" not in registrations["forms"]
