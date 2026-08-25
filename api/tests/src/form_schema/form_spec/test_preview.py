from __future__ import annotations

import copy
import json

import pytest

from src.form_schema.form_spec.bank import ARTIFACT_MANIFEST
from src.form_schema.form_spec.loader import load_form
from src.form_schema.form_spec.preview import (
    BROWSER_FORM_IDS,
    PREVIEW_FLAG,
    banked_form_ids,
    build_preview_form,
    operational_behavior_for_preview_form_id,
    portable_id_for_preview_form_id,
    portable_preview_enabled,
    preview_form_id,
    preview_portable_forms,
    selected_browser_form_ids,
)
from src.form_schema.form_spec.runtime_identity import _records as runtime_identity_records
from src.form_schema.forms import _ALL_FORMS, _forms_for_registry
from src.form_schema.registry.form_template_registry import FormTemplateKey, FormTemplateRegistry


def test_preview_is_fail_closed() -> None:
    assert not portable_preview_enabled({})
    assert not portable_preview_enabled({PREVIEW_FLAG: "true"})
    assert not portable_preview_enabled({"ENVIRONMENT": "prod", PREVIEW_FLAG: "true"})
    assert not portable_preview_enabled({"ENVIRONMENT": "local", PREVIEW_FLAG: "false"})
    assert portable_preview_enabled({"ENVIRONMENT": "local", PREVIEW_FLAG: "true"})
    assert portable_preview_enabled({"ENVIRONMENT": "test", PREVIEW_FLAG: "1"})
    assert portable_preview_enabled({"ENVIRONMENT": "dev", PREVIEW_FLAG: "yes"})


def test_preview_discovers_manifest_selection_without_an_allowlist() -> None:
    manifest = json.loads(ARTIFACT_MANIFEST.read_text())
    assert banked_form_ids() == tuple(manifest["selection"]["forms"])


def test_browser_selection_defaults_to_the_complete_bank() -> None:
    assert selected_browser_form_ids({}) == banked_form_ids()


def test_browser_selection_accepts_a_bounded_ordered_subset() -> None:
    assert selected_browser_form_ids({BROWSER_FORM_IDS: "sf424,sf424-short"}) == (
        "sf424",
        "sf424-short",
    )


@pytest.mark.parametrize("value", ["sf424,", "sf424,sf424", "not-a-form"])
def test_browser_selection_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match=BROWSER_FORM_IDS):
        selected_browser_form_ids({BROWSER_FORM_IDS: value})


def test_preview_identity_is_stable_and_separate_from_runtime_identity() -> None:
    first = preview_form_id("sf424")
    assert first == preview_form_id("sf424")
    assert first != preview_form_id("sf424a")
    assert first != runtime_identity_records()["sf424"].form_id
    assert portable_id_for_preview_form_id(first) == "sf424"
    assert portable_id_for_preview_form_id(runtime_identity_records()["sf424"].form_id) is None


def test_preview_behavior_uses_the_banked_contract_without_runtime_identity() -> None:
    behaviors = operational_behavior_for_preview_form_id(preview_form_id("rr-budget"))

    assert behaviors
    assert (
        operational_behavior_for_preview_form_id(runtime_identity_records()["sf424"].form_id) == ()
    )


def test_every_banked_package_builds_as_a_preview_form() -> None:
    previews = preview_portable_forms()
    assert [form.short_form_name for form in previews] == [
        f"portable-preview-{form_id}" for form_id in banked_form_ids()
    ]
    assert len({form.form_id for form in previews}) == len(previews)
    assert all(form.form_json_schema for form in previews)
    assert all(form.form_ui_schema for form in previews)
    assert all(form.form_instruction_id is None for form in previews)
    assert all(form.form_type is None for form in previews)
    assert all(form.json_to_xml_schema is None for form in previews)
    normalization_policies = {
        form.short_form_name: form.response_normalization
        for form in previews
        if form.response_normalization is not None
    }
    assert set(normalization_policies) == {"portable-preview-sf424a"}
    assert {
        operation.path for operation in normalization_policies["portable-preview-sf424a"].operations
    } == {
        "/direct_charges_explanation",
        "/indirect_charges_explanation",
        "/remarks",
    }


@pytest.mark.parametrize(
    ("form_id", "referenced_field"),
    [("sf424", "submission_type"), ("sf424-short", "agency_name")],
)
def test_preview_adapter_expands_family_references_for_the_simpler_renderer(
    form_id: str, referenced_field: str
) -> None:
    preview = build_preview_form(form_id)
    serialized = json.dumps(preview.form_json_schema)

    assert '"$ref"' not in serialized
    assert preview.form_json_schema["properties"][referenced_field]["allOf"][0]["type"] == "string"


def test_banking_still_does_not_enable_the_production_loader() -> None:
    bank_only = next(
        form_id for form_id in banked_form_ids() if form_id not in runtime_identity_records()
    )
    with pytest.raises(ValueError, match="no SGG runtime identity"):
        load_form(bank_only)


def test_registry_adds_every_preview_only_after_explicit_lower_environment_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv(PREVIEW_FLAG, "true")
    assert _forms_for_registry() == _ALL_FORMS

    monkeypatch.setenv("ENVIRONMENT", "local")
    forms = _forms_for_registry()
    assert forms[: len(_ALL_FORMS)] == _ALL_FORMS
    preview_ids = {preview_form_id(form_id) for form_id in banked_form_ids()}
    assert {form.form_id for form in forms[len(_ALL_FORMS) :]} == preview_ids

    registry = FormTemplateRegistry()
    for form in forms:
        registry.register(copy.deepcopy(form), major_version=1)

    assert len(registry.get_all()) == len(forms)
    assert len({form.form_id for form in registry.get_all()}) == len(forms)
    assert {
        registry.get_by_id_and_major_version(FormTemplateKey(form_id, 1)).form_id
        for form_id in preview_ids
    } == preview_ids


def test_every_preview_passes_through_the_real_runtime_registry() -> None:
    registry = FormTemplateRegistry()
    previews = preview_portable_forms()
    for form in previews:
        registry.register(form, major_version=1)

    assert len(registry.get_all()) == len(banked_form_ids())
    for portable_id in banked_form_ids():
        form = registry.get_by_id_and_major_version(
            FormTemplateKey(preview_form_id(portable_id), 1)
        )
        assert form.form_json_schema.get("$ref") is None
