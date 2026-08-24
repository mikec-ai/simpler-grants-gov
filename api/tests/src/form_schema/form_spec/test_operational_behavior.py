import copy
import uuid

import pytest

from src.form_schema.form_spec.loader import load_form
from src.form_schema.form_spec.operational_behavior import (
    ProjectedCanonicalValueSource,
    ProjectedExecutionPolicy,
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
