import pytest

from src.form_schema.form_spec.preview import banked_form_ids, preview_form_id
from tests.lib.seed_local_db import _portable_preview_seed_forms


def test_portable_preview_seed_forms_follow_manifest_order() -> None:
    expected = list(banked_form_ids())
    forms_map = {
        f"portable-preview-{form_id}": type("FormStub", (), {"form_id": preview_form_id(form_id)})()
        for form_id in reversed(expected)
    }

    selected = _portable_preview_seed_forms(forms_map)

    assert [form.form_id for form in selected] == [preview_form_id(form_id) for form_id in expected]


def test_portable_preview_seed_forms_reject_missing_registration() -> None:
    expected = list(banked_form_ids())
    forms_map = {
        f"portable-preview-{form_id}": type("FormStub", (), {"form_id": preview_form_id(form_id)})()
        for form_id in expected[1:]
    }

    with pytest.raises(ValueError, match="missing selected forms"):
        _portable_preview_seed_forms(forms_map)
