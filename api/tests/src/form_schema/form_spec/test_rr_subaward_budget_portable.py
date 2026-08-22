"""R&R Subaward Budget 3.0 must remain a source-bound portable form package."""

import copy
import json
from pathlib import Path
from typing import Any, cast

from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms.rr_subaward_budget import RRSubawardBudget_v3_0
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from tests.src.form_schema.form_spec.parity import pointers, rendered_field

ARTIFACTS = Path("src/form_schema/form_spec/artifacts/forms/rr-subaward-budget")


def _objects(node: Any) -> list[dict[str, Any]]:
    if isinstance(node, dict):
        return [node, *[item for value in node.values() for item in _objects(value)]]
    if isinstance(node, list):
        return [item for value in node for item in _objects(value)]
    return []


def test_runtime_identity_comes_from_the_portable_manifest() -> None:
    loaded = load_form("rr-subaward-budget")

    assert loaded.meta == {
        "id": "rr-subaward-budget",
        "formId": "67450974-a273-5bb8-86e5-b88d8a68c732",
        "legacyFormId": 776,
        "formName": "[Draft] R&R Subaward Budget Attachment(s) Form",
        "shortFormName": "RR_SubawardBudget_3_0",
        "formVersion": "3.0",
        "agencyCode": "GRANTS_GOV",
        "ombNumber": "4040-0001",
        "formType": "RRSubawardBudget",
        "sggVersion": "1.0",
    }
    assert RRSubawardBudget_v3_0.form_type is FormType.RR_SUBAWARD_BUDGET
    assert resolve_jsonschema(
        copy.deepcopy(RRSubawardBudget_v3_0.form_json_schema)
    ) == resolve_jsonschema(copy.deepcopy(loaded.form_json_schema))
    assert cast(Any, RRSubawardBudget_v3_0.form_ui_schema) == loaded.form_ui_schema
    assert RRSubawardBudget_v3_0.form_rule_schema == loaded.form_rule_schema


def test_every_rendered_pointer_resolves_through_the_shared_bank() -> None:
    schema = resolve_jsonschema(copy.deepcopy(RRSubawardBudget_v3_0.form_json_schema))
    ui_pointers = pointers(RRSubawardBudget_v3_0.form_ui_schema)

    assert len(ui_pointers) == 163
    assert len(set(ui_pointers)) == len(ui_pointers)
    assert all(rendered_field(schema, pointer) is not None for pointer in ui_pointers)


def test_nested_repeating_groups_and_rules_are_projected_generically() -> None:
    ui_objects = _objects(RRSubawardBudget_v3_0.form_ui_schema)
    rule_objects = _objects(RRSubawardBudget_v3_0.form_rule_schema)
    calculations = [
        node["gg_pre_population"] for node in rule_objects if "gg_pre_population" in node
    ]

    assert sum(node.get("type") == "fieldList" for node in ui_objects) == 6
    assert len(calculations) == 30
    raw_rules = json.loads((ARTIFACTS / "sgg" / "rule-schema.json").read_text())
    assert "@PARENT." in json.dumps(raw_rules)
    assert sorted(rule["order"] for rule in calculations) == list(range(1, 31))


def test_official_xsd_and_dat_provenance_are_pinned() -> None:
    evidence = json.loads((ARTIFACTS / "evidence.json").read_text())

    assert [(source["type"], source["sha256"]) for source in evidence["sources"]] == [
        ("xsd", "e1ea95403a58ef1ade290952de3531c73e015308ca7aee6b426d4a9bcb794510"),
        ("dat", "4eab979aa62d4a4e79da6ee536140da7b76545a8fc20a9897c1c13527b3c56fd"),
    ]
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}
