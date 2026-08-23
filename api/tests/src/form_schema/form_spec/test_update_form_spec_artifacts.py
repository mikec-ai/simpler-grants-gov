from __future__ import annotations

import json
import subprocess

import pytest

from bin.update_form_spec_artifacts import promotion_forms, resolve_revision, selected_forms


def test_preserves_the_existing_selection_allowlist(tmp_path):
    target = tmp_path / "artifacts"
    target.mkdir()
    (target / "artifact-manifest.json").write_text(
        json.dumps({
            "contract": "grants-form-artifact-selection/v1",
            "selection": {"forms": ["first", "second", "first"]},
        })
    )

    assert selected_forms(target) == ["first", "second"]


def test_rejects_a_target_without_a_selection_allowlist(tmp_path):
    target = tmp_path / "artifacts"
    target.mkdir()
    (target / "artifact-manifest.json").write_text("{}")

    with pytest.raises(ValueError, match="supported artifact selection"):
        selected_forms(target)


def test_additive_promotion_preserves_order_and_reports_only_new_forms(tmp_path):
    target = tmp_path / "artifacts"
    target.mkdir()
    (target / "artifact-manifest.json").write_text(
        json.dumps({
            "contract": "grants-form-artifact-selection/v1",
            "selection": {"forms": ["first", "second"]},
        })
    )

    forms, added = promotion_forms(
        target,
        add=["second", "third"],
        add_csv="fourth,third",
    )

    assert forms == ["first", "second", "third", "fourth"]
    assert added == ["third", "fourth"]


def test_exact_and_additive_selection_are_mutually_exclusive(tmp_path):
    target = tmp_path / "artifacts"
    target.mkdir()
    (target / "artifact-manifest.json").write_text(
        json.dumps({
            "contract": "grants-form-artifact-selection/v1",
            "selection": {"forms": ["first"]},
        })
    )

    with pytest.raises(ValueError, match="cannot be combined"):
        promotion_forms(target, exact=["first"], add=["second"])


@pytest.mark.parametrize("invalid", ["", "../escape", "UPPER", "contains space", "trailing-"])
def test_rejects_invalid_additive_form_ids(tmp_path, invalid):
    target = tmp_path / "artifacts"
    target.mkdir()
    (target / "artifact-manifest.json").write_text(
        json.dumps({
            "contract": "grants-form-artifact-selection/v1",
            "selection": {"forms": ["first"]},
        })
    )

    with pytest.raises(ValueError, match="invalid form ids"):
        promotion_forms(target, add=[invalid])


def test_resolves_a_producer_ref_to_a_full_commit(tmp_path):
    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True
    )
    (tmp_path / "tracked").write_text("test")
    subprocess.run(["git", "-C", str(tmp_path), "add", "tracked"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "--quiet", "-m", "test"], check=True)

    assert len(resolve_revision(tmp_path, "HEAD")) == 40
