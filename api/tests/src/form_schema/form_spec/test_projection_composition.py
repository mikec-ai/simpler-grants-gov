import json

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.projection import Projection, project_schema, project_ui_schema


def test_project_schema_preserves_source_enum_while_adapting_runtime_spelling() -> None:
    source = ARTIFACTS / "question-bank" / "generics" / "address" / "schema.json"
    canonical = json.loads(source.read_text())

    projected = project_schema(canonical, Projection())

    assert "CIV: CÔTE D’IVOIRE" in canonical["$defs"]["CountryCode"]["enum"]
    assert "CIV: CÔTE D'IVOIRE" in projected["$defs"]["CountryCode"]["enum"]
    assert "CIV: CÔTE D’IVOIRE" not in projected["$defs"]["CountryCode"]["enum"]


def test_object_composition_rebases_local_definitions_to_the_shared_bank() -> None:
    ref = "../../question-bank/budget/example/schema.json"
    projection = Projection(
        bank_uri="https://example.test/question-bank.json",
        block_ids={"question-bank/budget/example/schema.json": "budget/example"},
        blocks={
            "budget/example": {
                "type": "object",
                "properties": {"amount": {"$ref": "#/$defs/Amount"}},
                "$defs": {"Amount": {"type": "string"}},
            }
        },
    )
    form = {
        "type": "object",
        "allOf": [{"$ref": ref}],
        "properties": {"note": {"type": "string"}},
    }

    projected = project_schema(form, projection)

    assert "$defs" not in projected
    assert projected["properties"]["amount"] == {
        "$ref": "https://example.test/question-bank.json#/$defs/Amount"
    }
    assert projected["properties"]["note"] == {"type": "string"}


def test_object_composition_deep_merges_a_nested_annotation() -> None:
    ref = "../../question-bank/budget/period/schema.json"
    projection = Projection(
        bank_uri="https://example.test/question-bank.json",
        block_ids={"question-bank/budget/period/schema.json": "budget/period"},
        blocks={
            "budget/period": {
                "type": "object",
                "properties": {
                    "equipment": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "total": {"type": "string"},
                        },
                    }
                },
            }
        },
    )
    form = {
        "type": "object",
        "allOf": [{"$ref": ref}],
        "properties": {"equipment": {"properties": {"total": {"readOnly": True}}}},
    }

    projected = project_schema(form, projection)

    assert projected["properties"]["equipment"] == {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "total": {"type": "string", "readOnly": True},
        },
    }


def test_nested_overlay_preserves_a_hoisted_definition() -> None:
    ref = "../../question-bank/budget/period/schema.json"
    projection = Projection(
        bank_uri="https://example.test/question-bank.json",
        block_ids={"question-bank/budget/period/schema.json": "budget/period"},
        blocks={
            "budget/period": {
                "type": "object",
                "properties": {
                    "people": {
                        "type": "array",
                        "items": {"$ref": "#/$defs/Person"},
                    }
                },
                "$defs": {
                    "Person": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "amount": {"type": "string", "pattern": "^[0-9]+$"},
                        },
                    }
                },
            }
        },
    )
    form = {
        "type": "object",
        "allOf": [{"$ref": ref}],
        "properties": {"people": {"items": {"properties": {"amount": {"readOnly": True}}}}},
    }

    projected = project_schema(form, projection)

    assert projected["properties"]["people"]["items"] == {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "amount": {
                "type": "string",
                "pattern": "^[0-9]+$",
                "readOnly": True,
            },
        },
    }


def test_ui_condition_projects_only_the_data_pointer() -> None:
    projected = project_ui_schema(
        {
            "type": "field",
            "definition": "/properties/applicantType/properties/otherExplanation",
            "conditional": {
                "when": {
                    "op": "equals",
                    "ref": {
                        "scope": "root",
                        "pointer": "/applicantType/applicantTypeCode",
                    },
                    "value": "X: Other (specify)",
                },
                "then": {"visible": True},
                "otherwise": {"visible": False},
            },
        },
        Projection(),
    )

    assert projected["definition"] == ("/properties/applicant_type/properties/other_explanation")
    assert projected["conditional"] == {
        "when": {
            "op": "equals",
            "ref": {
                "scope": "root",
                "pointer": "/applicant_type/applicant_type_code",
            },
            "value": "X: Other (specify)",
        },
        "then": {"visible": True},
        "otherwise": {"visible": False},
    }


def test_ui_condition_projects_every_ref_inside_presence_disjunction() -> None:
    projected = project_ui_schema(
        {
            "type": "field",
            "definition": "/properties/additionalProfiles",
            "conditional": {
                "when": {
                    "op": "any",
                    "predicates": [
                        {
                            "op": "countAtLeast",
                            "ref": {"scope": "root", "pointer": "/seniorKeyPersons"},
                            "minimum": 99,
                        },
                        {
                            "op": "present",
                            "ref": {"scope": "root", "pointer": "/additionalProfiles"},
                        },
                    ],
                },
                "then": {"interaction": "enabled"},
                "otherwise": {"interaction": "disabled"},
            },
        },
        Projection(
            renames={
                "seniorKeyPersons": "senior_key_persons",
                "additionalProfiles": "additional_profiles",
            }
        ),
    )

    assert projected["definition"] == "/properties/additional_profiles"
    assert projected["conditional"]["when"] == {
        "op": "any",
        "predicates": [
            {
                "op": "countAtLeast",
                "ref": {"scope": "root", "pointer": "/senior_key_persons"},
                "minimum": 99,
            },
            {
                "op": "present",
                "ref": {"scope": "root", "pointer": "/additional_profiles"},
            },
        ],
    }
