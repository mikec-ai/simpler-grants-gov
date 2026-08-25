from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile

import pytest

from bin.sync_form_spec_artifacts import select_artifacts, verify_selected_xsds, write_selection


def _bundle(path, files, *, with_decision=True):
    governance = {
        "contract/v1/parity-delta-ledger.schema.json": b"{}",
        "parity/consumer-evidence-verification.v1.json": b"{}",
        "parity/legacy-deltas.v1.json": (
            b'{"decisionVerification":{"receipt":"parity/decision-verification.v1.json"}}'
            if with_decision
            else b"{}"
        ),
    }
    if with_decision:
        governance.update(
            {
                "contract/v1/parity-decision-artifact.schema.json": b"{}",
                "contract/v1/parity-decision-verification.schema.json": b"{}",
                "parity/decision-verification.v1.json": b'{"artifacts":[]}',
            }
        )
    files = {
        **governance,
        **files,
    }
    records = [
        {"path": name, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        for name, payload in sorted(files.items())
    ]
    manifest = {
        "contract": "grants-form-artifacts/v1",
        "source": {"repository": "example", "revision": "abc123"},
        "files": records,
    }
    entries = {"artifact-manifest.json": json.dumps(manifest).encode(), **files}
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for name, payload in entries.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))


def test_selects_only_runtime_files_and_transitive_questions(tmp_path):
    files = {
        "dist/forms/example/manifest.json": b'{"artifacts":{"operational-behavior.json":"generated","policy-binding.json":"generated","policy-content.json":"generated","response-normalization.json":{"origin":"passthrough","sha256":"abc"},"targets/grants-gov-xml.json":"generated"}}',
        "dist/forms/example/evidence.json": b"{}",
        "dist/forms/example/schema.json": b'{"$ref":"../../question-bank/a/schema.json"}',
        "dist/forms/example/sgg/rule-schema.json": b"{}",
        "dist/forms/example/sgg/ui-schema.json": b"[]",
        "dist/forms/example/ui.json": b"[]",
        "dist/forms/example/policy-binding.json": b"{}",
        "dist/forms/example/policy-content.json": b"{}",
        "dist/forms/example/operational-behavior.json": b"{}",
        "dist/forms/example/response-normalization.json": b"{}",
        "dist/forms/example/targets/grants-gov-xml.json": b"{}",
        "dist/question-bank/a/schema.json": b'{"$ref":"../b/schema.json"}',
        "dist/question-bank/b/schema.json": b'{"type":"string"}',
        "dist/question-bank/unrelated/schema.json": b'{"type":"string"}',
    }
    bundle = tmp_path / "bundle.tar.gz"
    _bundle(bundle, files)

    manifest, selected = select_artifacts(bundle, "example")

    assert set(selected) == {
        "forms/example/manifest.json",
        "forms/example/evidence.json",
        "forms/example/schema.json",
        "forms/example/sgg/rule-schema.json",
        "forms/example/sgg/ui-schema.json",
        "forms/example/policy-binding.json",
        "forms/example/policy-content.json",
        "forms/example/operational-behavior.json",
        "forms/example/response-normalization.json",
        "forms/example/targets/grants-gov-xml.json",
        "question-bank/a/schema.json",
        "question-bank/b/schema.json",
        "governance/contract/v1/parity-delta-ledger.schema.json",
        "governance/contract/v1/parity-decision-artifact.schema.json",
        "governance/contract/v1/parity-decision-verification.schema.json",
        "governance/parity/consumer-evidence-verification.v1.json",
        "governance/parity/decision-verification.v1.json",
        "governance/parity/legacy-deltas.v1.json",
    }
    assert manifest["source"]["revision"] == "abc123"
    assert manifest["selection"]["forms"] == ["example"]

    target = tmp_path / "artifacts"
    write_selection(target=target, manifest=manifest, files=selected)
    assert (target / "question-bank/b/schema.json").is_file()
    assert (target / "governance/parity/legacy-deltas.v1.json").is_file()
    assert not (target / "question-bank/unrelated/schema.json").exists()


def test_selects_every_offline_verified_decision_artifact(tmp_path):
    decision_path = "parity/decisions/example-acceptance.json"
    files = {
        "dist/forms/example/manifest.json": b"{}",
        "dist/forms/example/evidence.json": b"{}",
        "dist/forms/example/schema.json": b"{}",
        "dist/forms/example/sgg/rule-schema.json": b"{}",
        "dist/forms/example/sgg/ui-schema.json": b"[]",
        "parity/decision-verification.v1.json": json.dumps(
            {"artifacts": [{"path": decision_path}]}
        ).encode(),
        decision_path: b'{"decision":"accepted"}',
    }
    bundle = tmp_path / "bundle.tar.gz"
    _bundle(bundle, files)

    _, selected = select_artifacts(bundle, "example")

    assert f"governance/{decision_path}" in selected


def test_legacy_bundle_without_decision_contract_remains_selectable(tmp_path):
    files = {
        "dist/forms/example/manifest.json": b"{}",
        "dist/forms/example/evidence.json": b"{}",
        "dist/forms/example/schema.json": b"{}",
        "dist/forms/example/sgg/rule-schema.json": b"{}",
        "dist/forms/example/sgg/ui-schema.json": b"[]",
    }
    bundle = tmp_path / "legacy-bundle.tar.gz"
    _bundle(bundle, files, with_decision=False)

    manifest, selected = select_artifacts(bundle, "example")
    target = tmp_path / "legacy-selection"
    write_selection(target=target, manifest=manifest, files=selected)

    assert "governance/parity/legacy-deltas.v1.json" in selected
    assert "governance/parity/decision-verification.v1.json" not in selected
    assert "governance/contract/v1/parity-decision-artifact.schema.json" not in selected
    assert (target / "forms/example/schema.json").is_file()
    assert not (target / "governance/parity/decision-verification.v1.json").exists()


def test_rejects_decision_artifact_path_traversal_before_selection(tmp_path):
    malicious_path = "parity/decisions/../../../../../escaped.json"
    files = {
        "dist/forms/example/manifest.json": b"{}",
        "dist/forms/example/evidence.json": b"{}",
        "dist/forms/example/schema.json": b"{}",
        "dist/forms/example/sgg/rule-schema.json": b"{}",
        "dist/forms/example/sgg/ui-schema.json": b"[]",
        "parity/decision-verification.v1.json": json.dumps(
            {"artifacts": [{"path": malicious_path}]}
        ).encode(),
        malicious_path: b"{}",
    }
    bundle = tmp_path / "malicious-bundle.tar.gz"
    _bundle(bundle, files)

    with pytest.raises(ValueError, match="invalid artifact path"):
        select_artifacts(bundle, "example")


def test_write_selection_rejects_any_path_that_escapes_the_target(tmp_path):
    target = tmp_path / "artifacts"
    relative = "governance/parity/decisions/../../../../../escaped.json"

    with pytest.raises(ValueError, match="escapes the target"):
        write_selection(target=target, manifest={}, files={relative: b"tampered"})

    assert not (tmp_path / "escaped.json").exists()


def test_rejects_a_reference_outside_the_question_bank(tmp_path):
    files = {
        "dist/forms/example/manifest.json": b"{}",
        "dist/forms/example/evidence.json": b"{}",
        "dist/forms/example/schema.json": b'{"$ref":"../../../outside.json"}',
        "dist/forms/example/sgg/rule-schema.json": b"{}",
        "dist/forms/example/sgg/ui-schema.json": b"[]",
        "outside.json": b"{}",
    }
    bundle = tmp_path / "bundle.tar.gz"
    _bundle(bundle, files)

    with pytest.raises(ValueError, match="escapes the question bank"):
        select_artifacts(bundle, "example")


def test_selects_multiple_forms_and_deduplicates_their_shared_questions(tmp_path):
    files = {
        **{
            f"dist/forms/{form}/{name}": payload
            for form in ("first", "second")
            for name, payload in {
                "manifest.json": b"{}",
                "evidence.json": b"{}",
                "schema.json": b'{"$ref":"../../question-bank/shared/schema.json"}',
                "sgg/rule-schema.json": b"{}",
                "sgg/ui-schema.json": b"[]",
            }.items()
        },
        "dist/question-bank/shared/schema.json": b'{"type":"string"}',
    }
    bundle = tmp_path / "bundle.tar.gz"
    _bundle(bundle, files)

    manifest, selected = select_artifacts(bundle, ["first", "second", "first"])

    assert manifest["selection"]["forms"] == ["first", "second"]
    assert "forms/first/schema.json" in selected
    assert "forms/second/schema.json" in selected
    assert list(selected).count("question-bank/shared/schema.json") == 1
    assert "governance/parity/legacy-deltas.v1.json" in selected


def test_selected_xml_profiles_must_match_a_vendored_xsd(tmp_path):
    payload = b"<schema/>"
    digest = hashlib.sha256(payload).hexdigest()
    profile = json.dumps(
        {
            "xsd": {
                "uri": "https://apply.grants.gov/forms/Example-V1.0.xsd",
                "sha256": digest,
            }
        }
    ).encode()
    xsd_directory = tmp_path / "xsds"
    xsd_directory.mkdir()
    (xsd_directory / "Example-V1.0.xsd").write_bytes(payload)

    verify_selected_xsds(
        {"forms/example/targets/grants-gov-xml.json": profile},
        xsd_directory=xsd_directory,
    )
