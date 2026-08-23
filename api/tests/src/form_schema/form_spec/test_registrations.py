from __future__ import annotations

import json

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.registrations import portable_form, registered_portable_forms
from src.form_schema.form_spec.runtime_identity import RUNTIME_IDENTITIES, runtime_identity

EXPECTED_REGISTERED_IDENTITIES = {
    "rr-budget": (
        "cfa593f7-e5ef-4ba8-82b2-c732ec65e461",
        "RRBudget",
        "1.0",
        "6c604b81-8582-4d39-b899-f3e15bbcd3ef",
    ),
    "rr-budget-10yr": (
        "2ae77c1c-58f7-41e7-9fb0-7a0823621758",
        "RRBudget10",
        "1.0",
        "6436c11c-0756-4806-885f-819d21ffe914",
    ),
    "rr-subaward-budget": (
        "67450974-a273-5bb8-86e5-b88d8a68c732",
        "RRSubawardBudget",
        "1.0",
        "b854f60f-d5e1-5146-8270-63fcbea3c7a1",
    ),
    "rr-subaward-budget-30": (
        "33ce5425-e8f1-422e-8fe0-e2337adbd56f",
        "RRSubawardBudget30",
        "1.0",
        "1bc60459-7d72-4964-9816-e965b2ba4aec",
    ),
    "rr-subaward-budget-10yr-30": (
        "8e208eec-a423-440b-9596-f71a33cec25f",
        "RRSubawardBudget10_30",
        "1.0",
        "f75a27cd-770b-41e9-bca8-ef0097201852",
    ),
}


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


def test_runtime_identity_target_covers_selected_forms_without_leaking_into_manifests():
    identity_document = json.loads(RUNTIME_IDENTITIES.read_text())
    artifact_document = json.loads((ARTIFACTS / "artifact-manifest.json").read_text())
    selected = artifact_document["selection"]["forms"]

    assert identity_document["contract"] == "sgg-form-runtime-identities/v1"
    assert set(identity_document["forms"]) == set(selected)
    assert len(identity_document["forms"]) == 19
    assert all(
        set(record) == {"formId", "formType", "sggVersion"}
        for record in identity_document["forms"].values()
    )
    for portable_id in selected:
        meta = json.loads((ARTIFACTS / "forms" / portable_id / "manifest.json").read_text())["form"]
        assert {"formId", "formType", "sggVersion"}.isdisjoint(meta)


def test_registered_forms_preserve_runtime_and_instruction_identity():
    registrations = json.loads(RUNTIME_IDENTITIES.with_name("registrations.json").read_text())[
        "forms"
    ]

    assert set(registrations) == set(EXPECTED_REGISTERED_IDENTITIES)
    for portable_id, (
        form_id,
        form_type,
        sgg_version,
        instruction_id,
    ) in EXPECTED_REGISTERED_IDENTITIES.items():
        identity = runtime_identity(portable_id)
        runtime_form = portable_form(portable_id)
        assert str(identity.form_id) == form_id
        assert identity.form_type == form_type
        assert identity.sgg_version == sgg_version
        assert str(runtime_form.form_id) == form_id
        assert runtime_form.form_type.value == form_type
        assert runtime_form.sgg_version == sgg_version
        assert str(runtime_form.form_instruction_id) == instruction_id
