from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.form_schema.form_spec.differential import (
    COHORT_PATH,
    CONTRACT,
    LEDGER_PATH,
    LEDGER_SCHEMA_PATH,
    Difference,
    _dimension,
    _load_cohort,
    _load_delta_ledger,
    compare_cohort,
)

EXPECTED_FORMS = [
    "sf424",
    "sf424-short",
    "sf424a",
    "key-contacts",
    "project-abstract-summary",
    "project-narrative-attachments",
    "sf424b",
]
TEST_REVISION = "1" * 40
ARTIFACT_MANIFEST = LEDGER_PATH.parents[2] / "artifact-manifest.json"
RECEIPT_SOURCE_PATH = "parity/consumer-evidence-verification.v1.json"
RECEIPT_PATH = LEDGER_PATH.with_name("consumer-evidence-verification.v1.json")


def _write_fixture_bundle(
    tmp_path: Path,
    *,
    ledger: dict | None = None,
    receipt: dict | None = None,
) -> tuple[Path, Path, Path]:
    ledger_path = tmp_path / "ledger.json"
    receipt_path = tmp_path / "receipt.json"
    manifest_path = tmp_path / "manifest.json"
    payloads = {
        "parity/legacy-deltas.v1.json": (
            json.dumps(ledger or json.loads(LEDGER_PATH.read_text())) + "\n"
        ).encode(),
        RECEIPT_SOURCE_PATH: (
            json.dumps(receipt or json.loads(RECEIPT_PATH.read_text())) + "\n"
        ).encode(),
    }
    ledger_path.write_bytes(payloads["parity/legacy-deltas.v1.json"])
    receipt_path.write_bytes(payloads[RECEIPT_SOURCE_PATH])
    manifest = json.loads(ARTIFACT_MANIFEST.read_text())
    for record in manifest["files"]:
        payload = payloads.get(record["path"])
        if payload is not None:
            record.update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    manifest_path.write_text(json.dumps(manifest))
    return ledger_path, receipt_path, manifest_path


@pytest.fixture(scope="module")
def receipts() -> list[dict]:
    return compare_cohort(consumer_revision=TEST_REVISION)


def test_uniform_cohort_has_seven_comparison_gated_receipts(receipts: list[dict]) -> None:
    assert [receipt["portableFormId"] for receipt in receipts] == EXPECTED_FORMS
    assert all(receipt["contract"] == CONTRACT for receipt in receipts)
    assert sum(receipt["comparisonGate"] for receipt in receipts) == 1
    assert all("releaseGate" not in receipt for receipt in receipts)
    assert all(receipt["source"]["revision"] == TEST_REVISION for receipt in receipts)
    assert len({receipt["source"]["cohortSha256"] for receipt in receipts}) == 1

    for receipt in receipts:
        assert set(receipt["dimensions"]) == {"schema", "ui", "validation", "rules"}
        assert receipt["unsupportedDimensions"]["xml"]["status"] == "unavailable"
        assert receipt["unsupportedDimensions"]["ruleOutcomes"]["status"] == "unavailable"
        assert receipt["unsupportedDimensions"]["runtimeLifecycle"]["status"] == "unavailable"
        assert all(
            dimension["status"]
            in {"parity", "reviewed_delta", "proposed_delta", "unresolved", "not_applicable"}
            for dimension in receipt["dimensions"].values()
        )


def test_exact_parity_is_distinct_from_proposed_delta_and_not_applicable(
    receipts: list[dict],
) -> None:
    by_form = {receipt["portableFormId"]: receipt for receipt in receipts}
    assert {
        dimension: result["status"]
        for dimension, result in by_form["project-narrative-attachments"]["dimensions"].items()
    } == {"schema": "parity", "ui": "parity", "validation": "parity", "rules": "parity"}
    assert by_form["key-contacts"]["dimensions"]["rules"]["status"] == "not_applicable"
    assert by_form["sf424b"]["dimensions"]["schema"]["status"] == "proposed_delta"
    assert not by_form["sf424b"]["comparisonGate"]


def test_cohort_contains_only_oracle_selection_not_delta_decisions() -> None:
    cohort = _load_cohort(COHORT_PATH)
    assert all("intentionalDeltas" not in form for form in cohort["forms"])


def test_undocumented_differences_and_stale_allowances_fail_closed() -> None:
    unexpected = _dimension([Difference("/field#type", "string", "number")], {})
    declaration = {
        "id": "example",
        "classification": "unclassified",
        "review": {"status": "proposed", "decisionEvidence": []},
    }
    stale = _dimension(
        [],
        {"/field#type": declaration},
    )

    assert unexpected["status"] == "failed"
    assert unexpected["unexpected"][0]["key"] == "/field#type"
    assert stale["status"] == "failed"
    assert stale["staleAllowances"] == ["/field#type"]


def test_mechanically_bounded_proposal_never_counts_as_reviewed() -> None:
    declaration = {
        "id": "example",
        "classification": "authoritative_source_correction",
        "sourceSupport": {"status": "verified", "evidenceReferences": [{"id": "source"}]},
        "review": {"status": "proposed", "decisionEvidence": []},
    }
    result = _dimension(
        [Difference("/field#type", "string", "number")], {"/field#type": declaration}
    )

    assert result["status"] == "proposed_delta"


def test_only_accepted_review_can_produce_reviewed_delta() -> None:
    declaration = {
        "id": "example",
        "classification": "approved_incompatibility",
        "review": {
            "status": "accepted",
            "reviewer": "accountable-reviewer",
            "reviewedAt": "2026-08-24T12:00:00Z",
            "decisionEvidence": [{"id": "decision"}],
        },
    }
    result = _dimension(
        [Difference("/field#type", "string", "number")], {"/field#type": declaration}
    )

    assert result["status"] == "reviewed_delta"


def test_ledger_digest_and_review_contract_fail_closed(tmp_path: Path) -> None:
    tampered = tmp_path / "tampered.json"
    tampered.write_bytes(LEDGER_PATH.read_bytes() + b" ")
    with pytest.raises(ValueError, match="does not match its pinned producer artifact"):
        _load_delta_ledger(tampered)

    ledger = json.loads(LEDGER_PATH.read_text())
    ledger["records"][0]["review"] = {
        "status": "accepted",
        "reviewer": "accountable-reviewer",
        "reviewedAt": "2026-08-24T12:00:00Z",
        "decisionEvidence": [ledger["records"][0]["evidenceReferences"][0]],
    }
    invalid = tmp_path / "invalid.json"
    payload = (json.dumps(ledger) + "\n").encode()
    invalid.write_bytes(payload)
    manifest = json.loads((LEDGER_PATH.parents[2] / "artifact-manifest.json").read_text())
    ledger_record = next(
        row for row in manifest["files"] if row["path"] == "parity/legacy-deltas.v1.json"
    )
    ledger_record.update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="contract failed"):
        _load_delta_ledger(
            invalid,
            manifest_path=manifest_path,
            schema_path=LEDGER_SCHEMA_PATH,
        )


def test_ledger_is_validated_against_the_vendored_schema(tmp_path: Path) -> None:
    ledger = json.loads(LEDGER_PATH.read_text())
    ledger["records"][0]["unexpectedProperty"] = True
    ledger_path, receipt_path, manifest_path = _write_fixture_bundle(tmp_path, ledger=ledger)

    with pytest.raises(ValueError, match="contract failed.*unexpectedProperty"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=LEDGER_SCHEMA_PATH,
            receipt_path=receipt_path,
        )


def test_evidence_references_and_assertions_join_the_offline_receipt(tmp_path: Path) -> None:
    ledger = json.loads(LEDGER_PATH.read_text())
    ledger["records"][0]["differentialAssertion"]["evidenceReferenceId"] = "missing"
    ledger_path, receipt_path, manifest_path = _write_fixture_bundle(tmp_path, ledger=ledger)
    with pytest.raises(ValueError, match="differential assertion does not join"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=LEDGER_SCHEMA_PATH,
            receipt_path=receipt_path,
        )

    ledger = json.loads(LEDGER_PATH.read_text())
    ledger["records"][0]["evidenceReferences"][0]["path"] = "not/in/receipt.json"
    ledger_path, receipt_path, manifest_path = _write_fixture_bundle(tmp_path, ledger=ledger)
    with pytest.raises(ValueError, match="evidence path is absent"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=LEDGER_SCHEMA_PATH,
            receipt_path=receipt_path,
        )


def test_evidence_receipt_fails_closed_when_tampered_or_stale(tmp_path: Path) -> None:
    receipt_path = tmp_path / "tampered-receipt.json"
    receipt_path.write_bytes(RECEIPT_PATH.read_bytes() + b" ")
    with pytest.raises(ValueError, match="does not match its pinned producer artifact"):
        _load_delta_ledger(receipt_path=receipt_path)

    receipt = json.loads(RECEIPT_PATH.read_text())
    receipt["revision"] = "2" * 40
    ledger_path, receipt_path, manifest_path = _write_fixture_bundle(tmp_path, receipt=receipt)
    with pytest.raises(ValueError, match="does not match the ledger pin"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=LEDGER_SCHEMA_PATH,
            receipt_path=receipt_path,
        )


def test_evidence_receipt_rejects_unused_entries(tmp_path: Path) -> None:
    receipt = json.loads(RECEIPT_PATH.read_text())
    receipt["files"].append({"path": "unused/evidence.json", "sha256": "3" * 64})
    ledger_path, receipt_path, manifest_path = _write_fixture_bundle(tmp_path, receipt=receipt)

    with pytest.raises(ValueError, match="unused paths.*unused/evidence.json"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=LEDGER_SCHEMA_PATH,
            receipt_path=receipt_path,
        )


def test_accepted_review_requires_an_independent_decision_receipt(tmp_path: Path) -> None:
    ledger = json.loads(LEDGER_PATH.read_text())
    record = ledger["records"][0]
    record["classification"] = "approved_incompatibility"
    record["review"] = {
        "status": "accepted",
        "reviewer": "accountable-reviewer",
        "reviewedAt": "2026-08-24T12:00:00Z",
        "decisionEvidence": [record["evidenceReferences"][0]],
    }
    ledger_path, receipt_path, manifest_path = _write_fixture_bundle(tmp_path, ledger=ledger)

    with pytest.raises(ValueError, match="independent decision-artifact receipt"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=LEDGER_SCHEMA_PATH,
            receipt_path=receipt_path,
        )


def test_cli_rejects_unknown_flags() -> None:
    result = subprocess.run(
        [sys.executable, "bin/build_portable_legacy_differential.py", "--unknown"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "."},
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "unrecognized arguments: --unknown" in result.stderr


def test_invalid_injected_revision_fails_before_comparison() -> None:
    with pytest.raises(ValueError, match="full lowercase 40-character Git SHA"):
        compare_cohort(consumer_revision="main")
