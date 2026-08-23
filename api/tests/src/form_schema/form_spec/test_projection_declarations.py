import json
from pathlib import Path

import pytest

from src.form_schema.form_spec import loader


def _write(root: Path, declaration: object) -> None:
    (root / "example.json").write_text(json.dumps(declaration))


def test_projection_rename_is_declared_with_a_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "PROJECTIONS", tmp_path)
    _write(
        tmp_path,
        {
            "renames": {
                "phone": {
                    "to": "phone_number",
                    "why": "The legacy payload uses a different field name.",
                }
            }
        },
    )

    assert loader._projection_for("example").renames == {"phone": "phone_number"}


def test_schema_annotation_is_declared_with_a_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "PROJECTIONS", tmp_path)
    _write(
        tmp_path,
        {
            "schemaAnnotations": {
                "submittedDate": {
                    "values": {"readOnly": True},
                    "why": "The legacy runtime exposes this annotation directly.",
                }
            }
        },
    )

    assert loader._projection_for("example").annotations == {"submittedDate": {"readOnly": True}}


def test_ui_identifier_is_declared_with_a_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "PROJECTIONS", tmp_path)
    _write(
        tmp_path,
        {
            "identifiers": {
                "legacySection": {
                    "to": "legacySection",
                    "why": "The existing component consumes this identifier.",
                }
            }
        },
    )

    assert loader._projection_for("example").identifiers == {"legacySection": "legacySection"}


def test_projection_profile_can_inherit_and_extend_an_existing_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "PROJECTIONS", tmp_path)
    (tmp_path / "base.json").write_text(
        json.dumps(
            {
                "renames": {
                    "phone": {
                        "to": "phone_number",
                        "why": "The legacy payload uses a different field name.",
                    }
                }
            }
        )
    )
    _write(
        tmp_path,
        {
            "extends": "base",
            "renames": {
                "email": {
                    "to": "email_address",
                    "why": "The derivative adds one legacy naming exception.",
                }
            },
        },
    )

    assert loader._projection_for("example").renames == {
        "phone": "phone_number",
        "email": "email_address",
    }


def test_projection_profile_rejects_inheritance_cycles(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "PROJECTIONS", tmp_path)
    (tmp_path / "example.json").write_text(json.dumps({"extends": "base"}))
    (tmp_path / "base.json").write_text(json.dumps({"extends": "example"}))

    with pytest.raises(ValueError, match="projection inheritance cycle"):
        loader._projection_for("example")


@pytest.mark.parametrize(
    "declaration",
    [
        {"renames": {"phone": "phone_number"}},
        {"renames": {"phone": {"to": "phone_number"}}},
        {"renames": {"phone": {"why": "Missing its target."}}},
    ],
)
def test_projection_rename_requires_target_and_reason(tmp_path, monkeypatch, declaration):
    monkeypatch.setattr(loader, "PROJECTIONS", tmp_path)
    _write(tmp_path, declaration)

    with pytest.raises(ValueError):
        loader._projection_for("example")
