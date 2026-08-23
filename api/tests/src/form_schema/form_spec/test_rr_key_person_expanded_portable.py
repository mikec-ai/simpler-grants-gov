"""R&R Senior/Key Person lifecycle canary without production registration."""

import copy
import json
from collections.abc import Iterator
from typing import Any

import pytest

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import build_runtime_form, load_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from tests.src.form_schema.form_spec.lifecycle import (
    ValidationCase,
    assert_validation_case,
    submit_form,
)

PI_BIOGRAPHICAL_SKETCH = "00000000-0000-4000-8000-000000000001"
PI_CURRENT_SUPPORT = "00000000-0000-4000-8000-000000000002"
KEY_PERSON_BIOGRAPHICAL_SKETCH = "00000000-0000-4000-8000-000000000003"
KEY_PERSON_CURRENT_SUPPORT = "00000000-0000-4000-8000-000000000004"
ADDITIONAL_PROFILES = "00000000-0000-4000-8000-000000000005"
ADDITIONAL_BIOGRAPHICAL_SKETCHES = "00000000-0000-4000-8000-000000000006"
ADDITIONAL_CURRENT_SUPPORT = "00000000-0000-4000-8000-000000000007"

ATTACHMENT_IDS = frozenset({
    PI_BIOGRAPHICAL_SKETCH,
    PI_CURRENT_SUPPORT,
    KEY_PERSON_BIOGRAPHICAL_SKETCH,
    KEY_PERSON_CURRENT_SUPPORT,
    ADDITIONAL_PROFILES,
    ADDITIONAL_BIOGRAPHICAL_SKETCHES,
    ADDITIONAL_CURRENT_SUPPORT,
})


def _person(
    first_name: str,
    last_name: str,
    *,
    project_role: str = "Co-Investigator",
) -> dict[str, Any]:
    return {
        "name": {"first_name": first_name, "last_name": last_name},
        "organization_name": "Example Research Institute",
        "address": {
            "street1": "1 Research Way",
            "city": "Bethesda",
            "state": "MD: Maryland",
            "zip_code": "208521234",
            "country": "USA: UNITED STATES",
        },
        "phone": "301-555-0100",
        "email": f"{first_name.lower()}@example.gov",
        "project_role": project_role,
    }


VALID_RESPONSE: dict[str, Any] = {
    "principal_investigator": {
        **_person("Parker", "Investigator", project_role="PD/PI"),
        "biographical_sketch": PI_BIOGRAPHICAL_SKETCH,
        "current_pending_support": PI_CURRENT_SUPPORT,
    },
    "senior_key_persons": [
        {
            **_person("Casey", "Collaborator"),
            "biographical_sketch": KEY_PERSON_BIOGRAPHICAL_SKETCH,
            "current_pending_support": KEY_PERSON_CURRENT_SUPPORT,
        }
    ],
    "additional_profiles": ADDITIONAL_PROFILES,
    "additional_biographical_sketches": ADDITIONAL_BIOGRAPHICAL_SKETCHES,
    "additional_current_pending_support": ADDITIONAL_CURRENT_SUPPORT,
}


def _walk(value: object) -> Iterator[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _walk(item)
    elif isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _walk(item)


def test_key_person_loads_without_form_specific_adapter_code() -> None:
    projected = load_form("rr-key-person-expanded")
    fields = [node for node in _walk(projected.form_ui_schema) if node.get("type") == "field"]

    assert projected.meta == {
        "id": "rr-key-person-expanded",
        "legacyFormId": 774,
        "formName": "Research & Related Senior/Key Person Profile (Expanded)",
        "shortFormName": "RR_KeyPersonExpanded_4_0",
        "formVersion": "4.0",
        "agencyCode": "GRANTS_GOV",
        "ombNumber": "4040-0001",
    }
    assert list(projected.form_json_schema["properties"]) == [
        "principal_investigator",
        "senior_key_persons",
        "additional_profiles",
        "additional_biographical_sketches",
        "additional_current_pending_support",
    ]
    assert projected.form_json_schema["properties"]["senior_key_persons"]["maxItems"] == 99
    assert len(fields) == 57


def test_key_person_is_registration_ready_but_not_release_opted_in() -> None:
    runtime_form = build_runtime_form("rr-key-person-expanded")
    registrations = json.loads(REGISTRATIONS.read_text())

    assert runtime_form.form_type is not None
    assert runtime_form.form_type.value == "RRKeyPersonExpanded"
    assert str(runtime_form.form_id) == "2a638e46-7680-55ba-a11a-4d152f37ca1e"
    assert runtime_form.form_instruction_id is None
    assert "rr-key-person-expanded" not in registrations["forms"]


def test_repeated_person_conditions_use_current_item_scope() -> None:
    projected = load_form("rr-key-person-expanded")
    conditional = [node for node in _walk(projected.form_ui_schema) if "conditional" in node]
    root = [node for node in conditional if node["conditional"]["when"]["ref"]["scope"] == "root"]
    item = [node for node in conditional if node["conditional"]["when"]["ref"]["scope"] == "item"]

    assert len(root) == 3
    assert len(item) == 3
    assert {node["conditional"]["when"]["ref"]["pointer"] for node in item} == {
        "/address/country",
        "/project_role",
    }
    other_role = next(node for node in item if node["conditional"]["when"]["op"] == "in")
    assert other_role["conditional"]["when"]["values"] == [
        "Other Professional",
        "Other (Specify)",
    ]


def test_person_attachments_compile_while_overflow_semantics_stay_review_gated() -> None:
    projected = load_form("rr-key-person-expanded")
    attachment_rules = [
        node
        for node in _walk(projected.form_rule_schema)
        if node.get("gg_validation", {}).get("rule") == "attachment"
    ]
    assert len(attachment_rules) == 7

    root = ARTIFACTS / "forms" / "rr-key-person-expanded"
    evidence = json.loads((root / "evidence.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    assert evidence["extraction"] == {
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "4312f6504b060e2b9ffdbd2307fc41130c3123a0",
        "artifact": "artifacts/proof/grantsgov-RRKeyPersonExpanded.jsonl.manifest.json",
        "sourceSetSha256": "8866396d99e32eeec6618ea63c52c2b205718dc481482b27ab61699ecd2efeb0",
        "extractedAt": "2026-08-18T16:54:30.352133Z",
    }
    semantic_review = evidence["semanticReview"]
    assert semantic_review["status"] == "proposed"
    assert [mapping["sourcePath"] for mapping in semantic_review["mappings"]] == [
        "Form DAT!row 25 (Field # 1-17), Business Rules",
        "Form DAT!row 54 (Field # 2-17), Business Rules",
        "Form DAT!row 30 (Field # 1-22), Business Rules",
    ]
    assert {mapping["status"] for mapping in semantic_review["mappings"]} == {"proposed"}
    assert manifest["artifacts"]["targets/grants-gov-xml.json"] == "generated"
    assert projected.json_to_xml_schema is not None


def test_repeated_people_survive_add_edit_delete_before_persistence() -> None:
    response = copy.deepcopy(VALID_RESPONSE)

    response["senior_key_persons"].append(_person("Morgan", "Mentor"))
    response["senior_key_persons"][0]["department"] = "Biomedical Informatics"
    del response["senior_key_persons"][1]

    assert response["senior_key_persons"] == [
        {
            **_person("Casey", "Collaborator"),
            "department": "Biomedical Informatics",
            "biographical_sketch": KEY_PERSON_BIOGRAPHICAL_SKETCH,
            "current_pending_support": KEY_PERSON_CURRENT_SUPPORT,
        }
    ]
    assert_validation_case(
        "rr-key-person-expanded",
        ValidationCase("edited repeated person", response, frozenset()),
        attachment_ids=ATTACHMENT_IDS,
    )


def test_repeated_people_enforce_the_declared_99_person_limit() -> None:
    at_limit = copy.deepcopy(VALID_RESPONSE)
    at_limit["senior_key_persons"] = [
        _person(f"Person{index}", "Researcher") for index in range(99)
    ]
    assert_validation_case(
        "rr-key-person-expanded",
        ValidationCase("99 structured senior key people", at_limit, frozenset()),
        attachment_ids=ATTACHMENT_IDS,
    )

    over_limit = copy.deepcopy(at_limit)
    over_limit["senior_key_persons"].append(_person("Overflow", "Researcher"))
    assert_validation_case(
        "rr-key-person-expanded",
        ValidationCase(
            "100 structured senior key people",
            over_limit,
            frozenset({"$.senior_key_persons"}),
        ),
        attachment_ids=ATTACHMENT_IDS,
    )


def test_key_person_validation_covers_nested_and_conditional_requirements() -> None:
    missing_last_name = copy.deepcopy(VALID_RESPONSE)
    del missing_last_name["senior_key_persons"][0]["name"]["last_name"]
    assert_validation_case(
        "rr-key-person-expanded",
        ValidationCase(
            "repeated person missing a last name",
            missing_last_name,
            frozenset({"$.senior_key_persons[0].name.last_name"}),
        ),
        attachment_ids=ATTACHMENT_IDS,
    )

    other_role = copy.deepcopy(VALID_RESPONSE)
    other_role["senior_key_persons"][0]["project_role"] = "Other (Specify)"
    assert_validation_case(
        "rr-key-person-expanded",
        ValidationCase(
            "other role without its explanation",
            other_role,
            frozenset({"$.senior_key_persons[0].other_project_role"}),
        ),
        attachment_ids=ATTACHMENT_IDS,
    )
    other_role["senior_key_persons"][0]["other_project_role"] = "Data steward"
    assert_validation_case(
        "rr-key-person-expanded",
        ValidationCase("other role with its explanation", other_role, frozenset()),
        attachment_ids=ATTACHMENT_IDS,
    )


@pytest.mark.parametrize(
    ("unowned_attachment", "expected_path"),
    [
        (PI_BIOGRAPHICAL_SKETCH, "$.principal_investigator.biographical_sketch"),
        (PI_CURRENT_SUPPORT, "$.principal_investigator.current_pending_support"),
        (
            KEY_PERSON_BIOGRAPHICAL_SKETCH,
            "$.senior_key_persons[0].biographical_sketch",
        ),
        (
            KEY_PERSON_CURRENT_SUPPORT,
            "$.senior_key_persons[0].current_pending_support",
        ),
        (ADDITIONAL_PROFILES, "$.additional_profiles"),
        (ADDITIONAL_BIOGRAPHICAL_SKETCHES, "$.additional_biographical_sketches"),
        (ADDITIONAL_CURRENT_SUPPORT, "$.additional_current_pending_support"),
    ],
)
def test_each_nested_and_overflow_attachment_must_belong_to_the_application(
    unowned_attachment: str,
    expected_path: str,
) -> None:
    assert_validation_case(
        "rr-key-person-expanded",
        ValidationCase("all attachment references owned", VALID_RESPONSE, frozenset()),
        attachment_ids=ATTACHMENT_IDS,
    )
    assert_validation_case(
        "rr-key-person-expanded",
        ValidationCase(
            f"attachment {unowned_attachment} not owned",
            VALID_RESPONSE,
            frozenset({expected_path}),
        ),
        attachment_ids=ATTACHMENT_IDS - {unowned_attachment},
    )


def test_key_person_in_memory_submit_validation_accepts_a_valid_response() -> None:
    application_form = submit_form(
        "rr-key-person-expanded",
        VALID_RESPONSE,
        attachment_ids=ATTACHMENT_IDS,
    )

    assert application_form.application_response == VALID_RESPONSE
    assert application_form.form.form_instruction_id is None
