"""Database-independent tests for portable initial cross-form population."""

import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.form_schema.form_spec.preview import preview_form_id
from src.form_schema.form_spec.runtime_identity import runtime_identity
from src.services.applications.apply_initial_population import (
    apply_initial_population_from_source_update,
)


def _session_with_modified_targets(*target_ids: uuid.UUID) -> Mock:
    session = Mock()
    session.execute.return_value.scalars.return_value.all.return_value = list(target_ids)
    return session


def _forms(
    source_response: dict,
    target_response: dict | None = None,
    *,
    target_form_id: str = "rr-budget",
) -> tuple[object, object]:
    source = SimpleNamespace(
        application_form_id=uuid.uuid4(),
        form_id=runtime_identity("rr-sf424").form_id,
        application_response=source_response,
    )
    target = SimpleNamespace(
        application_form_id=uuid.uuid4(),
        form_id=runtime_identity(target_form_id).form_id,
        application_response=target_response or {},
    )
    return source, target


@pytest.mark.parametrize("target_form_id", ["rr-budget", "rr-budget-10yr"])
def test_exact_source_values_populate_declared_budget_targets(target_form_id: str) -> None:
    source, target = _forms(
        {
            "applicant_info": {
                "organization_info": {
                    "sam_uei": "ABCDEFGHIJKL",
                    "organization_name": "Example Research University",
                }
            },
            "proposed_project_period": {"proposed_start_date": "2027-07-01"},
        },
        target_form_id=target_form_id,
    )
    application = SimpleNamespace(application_id=uuid.uuid4(), application_forms=[source, target])

    changed = apply_initial_population_from_source_update(
        _session_with_modified_targets(), application, source
    )

    assert changed == (target,)
    assert target.application_response == {
        "samuei": "ABCDEFGHIJKL",
        "organization_name": "Example Research University",
        "budget_year": [{"budget_period_start_date": "2027-07-01"}],
    }


def test_banked_preview_executes_the_same_operational_population_contract() -> None:
    source, target = _forms(
        {
            "applicant_info": {
                "organization_info": {
                    "sam_uei": "ABCDEFGHIJKL",
                    "organization_name": "Example Research University",
                }
            },
            "proposed_project_period": {"proposed_start_date": "2027-07-01"},
        }
    )
    target.form_id = preview_form_id("rr-budget")
    application = SimpleNamespace(application_id=uuid.uuid4(), application_forms=[source, target])

    changed = apply_initial_population_from_source_update(
        _session_with_modified_targets(), application, source
    )

    assert changed == (target,)
    assert target.application_response["samuei"] == "ABCDEFGHIJKL"


@pytest.mark.parametrize("target_form_id", ["rr-budget", "rr-budget-10yr"])
def test_missing_sources_are_skipped_and_modified_target_is_never_overwritten(
    target_form_id: str,
) -> None:
    source, target = _forms(
        {"applicant_info": {"organization_info": {"sam_uei": "ABCDEFGHIJKL"}}},
        {"organization_name": "Applicant-confirmed Organization"},
        target_form_id=target_form_id,
    )
    application = SimpleNamespace(application_id=uuid.uuid4(), application_forms=[source, target])

    changed = apply_initial_population_from_source_update(
        _session_with_modified_targets(target.application_form_id), application, source
    )

    assert changed == ()
    assert target.application_response == {"organization_name": "Applicant-confirmed Organization"}
