from __future__ import annotations

import json

from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.registrations import portable_form, registered_portable_forms
from src.form_schema.form_spec.runtime_identity import RUNTIME_IDENTITIES, runtime_identity

EXPECTED_RUNTIME_IDENTITIES = {
    "budget-narrative-attachments": {
        "formId": "66092260-d3c2-4427-8fd2-bb14e1590aff",
        "formType": "BUDGET_NARRATIVE_ATTACHMENT",
        "sggVersion": "1.0",
    },
    "cd511": {
        "formId": "7057eaee-f043-4029-b7f2-c932f11ce900",
        "formType": "CD511",
        "sggVersion": "1.0",
    },
    "gg-lobbying": {
        "formId": "295d60a6-a3d1-4413-88fe-f4e5ee43b409",
        "formType": "GGLobbyingForm",
        "sggVersion": "1.0",
    },
    "key-contacts": {
        "formId": "f140c7db-724d-4954-bebd-081c0527908c",
        "formType": "KEY_CONTACTS",
        "sggVersion": "1.0",
    },
    "individual-sf424b": {
        "formId": "c34d48e7-92de-5cc4-8c25-ae347d40a55a",
        "formType": "SF424B",
        "sggVersion": "1.0",
    },
    "mandatory-sf424b": {
        "formId": "8842eb9b-5a66-5795-b30a-d0001a4928a4",
        "formType": "SF424B",
        "sggVersion": "1.0",
    },
    "other-narrative-attachments": {
        "formId": "8899954c-2919-4398-96aa-73961179fe16",
        "formType": "OTHER_NARRATIVE_ATTACHMENT",
        "sggVersion": "1.0",
    },
    "performance-site": {
        "formId": "3dac12c6-ef6f-573e-8958-fedd16b3a8d2",
        "formType": "PerformanceSite",
        "sggVersion": "1.0",
    },
    "phs398-modular-budget": {
        "formId": "885622d5-8122-5c9c-b15a-ba429fd458fe",
        "formType": "PHS398ModularBudget",
        "sggVersion": "1.0",
    },
    "project-abstract-summary": {
        "formId": "bf683068-23a4-43fa-ac7a-0f046b83cb14",
        "formType": "ProjectAbstractSummary",
        "sggVersion": "1.0",
    },
    "project-narrative-attachments": {
        "formId": "32165da2-354d-42c0-a986-cf4f2f350039",
        "formType": "PROJECT_NARRATIVE_ATTACHMENT",
        "sggVersion": "1.0",
    },
    "rr-budget": {
        "formId": "cfa593f7-e5ef-4ba8-82b2-c732ec65e461",
        "formType": "RRBudget",
        "sggVersion": "1.0",
    },
    "rr-budget-10yr": {
        "formId": "2ae77c1c-58f7-41e7-9fb0-7a0823621758",
        "formType": "RRBudget10",
        "sggVersion": "1.0",
    },
    "rr-key-person-expanded": {
        "formId": "2a638e46-7680-55ba-a11a-4d152f37ca1e",
        "formType": "RRKeyPersonExpanded",
        "sggVersion": "1.0",
    },
    "rr-other-project-information": {
        "formId": "c1559671-bd72-51e5-9a58-2101b4c654d0",
        "formType": "RROtherProjectInfo",
        "sggVersion": "1.0",
    },
    "rr-sf424": {
        "formId": "98f03cc4-5cd8-455b-a318-ba5abd0cf572",
        "formType": "RRSF424",
        "sggVersion": "1.0",
    },
    "rr-sf424-multi-project-cover": {
        "formId": "6d1fcf04-63e9-5951-841f-8ff06071f40c",
        "formType": "RRSF424MPCover",
        "sggVersion": "1.0",
    },
    "rr-subaward-budget": {
        "formId": "67450974-a273-5bb8-86e5-b88d8a68c732",
        "formType": "RRSubawardBudget",
        "sggVersion": "1.0",
    },
    "rr-subaward-budget-10yr-30": {
        "formId": "8e208eec-a423-440b-9596-f71a33cec25f",
        "formType": "RRSubawardBudget10_30",
        "sggVersion": "1.0",
    },
    "rr-subaward-budget-30": {
        "formId": "33ce5425-e8f1-422e-8fe0-e2337adbd56f",
        "formType": "RRSubawardBudget30",
        "sggVersion": "1.0",
    },
    "sf424": {
        "formId": "1623b310-85be-496a-b84b-34bdee22a68a",
        "formType": "SF424",
        "sggVersion": "1.0",
    },
    "sf424-short": {
        "formId": "cf355a4d-d840-43fd-a78f-729edf41ab4c",
        "formType": "SF424_SHORT",
        "sggVersion": "1.0",
    },
    "sf424a": {
        "formId": "08e6603f-d197-4a60-98cd-d49acb1fc1fd",
        "formType": "SF424A",
        "sggVersion": "1.0",
    },
    "sf424b": {
        "formId": "1d0681f8-26f9-4ff1-a75e-e33477668f73",
        "formType": "SF424B",
        "sggVersion": "1.0",
    },
    "sflll": {
        "formId": "778a1485-082a-463e-a61b-6615ccebe027",
        "formType": "SFLLL",
        "sggVersion": "1.0",
    },
}

EXPECTED_REGISTRATIONS = {
    "rr-budget": "6c604b81-8582-4d39-b899-f3e15bbcd3ef",
    "rr-budget-10yr": "6436c11c-0756-4806-885f-819d21ffe914",
    "rr-subaward-budget": "b854f60f-d5e1-5146-8270-63fcbea3c7a1",
    "rr-subaward-budget-30": "1bc60459-7d72-4964-9816-e965b2ba4aec",
    "rr-subaward-budget-10yr-30": "f75a27cd-770b-41e9-bca8-ef0097201852",
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
    assert identity_document["forms"] == EXPECTED_RUNTIME_IDENTITIES
    assert set(EXPECTED_RUNTIME_IDENTITIES) == set(selected)
    for portable_id in selected:
        meta = json.loads((ARTIFACTS / "forms" / portable_id / "manifest.json").read_text())["form"]
        assert {"formId", "formType", "sggVersion"}.isdisjoint(meta)


def test_registered_forms_preserve_runtime_and_instruction_identity():
    registrations = json.loads(RUNTIME_IDENTITIES.with_name("registrations.json").read_text())[
        "forms"
    ]

    assert registrations == {
        portable_id: {"formInstructionId": instruction_id}
        for portable_id, instruction_id in EXPECTED_REGISTRATIONS.items()
    }
    for portable_id, instruction_id in EXPECTED_REGISTRATIONS.items():
        expected_identity = EXPECTED_RUNTIME_IDENTITIES[portable_id]
        identity = runtime_identity(portable_id)
        runtime_form = portable_form(portable_id)
        assert str(identity.form_id) == expected_identity["formId"]
        assert identity.form_type == expected_identity["formType"]
        assert identity.sgg_version == expected_identity["sggVersion"]
        assert str(runtime_form.form_id) == expected_identity["formId"]
        assert runtime_form.form_type.value == expected_identity["formType"]
        assert runtime_form.sgg_version == expected_identity["sggVersion"]
        assert str(runtime_form.form_instruction_id) == instruction_id
