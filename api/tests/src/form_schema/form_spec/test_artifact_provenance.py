import hashlib
import json

import pytest

from src.form_schema.form_spec.bank import (
    ARTIFACTS,
    ARTIFACT_MANIFEST,
    verify_artifact_selection,
    verify_artifacts,
)


def test_vendored_artifacts_match_the_pinned_form_spec_build():
    manifest = verify_artifacts()
    assert manifest["source"] == {
        "repository": "https://github.com/mikec-ai/grants-form-spec.git",
        "revision": "df40ac7acb07e54c2637894132eae5993d4e197b",
    }
    assert manifest["selection"]["forms"] == [
        "key-contacts",
        "sf424",
        "sf424a",
        "sf424-short",
        "project-narrative-attachments",
        "budget-narrative-attachments",
        "other-narrative-attachments",
    ]


def test_manifest_covers_every_vendored_json_artifact():
    manifest = json.loads(ARTIFACT_MANIFEST.read_text())
    expected = {str(record["path"]).removeprefix("dist/") for record in manifest["files"]}
    present = {
        str(path.relative_to(ARTIFACTS))
        for path in ARTIFACTS.rglob("*.json")
        if path != ARTIFACT_MANIFEST
    }
    assert present == expected


def test_changed_artifact_fails_closed(tmp_path):
    manifest = json.loads(ARTIFACT_MANIFEST.read_text())
    record = manifest["files"][0]
    relative = record["path"].removeprefix("dist/")
    source = ARTIFACTS / relative
    selected = tmp_path / "artifacts"
    changed = selected / relative
    changed.parent.mkdir(parents=True)
    payload = bytearray(source.read_bytes())
    payload[-2] ^= 1
    changed.write_bytes(payload)
    narrowed_manifest = {**manifest, "files": [record]}
    manifest_path = selected / "artifact-manifest.json"
    manifest_path.write_text(json.dumps(narrowed_manifest))

    assert hashlib.sha256(changed.read_bytes()).hexdigest() != record["sha256"]
    with pytest.raises(ValueError, match="artifact digest mismatch"):
        verify_artifact_selection(artifacts=selected, manifest_path=manifest_path)
