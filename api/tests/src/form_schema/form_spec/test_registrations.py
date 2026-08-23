from __future__ import annotations

from src.form_schema.form_spec.registrations import portable_form, registered_portable_forms


def test_portable_registry_is_data_driven_and_preserves_declared_order():
    forms = registered_portable_forms()

    assert [form.short_form_name for form in forms] == [
        "RR_Budget_3_0",
        "RR_Budget10_3_0",
        "RR_SubawardBudget_3_0",
        "RR_SubawardBudget30_3_0",
        "RR_SubawardBudget10_30_3_0",
    ]
    assert len({form.form_id for form in forms}) == len(forms)


def test_compatibility_modules_share_the_registered_form_instance():
    from src.form_schema.forms.rr_budget import RRBudget_v3_0

    assert RRBudget_v3_0 is portable_form("rr-budget")
