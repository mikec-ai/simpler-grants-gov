import pytest

from src.form_schema.form_spec.projection import (
    Projection,
    project_response_pointer,
    project_rule_schema,
    project_schema,
    project_ui_schema,
)


def test_ui_paths_decode_fields_and_preserve_non_field_identifiers() -> None:
    projection = Projection(
        renames={
            "contact/info": "contacts",
            "contact/info.value~code": "legacy_value",
            "properties": "legacy_properties",
            "properties.childValue": "legacy_child",
        },
        identifiers={"sectionIdentity": "keptSectionIdentity"},
    )
    ui_schema = [
        {
            "type": "section",
            "name": "sectionIdentity",
            "label": "Contact",
            "children": [
                {
                    "type": "field",
                    "definition": (
                        "/properties/contact~1info/items/properties/value~0code/$defs/DoNotRename"
                    ),
                    "conditional": {
                        "when": {
                            "ref": {
                                "scope": "root",
                                "pointer": "/contact~1info/value~0code",
                            }
                        }
                    },
                },
                {
                    "type": "multiField",
                    "name": "ExistingWidgetName",
                    "widget": "ExistingWidgetName",
                    "definition": [
                        "/properties/contact~1info",
                        "/properties/properties/properties/childValue",
                    ],
                    "children": {
                        "columns": [{"columnHeader": "Value"}],
                        "rows": [
                            {
                                "cells": [
                                    {
                                        "type": "input",
                                        "definition": (
                                            "/properties/contact~1info/properties/value~0code"
                                        ),
                                    }
                                ]
                            }
                        ],
                    },
                },
            ],
        }
    ]

    projected = project_ui_schema(ui_schema, projection)

    assert projected[0]["name"] == "keptSectionIdentity"
    field = projected[0]["children"][0]
    assert field["definition"] == (
        "/properties/contacts/items/properties/legacy_value/$defs/DoNotRename"
    )
    assert field["conditional"]["when"]["ref"]["pointer"] == ("/contacts/legacy_value")
    widget = projected[0]["children"][1]
    assert widget["name"] == "ExistingWidgetName"
    assert widget["widget"] == "ExistingWidgetName"
    assert widget["definition"] == [
        "/properties/contacts",
        "/properties/legacy_properties/properties/legacy_child",
    ]
    assert widget["children"]["rows"][0]["cells"][0]["definition"] == (
        "/properties/contacts/properties/legacy_value"
    )


def test_rule_paths_share_exact_ancestry_across_relative_and_root_references() -> None:
    projection = Projection(
        renames={
            "outerItems": "outer_records",
            "outerItems.innerItems": "inner_records",
            "outerItems.innerItems.sourceValue": "legacy_source",
            "outerItems.parentValue": "legacy_parent",
        }
    )
    rules = {
        "outerItems": {
            "gg_type": "array",
            "innerItems": {
                "gg_type": "array",
                "resultValue": {
                    "gg_pre_population": {
                        "rule": "sum_monetary",
                        "fields": [
                            "@THIS.sourceValue",
                            "@PARENT.parentValue",
                            "outerItems[*].innerItems[*].sourceValue",
                            "outerItems[0].innerItems[1].sourceValue",
                        ],
                    }
                },
            },
        }
    }

    projected = project_rule_schema(rules, projection)
    calculation = projected["outer_records"]["inner_records"]["result_value"]["gg_pre_population"]

    assert calculation["rule"] == "sum_monetary"
    assert calculation["fields"] == [
        "@THIS.legacy_source",
        "@PARENT.legacy_parent",
        "outer_records[*].inner_records[*].legacy_source",
        "outer_records[0].inner_records[1].legacy_source",
    ]


def test_rule_paths_reject_multiple_array_selectors_on_one_segment() -> None:
    rules = {
        "resultValue": {
            "gg_pre_population": {
                "rule": "sum_monetary",
                "fields": ["outerItems[0][*].sourceValue"],
            }
        }
    }

    with pytest.raises(ValueError, match="at most one trailing"):
        project_rule_schema(rules, Projection())


@pytest.mark.parametrize("policy", ["unknown", "", None])
def test_rule_projection_rejects_unknown_materialization_policy(policy) -> None:
    rules = {
        "total": {
            "gg_pre_population": {
                "rule": "sum_monetary",
                "fields": ["amount"],
                "presence_fields": ["amount"],
                "materialize": policy,
            }
        }
    }

    with pytest.raises(ValueError, match="unknown calculation materialization policy"):
        project_rule_schema(rules, Projection())


def test_rule_projection_requires_presence_fields_for_conditional_materialization() -> None:
    rules = {
        "total": {
            "gg_pre_population": {
                "rule": "sum_monetary",
                "fields": ["amount"],
                "materialize": "when_any_source_present",
            }
        }
    }

    with pytest.raises(ValueError, match="requires non-empty string presence_fields"):
        project_rule_schema(rules, Projection())


def test_rule_projection_rejects_materialization_on_non_calculation_rule() -> None:
    rules = {
        "submitted_at": {
            "gg_pre_population": {
                "rule": "current_date",
                "presence_fields": ["signature"],
                "materialize": "when_any_source_present",
            }
        }
    }

    with pytest.raises(ValueError, match="requires a supported calculation rule"):
        project_rule_schema(rules, Projection())


def test_rule_projection_renames_percentage_operands_and_presence_fields() -> None:
    rules = {
        "fee": {
            "gg_pre_population": {
                "rule": "multiply_by_percentage",
                "amount": "directCost",
                "percentage": "feeRate",
                "presence_fields": ["directCost", "feeRate"],
                "materialize": "when_any_source_present",
            }
        }
    }

    projected = project_rule_schema(rules, Projection())

    assert projected["fee"]["gg_pre_population"] == {
        "rule": "multiply_by_percentage",
        "amount": "direct_cost",
        "percentage": "fee_rate",
        "presence_fields": ["direct_cost", "fee_rate"],
        "materialize": "when_any_source_present",
    }


@pytest.mark.parametrize(
    "rule",
    [
        {
            "rule": "sum_monetary",
            "presence_fields": ["amount"],
            "materialize": "when_any_source_present",
        },
        {
            "rule": "sum_integer",
            "fields": [],
            "presence_fields": ["count"],
            "materialize": "when_any_source_present",
        },
        {
            "rule": "subtract_monetary",
            "fields": [""],
            "presence_fields": ["amount"],
            "materialize": "when_any_source_present",
        },
    ],
)
def test_rule_projection_rejects_materialized_sum_with_malformed_fields(rule) -> None:
    with pytest.raises(ValueError, match="requires non-empty string fields"):
        project_rule_schema({"total": {"gg_pre_population": rule}}, Projection())


@pytest.mark.parametrize(
    "operands",
    [
        {},
        {"amount": "amount"},
        {"percentage": "percentage"},
        {"amount": "", "percentage": "percentage"},
        {"amount": "amount", "percentage": ""},
    ],
)
def test_rule_projection_rejects_materialized_percentage_with_malformed_operands(
    operands,
) -> None:
    rule = {
        "rule": "multiply_by_percentage",
        "presence_fields": ["amount", "percentage"],
        "materialize": "when_any_source_present",
        **operands,
    }

    with pytest.raises(ValueError, match="requires non-empty amount and percentage paths"):
        project_rule_schema({"fee": {"gg_pre_population": rule}}, Projection())


def test_response_pointer_uses_json_pointer_escaping_and_path_qualified_renames() -> None:
    projection = Projection(
        renames={
            "group/name": "legacy/group",
            "group/name.value~code": "legacy~value",
            "group/name.child/value": "legacy/child",
        }
    )

    assert (
        project_response_pointer("/group~1name/value~0code", projection)
        == "/legacy~1group/legacy~0value"
    )
    assert project_response_pointer("rootField.childField", projection) == ("rootField.childField")
    assert (
        project_response_pointer("/group~1name/12/child~1value", projection)
        == "/legacy~1group/12/legacy~1child"
    )


def test_nested_item_conditionals_use_field_list_ancestry_for_exact_renames() -> None:
    projection = Projection(
        renames={
            "outerItems": "outer_records",
            "outerItems.innerItems": "inner_records",
            "outerItems.innerItems.sourceValue": "legacy_source",
        }
    )
    ui_schema = [
        {
            "type": "fieldList",
            "name": "outerItems",
            "definition": "/properties/outerItems",
            "children": [
                {
                    "type": "fieldList",
                    "name": "innerItems",
                    "definition": "/properties/outerItems/items/properties/innerItems",
                    "children": [
                        {
                            "type": "field",
                            "definition": (
                                "/properties/outerItems/items/properties/innerItems/"
                                "items/properties/resultValue"
                            ),
                            "conditional": {
                                "when": {
                                    "op": "equals",
                                    "ref": {"scope": "item", "pointer": "/sourceValue"},
                                    "value": "yes",
                                },
                                "then": {"enabled": True},
                            },
                        }
                    ],
                }
            ],
        }
    ]

    projected = project_ui_schema(ui_schema, projection)
    inner = projected[0]["children"][0]
    conditional = inner["children"][0]["conditional"]

    assert inner["definition"] == "/properties/outer_records/items/properties/inner_records"
    assert inner["name"] == "inner_records"
    assert conditional["when"]["ref"]["pointer"] == "/legacy_source"


def test_pattern_property_regex_keys_are_not_projected_as_fields() -> None:
    schema = {
        "type": "object",
        "patternProperties": {
            "^x-[A-Z]+$": {
                "type": "object",
                "properties": {"childValue": {"type": "string"}},
            }
        },
    }
    projection = Projection(
        renames={
            "^x-[A-Z]+$": "must_not_replace_regex",
            "childValue": "legacy_child",
        }
    )

    projected = project_schema(schema, projection)

    assert list(projected["patternProperties"]) == ["^x-[A-Z]+$"]
    assert list(projected["patternProperties"]["^x-[A-Z]+$"]["properties"]) == ["legacy_child"]
