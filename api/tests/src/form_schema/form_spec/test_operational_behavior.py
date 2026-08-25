import copy
import uuid

import pytest

from src.form_schema.form_spec.loader import load_form
from src.form_schema.form_spec.operational_behavior import (
    ProjectedCanonicalValueSource,
    ProjectedExecutionPolicy,
    ProjectedOperationalBehavior,
    apply_operational_editability,
    project_operational_behavior,
)
from src.form_schema.form_spec.projection import Projection

RR_SF424_RUNTIME_ID = uuid.UUID("98f03cc4-5cd8-455b-a318-ba5abd0cf572")


@pytest.mark.parametrize("form_id", ["rr-budget", "rr-budget-10yr"])
def test_rr_budget_projects_exact_cross_form_prefill_coordinates(form_id: str) -> None:
    loaded = load_form(form_id)
    assert len(loaded.operational_behavior) == 3
    by_path = {record.canonical_path: record for record in loaded.operational_behavior}

    sam_uei = by_path["/samUei"]
    assert sam_uei.path == "/samuei"
    assert sam_uei.operation_kind == "prefill"
    assert sam_uei.editability == "editable"
    assert sam_uei.execution_policy == ProjectedExecutionPolicy(
        trigger="source-response-updated",
        write_policy="until-target-user-modified",
        missing_source_policy="skip",
    )
    assert sam_uei.value_source == ProjectedCanonicalValueSource(
        form_id="rr-sf424",
        runtime_form_id=RR_SF424_RUNTIME_ID,
        canonical_path="/applicantInfo/organizationInfo/samUei",
        path="/applicant_info/organization_info/sam_uei",
    )

    organization_name = by_path["/organizationName"]
    assert organization_name.path == "/organization_name"
    assert organization_name.editability == "unspecified"
    assert isinstance(organization_name.value_source, ProjectedCanonicalValueSource)
    assert (
        organization_name.value_source.path == "/applicant_info/organization_info/organization_name"
    )

    start_date = by_path["/budgetYear/[]/budgetPeriodStartDate"]
    assert start_date.path == "/budget_year/[]/budget_period_start_date"
    assert start_date.target_selection is not None
    assert start_date.target_selection.array_path == "/budget_year"
    assert start_date.target_selection.index == 0
    assert isinstance(start_date.value_source, ProjectedCanonicalValueSource)
    assert start_date.value_source.path == "/proposed_project_period/proposed_start_date"


def test_projection_rejects_an_unsupported_execution_policy() -> None:
    loaded = load_form("rr-budget")
    document = {
        "contract": "grants-form-operational-behavior/v1",
        "formId": "rr-budget",
        "behaviors": [
            {
                "canonicalPath": loaded.operational_behavior[0].canonical_path,
                "operationKind": "prefill",
                "valueSource": {
                    "kind": "canonical",
                    "blockId": "rr-sf424",
                    "path": "/answer",
                },
                "editability": "editable",
                "executionPolicy": {
                    "trigger": "form-opened",
                    "writePolicy": "until-target-user-modified",
                    "missingSourcePolicy": "skip",
                },
            }
        ],
    }

    with pytest.raises(ValueError, match="unsupported execution trigger"):
        project_operational_behavior(
            copy.deepcopy(document),
            form_id="rr-budget",
            target_projection=Projection(),
            projection_for=lambda _form_id: Projection(),
            runtime_form_id_for=lambda _form_id: RR_SF424_RUNTIME_ID,
        )


def test_projection_fails_closed_when_source_form_has_no_runtime_identity() -> None:
    document = {
        "contract": "grants-form-operational-behavior/v1",
        "formId": "target",
        "behaviors": [
            {
                "canonicalPath": "/answer",
                "operationKind": "prefill",
                "valueSource": {"kind": "canonical", "blockId": "source", "path": "/answer"},
                "editability": "editable",
                "executionPolicy": {
                    "trigger": "source-response-updated",
                    "writePolicy": "until-target-user-modified",
                    "missingSourcePolicy": "skip",
                },
            }
        ],
    }

    def missing_identity(_form_id: str) -> uuid.UUID:
        raise ValueError("missing runtime identity")

    with pytest.raises(ValueError, match="missing runtime identity"):
        project_operational_behavior(
            document,
            form_id="target",
            target_projection=Projection(),
            projection_for=lambda _form_id: Projection(),
            runtime_form_id_for=missing_identity,
        )


def test_operational_editability_protects_nested_and_repeating_targets() -> None:
    source = ProjectedCanonicalValueSource(
        form_id="source",
        runtime_form_id=RR_SF424_RUNTIME_ID,
        canonical_path="/source",
        path="/source",
    )
    policy = ProjectedExecutionPolicy(
        trigger="source-response-updated",
        write_policy="until-target-user-modified",
        missing_source_policy="skip",
    )
    behaviors = tuple(
        ProjectedOperationalBehavior(
            canonical_path=path,
            path=path,
            operation_kind="prefill",
            editability="protected",
            execution_policy=policy,
            value_source=source,
            target_selection=None,
        )
        for path in ("/person/name", "/people/[]/name")
    )
    schema = {
        "type": "object",
        "properties": {
            "person": {"type": "object", "properties": {"name": {"type": "string"}}},
            "people": {
                "type": "array",
                "items": {"type": "object", "properties": {"name": {"type": "string"}}},
            },
        },
    }

    projected = apply_operational_editability(schema, behaviors)

    assert projected["properties"]["person"]["properties"]["name"]["readOnly"] is True
    assert projected["properties"]["people"]["items"]["properties"]["name"]["readOnly"] is True
    assert "readOnly" not in schema["properties"]["person"]["properties"]["name"]


def test_operational_editability_does_not_bleed_across_resolver_aliases() -> None:
    behavior = ProjectedOperationalBehavior(
        canonical_path="/project_director/name",
        path="/project_director/name",
        operation_kind="prefill",
        editability="protected",
        execution_policy=ProjectedExecutionPolicy(
            trigger="source-response-updated",
            write_policy="until-target-user-modified",
            missing_source_policy="skip",
        ),
        value_source=ProjectedCanonicalValueSource(
            form_id="source",
            runtime_form_id=RR_SF424_RUNTIME_ID,
            canonical_path="/source",
            path="/source",
        ),
        target_selection=None,
    )
    shared_name = {"type": "string"}
    schema = {
        "type": "object",
        "properties": {
            "project_director": {
                "type": "object",
                "properties": {"name": shared_name},
            },
            "co_project_director": {
                "type": "object",
                "properties": {"name": shared_name},
            },
        },
    }

    projected = apply_operational_editability(schema, (behavior,))

    assert projected["properties"]["project_director"]["properties"]["name"]["readOnly"] is True
    assert "readOnly" not in projected["properties"]["co_project_director"]["properties"]["name"]
    assert "readOnly" not in shared_name


def test_operational_editability_traverses_composed_object_schemas() -> None:
    behavior = ProjectedOperationalBehavior(
        canonical_path="/person/name",
        path="/person/name",
        operation_kind="prefill",
        editability="protected",
        execution_policy=ProjectedExecutionPolicy(
            trigger="source-response-updated",
            write_policy="until-target-user-modified",
            missing_source_policy="skip",
        ),
        value_source=ProjectedCanonicalValueSource(
            form_id="source",
            runtime_form_id=RR_SF424_RUNTIME_ID,
            canonical_path="/source",
            path="/source",
        ),
        target_selection=None,
    )
    schema = {
        "type": "object",
        "properties": {
            "person": {
                "allOf": [
                    {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    }
                ]
            }
        },
    }

    projected = apply_operational_editability(schema, (behavior,))

    assert projected["properties"]["person"]["allOf"][0]["properties"]["name"] == {
        "type": "string",
        "readOnly": True,
    }


@pytest.mark.parametrize("keyword", ["allOf", "anyOf", "oneOf"])
def test_operational_editability_combines_direct_and_parallel_composed_paths(
    keyword: str,
) -> None:
    behavior = ProjectedOperationalBehavior(
        canonical_path="/person/name",
        path="/person/name",
        operation_kind="prefill",
        editability="protected",
        execution_policy=ProjectedExecutionPolicy(
            trigger="source-response-updated",
            write_policy="until-target-user-modified",
            missing_source_policy="skip",
        ),
        value_source=ProjectedCanonicalValueSource(
            form_id="source",
            runtime_form_id=RR_SF424_RUNTIME_ID,
            canonical_path="/source",
            path="/source",
        ),
        target_selection=None,
    )
    schema = {
        "type": "object",
        "properties": {"person": {"type": "object", "title": "Person"}},
        keyword: [
            {
                "properties": {
                    "person": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    }
                }
            }
        ],
    }

    projected = apply_operational_editability(schema, (behavior,))

    assert projected[keyword][0]["properties"]["person"]["properties"]["name"]["readOnly"] is True


def test_operational_editability_fails_closed_for_a_missing_target() -> None:
    behavior = ProjectedOperationalBehavior(
        canonical_path="/missing",
        path="/missing",
        operation_kind="prefill",
        editability="protected",
        execution_policy=ProjectedExecutionPolicy(
            trigger="source-response-updated",
            write_policy="until-target-user-modified",
            missing_source_policy="skip",
        ),
        value_source=ProjectedCanonicalValueSource(
            form_id="source",
            runtime_form_id=RR_SF424_RUNTIME_ID,
            canonical_path="/source",
            path="/source",
        ),
        target_selection=None,
    )

    with pytest.raises(ValueError, match="does not resolve in schema"):
        apply_operational_editability({"type": "object", "properties": {}}, (behavior,))
