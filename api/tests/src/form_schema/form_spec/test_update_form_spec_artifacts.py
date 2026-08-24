from __future__ import annotations

import hashlib
import json
import subprocess

import pytest

from bin.update_form_spec_artifacts import (
    promotion_forms,
    provision_selected_xsds,
    resolve_revision,
    selected_forms,
)


def test_preserves_the_existing_selection_allowlist(tmp_path):
    target = tmp_path / "artifacts"
    target.mkdir()
    (target / "artifact-manifest.json").write_text(
        json.dumps(
            {
                "contract": "grants-form-artifact-selection/v1",
                "selection": {"forms": ["first", "second", "first"]},
            }
        )
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
        json.dumps(
            {
                "contract": "grants-form-artifact-selection/v1",
                "selection": {"forms": ["first", "second"]},
            }
        )
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
        json.dumps(
            {
                "contract": "grants-form-artifact-selection/v1",
                "selection": {"forms": ["first"]},
            }
        )
    )

    with pytest.raises(ValueError, match="cannot be combined"):
        promotion_forms(target, exact=["first"], add=["second"])


@pytest.mark.parametrize("invalid", ["", "../escape", "UPPER", "contains space", "trailing-"])
def test_rejects_invalid_additive_form_ids(tmp_path, invalid):
    target = tmp_path / "artifacts"
    target.mkdir()
    (target / "artifact-manifest.json").write_text(
        json.dumps(
            {
                "contract": "grants-form-artifact-selection/v1",
                "selection": {"forms": ["first"]},
            }
        )
    )

    with pytest.raises(ValueError, match="invalid form ids"):
        promotion_forms(target, add=[invalid])


def test_resolves_a_producer_ref_to_a_full_commit(tmp_path, monkeypatch):
    revision = "a" * 40

    def fake_run(command, **kwargs):
        assert command == [
            "git",
            "-C",
            str(tmp_path),
            "rev-parse",
            "--verify",
            "HEAD^{commit}",
        ]
        assert kwargs == {"check": True, "capture_output": True, "text": True}
        return subprocess.CompletedProcess(command, 0, stdout=f"{revision}\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert resolve_revision(tmp_path, "HEAD") == revision


def test_provisions_a_missing_xsd_from_the_pinned_producer_checkout(tmp_path):
    payload = b"<schema version='1.0'/>"
    digest = hashlib.sha256(payload).hexdigest()
    profile = json.dumps(
        {
            "xsd": {
                "uri": "https://apply.grants.gov/forms/Example-V1.0.xsd",
                "sha256": digest,
            }
        }
    ).encode()
    producer = tmp_path / "producer"
    fixture = producer / "tests/fixtures/grants-gov-xsd/example/Example-V1.0.xsd"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(payload)
    xsd_directory = tmp_path / "consumer-xsds"

    additions = provision_selected_xsds(
        {"forms/example/targets/grants-gov-xml.json": profile},
        producer=producer,
        xsd_directory=xsd_directory,
    )

    destination = xsd_directory / "Example-V1.0.xsd"
    assert additions == [destination]
    assert destination.read_bytes() == payload


def test_refuses_a_producer_fixture_that_does_not_match_the_declared_digest(tmp_path):
    profile = json.dumps(
        {
            "xsd": {
                "uri": "https://apply.grants.gov/forms/Example-V1.0.xsd",
                "sha256": hashlib.sha256(b"official").hexdigest(),
            }
        }
    ).encode()
    producer = tmp_path / "producer"
    fixture = producer / "tests/fixtures/grants-gov-xsd/example/Example-V1.0.xsd"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(b"different")

    with pytest.raises(ValueError, match="no matching official fixture"):
        provision_selected_xsds(
            {"forms/example/targets/grants-gov-xml.json": profile},
            producer=producer,
            xsd_directory=tmp_path / "consumer-xsds",
        )
