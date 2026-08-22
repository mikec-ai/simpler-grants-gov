from src.form_schema.form_spec.projection import Projection, project_schema


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
