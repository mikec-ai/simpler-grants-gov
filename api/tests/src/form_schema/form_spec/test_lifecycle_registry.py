from __future__ import annotations

from typing import Any

import pytest

from src.form_schema.form_spec.loader import build_runtime_form
from src.form_schema.registry.form_template_registry import FormTemplateKey, form_template_registry
from tests.src.form_schema.form_spec.lifecycle import register_runtime_form_for_test


def test_failed_temporary_registration_restores_displaced_form(monkeypatch: Any) -> None:
    portable_form = build_runtime_form("sflll")
    key = FormTemplateKey(portable_form.form_id, 1)
    displaced = build_runtime_form("sflll")
    original = form_template_registry._registry.pop(key, None)
    form_template_registry._registry[key] = displaced

    def fail_registration(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("forced registration failure")

    monkeypatch.setattr(form_template_registry, "register", fail_registration)
    try:
        with pytest.raises(RuntimeError, match="forced registration failure"):
            register_runtime_form_for_test("sflll")
        assert form_template_registry._registry[key] is displaced
    finally:
        form_template_registry._registry.pop(key, None)
        if original is not None:
            form_template_registry._registry[key] = original
