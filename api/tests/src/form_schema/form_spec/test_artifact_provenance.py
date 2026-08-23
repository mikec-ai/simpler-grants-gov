import hashlib
import json
import re

import pytest

from src.form_schema.form_spec.bank import (
    ARTIFACT_MANIFEST,
    ARTIFACTS,
    verify_artifact_selection,
    verify_artifacts,
)


def test_vendored_artifacts_match_the_pinned_form_spec_build():
    manifest = verify_artifacts()
    assert manifest["source"]["repository"] == "https://github.com/mikec-ai/grants-form-spec.git"
    assert re.fullmatch(r"[0-9a-f]{40}", manifest["source"]["revision"])
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["sourceBundleSha256"])
    assert manifest["selection"]["forms"] == [
        "key-contacts",
        "sf424",
        "sf424a",
        "sf424-short",
        "project-narrative-attachments",
        "budget-narrative-attachments",
        "other-narrative-attachments",
        "rr-budget",
        "rr-budget-10yr",
        "rr-subaward-budget",
        "rr-subaward-budget-30",
        "rr-subaward-budget-10yr-30",
        "project-abstract-summary",
        "rr-sf424",
        "rr-sf424-multi-project-cover",
        "rr-key-person-expanded",
        "performance-site",
        "rr-other-project-information",
        "phs398-modular-budget",
        "sflll",
        "cd511",
        "gg-lobbying",
        "sf424b",
        "mandatory-sf424b",
        "individual-sf424b",
        "sf424d",
        "mandatory-sf424d",
        "individual-sf424d",
        "sf424c",
        "phs-assignment-request",
        "attachment-form",
        "rr-sf424b",
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


@pytest.mark.parametrize(
    "form_id,inherited_from,mount_prefix",
    [
        ("rr-budget", None, ""),
        ("rr-budget-10yr", "rr-budget", ""),
        ("rr-subaward-budget", "rr-budget", "budgetAttachments[*]."),
        ("rr-subaward-budget-30", "rr-budget", "budgetAttachments[*]."),
        ("rr-subaward-budget-10yr-30", "rr-budget", "budgetAttachments[*]."),
    ],
)
def test_budget_family_behavior_evidence_pins_exact_f770_records(
    form_id, inherited_from, mount_prefix
):
    evidence = json.loads((ARTIFACTS / "forms" / form_id / "evidence.json").read_text())
    records = evidence["behaviorEvidence"]
    root = json.loads((ARTIFACTS / "forms" / "rr-budget" / "evidence.json").read_text())
    source_records = [record for record in records if record["authority"] == "official_source"]
    unresolved_records = [record for record in records if record["authority"] == "unresolved"]

    assert len(records) == 56
    assert len(source_records) == 20
    assert len(unresolved_records) == 36
    assert {record["sourceId"] for record in source_records} == {"grantsgov-rr-budget-dat-3.0-f770"}
    assert len({record["sourceRecord"] for record in source_records}) == 20
    assert {record["canonicalPath"] for record in records} == {
        f"{mount_prefix}{record['canonicalPath']}" for record in root["behaviorEvidence"]
    }
    assert all(record["sourcePath"] for record in source_records)
    assert all(record["owner"] == "form-semantic-review" for record in unresolved_records)
    if inherited_from is None:
        assert all("inheritedFrom" not in record for record in records)
    else:
        assert {record["inheritedFrom"] for record in records} == {inherited_from}
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}


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
