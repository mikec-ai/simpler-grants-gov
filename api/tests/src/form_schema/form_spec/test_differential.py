from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from src.form_schema.form_spec.differential import (
    COHORT_PATH,
    CONTRACT,
    DISPOSITION_CONTRACT,
    LEDGER_PATH,
    LEDGER_SCHEMA_PATH,
    Difference,
    _dimension,
    _load_cohort,
    _load_delta_ledger,
    compare_cohort,
    no_oracle_disposition,
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
    decision_receipt: dict | None = None,
    decision_artifacts: dict[str, bytes] | None = None,
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
    if decision_receipt is not None:
        payloads["parity/decision-verification.v1.json"] = (
            json.dumps(decision_receipt) + "\n"
        ).encode()
        ledger_schema = json.loads(LEDGER_SCHEMA_PATH.read_text())
        if "decisionVerification" not in ledger_schema["properties"]:
            ledger_schema["required"].append("decisionVerification")
            ledger_schema["properties"]["decisionVerification"] = {
                "type": "object",
                "required": ["receipt"],
                "properties": {"receipt": {"type": "string"}},
            }
        payloads["contract/v1/parity-delta-ledger.schema.json"] = (
            json.dumps(ledger_schema) + "\n"
        ).encode()
        payloads["contract/v1/parity-decision-verification.schema.json"] = (
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": ["contract", "artifacts"],
                    "properties": {
                        "contract": {"const": "grants-form-parity-decision-verification/v1"},
                        "artifacts": {"type": "array", "items": {"type": "object"}},
                    },
                }
            )
            + "\n"
        ).encode()
        payloads["contract/v1/parity-decision-artifact.schema.json"] = (
            json.dumps(
                {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    "type": "object",
                    "required": [
                        "contract",
                        "id",
                        "ledgerRecordId",
                        "formId",
                        "target",
                        "classification",
                        "decision",
                        "reviewer",
                        "reviewedAt",
                        "rationale",
                    ],
                    "properties": {
                        "contract": {"const": "grants-form-parity-decision/v1"},
                        "decision": {"const": "accepted"},
                    },
                }
            )
            + "\n"
        ).encode()
    payloads.update(decision_artifacts or {})
    ledger_path.write_bytes(payloads["parity/legacy-deltas.v1.json"])
    receipt_path.write_bytes(payloads[RECEIPT_SOURCE_PATH])
    if decision_receipt is not None:
        (tmp_path / "decision-receipt.json").write_bytes(
            payloads["parity/decision-verification.v1.json"]
        )
        (tmp_path / "decision-ledger-schema.json").write_bytes(
            payloads["contract/v1/parity-delta-ledger.schema.json"]
        )
        (tmp_path / "decision-receipt-schema.json").write_bytes(
            payloads["contract/v1/parity-decision-verification.schema.json"]
        )
        (tmp_path / "decision-artifact-schema.json").write_bytes(
            payloads["contract/v1/parity-decision-artifact.schema.json"]
        )
    for source_path, artifact_payload in (decision_artifacts or {}).items():
        artifact_path = tmp_path / source_path
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(artifact_payload)
    manifest = json.loads(ARTIFACT_MANIFEST.read_text())
    for record in manifest["files"]:
        payload = payloads.get(record["path"])
        if payload is not None:
            record.update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    existing = {record["path"] for record in manifest["files"]}
    for source_path, payload in payloads.items():
        if source_path not in existing:
            manifest["files"].append(
                {
                    "path": source_path,
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
    manifest_path.write_text(json.dumps(manifest))
    return ledger_path, receipt_path, manifest_path


def _accepted_decision_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path, Path, Path, Path]:
    ledger = json.loads(LEDGER_PATH.read_text())
    ledger["decisionVerification"] = {"receipt": "parity/decision-verification.v1.json"}
    record = next(
        row
        for row in ledger["records"]
        if row["classification"] == "authoritative_source_correction"
    )
    decision_path = "parity/decisions/fixture-acceptance.json"
    decision_reference = {
        "id": "fixture-acceptance",
        "repository": "https://github.com/mikec-ai/grants-form-spec.git",
        "revision": "3" * 40,
        "path": decision_path,
    }
    record["review"] = {
        "status": "accepted",
        "reviewer": "accountable-reviewer",
        "reviewedAt": "2026-08-25T12:00:00Z",
        "decisionEvidence": [decision_reference],
    }
    artifact = {
        "contract": "grants-form-parity-decision/v1",
        "id": decision_reference["id"],
        "ledgerRecordId": record["id"],
        "formId": record["formId"],
        "target": record["target"],
        "classification": record["classification"],
        "decision": "accepted",
        "reviewer": record["review"]["reviewer"],
        "reviewedAt": record["review"]["reviewedAt"],
        "rationale": "The accountable reviewer accepts this exact fixture delta.",
    }
    artifact_payload = (json.dumps(artifact, sort_keys=True) + "\n").encode()
    decision_receipt = {
        "contract": "grants-form-parity-decision-verification/v1",
        "artifacts": [
            {
                **{key: decision_reference[key] for key in ("repository", "revision", "path")},
                "sha256": hashlib.sha256(artifact_payload).hexdigest(),
            }
        ],
    }
    ledger_path, receipt_path, manifest_path = _write_fixture_bundle(
        tmp_path,
        ledger=ledger,
        decision_receipt=decision_receipt,
        decision_artifacts={decision_path: artifact_payload},
    )
    return (
        ledger_path,
        receipt_path,
        manifest_path,
        tmp_path / "decision-receipt.json",
        tmp_path / decision_path,
        tmp_path / "decision-ledger-schema.json",
        tmp_path / "decision-receipt-schema.json",
        tmp_path / "decision-artifact-schema.json",
    )


@pytest.fixture(scope="module")
def receipts() -> list[dict]:
    return compare_cohort(consumer_revision=TEST_REVISION)


def test_uniform_cohort_has_seven_comparison_gated_receipts(receipts: list[dict]) -> None:
    assert [receipt["portableFormId"] for receipt in receipts] == EXPECTED_FORMS
    assert all(receipt["contract"] == CONTRACT for receipt in receipts)
    assert sum(receipt["comparisonGate"] for receipt in receipts) == 1
    assert all("releaseGate" not in receipt for receipt in receipts)
    assert all(receipt["source"]["revision"] == TEST_REVISION for receipt in receipts)
    assert all(receipt["source"]["testedRevision"] == TEST_REVISION for receipt in receipts)
    assert all(receipt["source"]["prHeadRevision"] == TEST_REVISION for receipt in receipts)
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

    with pytest.raises(ValueError, match="absent from the offline verification receipt"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=LEDGER_SCHEMA_PATH,
            receipt_path=receipt_path,
        )


def test_exact_offline_verified_accountable_decision_is_accepted(tmp_path: Path) -> None:
    (
        ledger_path,
        receipt_path,
        manifest_path,
        decision_receipt_path,
        _,
        ledger_schema_path,
        receipt_schema_path,
        artifact_schema_path,
    ) = _accepted_decision_fixture(tmp_path)

    ledger, source = _load_delta_ledger(
        ledger_path,
        manifest_path=manifest_path,
        schema_path=ledger_schema_path,
        receipt_path=receipt_path,
        decision_receipt_path=decision_receipt_path,
        decision_artifact_root=tmp_path,
        decision_receipt_schema_path=receipt_schema_path,
        decision_schema_path=artifact_schema_path,
    )

    assert any(record["review"]["status"] == "accepted" for record in ledger["records"])
    assert re.fullmatch(r"[0-9a-f]{64}", source["decisionReceiptSha256"])


def test_decision_evidence_rejects_missing_tampered_and_stale_artifacts(tmp_path: Path) -> None:
    (
        ledger_path,
        receipt_path,
        manifest_path,
        decision_receipt_path,
        artifact_path,
        ledger_schema_path,
        receipt_schema_path,
        artifact_schema_path,
    ) = _accepted_decision_fixture(tmp_path)
    artifact_path.unlink()
    with pytest.raises(ValueError, match="pinned portable artifact is missing"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=ledger_schema_path,
            receipt_path=receipt_path,
            decision_receipt_path=decision_receipt_path,
            decision_artifact_root=tmp_path,
            decision_receipt_schema_path=receipt_schema_path,
            decision_schema_path=artifact_schema_path,
        )

    other = tmp_path / "tampered"
    other.mkdir()
    (
        ledger_path,
        receipt_path,
        manifest_path,
        decision_receipt_path,
        artifact_path,
        ledger_schema_path,
        receipt_schema_path,
        artifact_schema_path,
    ) = _accepted_decision_fixture(other)
    artifact_path.write_bytes(artifact_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="does not match its pinned producer artifact"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=ledger_schema_path,
            receipt_path=receipt_path,
            decision_receipt_path=decision_receipt_path,
            decision_artifact_root=other,
            decision_receipt_schema_path=receipt_schema_path,
            decision_schema_path=artifact_schema_path,
        )

    stale = tmp_path / "stale"
    stale.mkdir()
    (
        ledger_path,
        receipt_path,
        manifest_path,
        decision_receipt_path,
        artifact_path,
        ledger_schema_path,
        receipt_schema_path,
        artifact_schema_path,
    ) = _accepted_decision_fixture(stale)
    ledger = json.loads(ledger_path.read_text())
    accepted = next(
        record for record in ledger["records"] if record["review"]["status"] == "accepted"
    )
    accepted["review"]["reviewer"] = "different-reviewer"
    payload = (json.dumps(ledger) + "\n").encode()
    ledger_path.write_bytes(payload)
    manifest = json.loads(manifest_path.read_text())
    manifest_record = next(
        row for row in manifest["files"] if row["path"] == "parity/legacy-deltas.v1.json"
    )
    manifest_record.update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="stale for ledger fields.*reviewer"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=ledger_schema_path,
            receipt_path=receipt_path,
            decision_receipt_path=decision_receipt_path,
            decision_artifact_root=stale,
            decision_receipt_schema_path=receipt_schema_path,
            decision_schema_path=artifact_schema_path,
        )


def test_decision_evidence_rejects_unverified_and_reused_artifacts(tmp_path: Path) -> None:
    (
        ledger_path,
        receipt_path,
        manifest_path,
        decision_receipt_path,
        _,
        ledger_schema_path,
        receipt_schema_path,
        artifact_schema_path,
    ) = _accepted_decision_fixture(tmp_path)
    ledger = json.loads(ledger_path.read_text())
    accepted = next(
        record for record in ledger["records"] if record["review"]["status"] == "accepted"
    )
    accepted["review"]["decisionEvidence"][0]["revision"] = "4" * 40
    payload = (json.dumps(ledger) + "\n").encode()
    ledger_path.write_bytes(payload)
    manifest = json.loads(manifest_path.read_text())
    manifest_record = next(
        row for row in manifest["files"] if row["path"] == "parity/legacy-deltas.v1.json"
    )
    manifest_record.update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="absent from the offline verification receipt"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=ledger_schema_path,
            receipt_path=receipt_path,
            decision_receipt_path=decision_receipt_path,
            decision_artifact_root=tmp_path,
            decision_receipt_schema_path=receipt_schema_path,
            decision_schema_path=artifact_schema_path,
        )

    reused = tmp_path / "reused"
    reused.mkdir()
    (
        ledger_path,
        receipt_path,
        manifest_path,
        decision_receipt_path,
        _,
        ledger_schema_path,
        receipt_schema_path,
        artifact_schema_path,
    ) = _accepted_decision_fixture(reused)
    ledger = json.loads(ledger_path.read_text())
    accepted = next(
        record for record in ledger["records"] if record["review"]["status"] == "accepted"
    )
    duplicate = json.loads(json.dumps(accepted))
    duplicate["id"] = "fixture.second-accepted-delta"
    duplicate["target"]["differenceKey"] = "/different#key"
    ledger["records"].append(duplicate)
    payload = (json.dumps(ledger) + "\n").encode()
    ledger_path.write_bytes(payload)
    manifest = json.loads(manifest_path.read_text())
    manifest_record = next(
        row for row in manifest["files"] if row["path"] == "parity/legacy-deltas.v1.json"
    )
    manifest_record.update(size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="reuses a decision artifact"):
        _load_delta_ledger(
            ledger_path,
            manifest_path=manifest_path,
            schema_path=ledger_schema_path,
            receipt_path=receipt_path,
            decision_receipt_path=decision_receipt_path,
            decision_artifact_root=reused,
            decision_receipt_schema_path=receipt_schema_path,
            decision_schema_path=artifact_schema_path,
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


def test_tested_and_pr_head_revisions_are_attributed_separately() -> None:
    pr_head = "2" * 40
    selected = compare_cohort(
        consumer_revision=TEST_REVISION,
        pr_head_revision=pr_head,
        form_ids=("project-narrative-attachments",),
    )

    assert selected[0]["source"]["revision"] == TEST_REVISION
    assert selected[0]["source"]["testedRevision"] == TEST_REVISION
    assert selected[0]["source"]["prHeadRevision"] == pr_head


def test_no_oracle_disposition_is_versioned_and_revision_attributed() -> None:
    disposition = no_oracle_disposition(
        "sf424c",
        consumer_revision=TEST_REVISION,
        pr_head_revision="2" * 40,
    )

    assert disposition["contract"] == DISPOSITION_CONTRACT
    assert disposition["outcome"] == "no_oracle"
    assert disposition["reasonCode"] == "no-versioned-oracle-configured"
    assert disposition["source"]["testedRevision"] == TEST_REVISION
    assert disposition["source"]["prHeadRevision"] == "2" * 40


def test_exact_form_subset_preserves_requested_order() -> None:
    selected = compare_cohort(
        consumer_revision=TEST_REVISION,
        form_ids=("project-narrative-attachments", "project-abstract-summary"),
    )

    assert [receipt["portableFormId"] for receipt in selected] == [
        "project-narrative-attachments",
        "project-abstract-summary",
    ]


@pytest.mark.parametrize(
    ("form_ids", "message"),
    [
        ((), "cannot be empty"),
        (("sf424", "sf424"), "duplicate"),
        (("not-in-cohort",), "outside the cohort"),
    ],
)
def test_exact_form_subset_fails_closed(form_ids: tuple[str, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        compare_cohort(consumer_revision=TEST_REVISION, form_ids=form_ids)


def test_cli_writes_only_requested_form_receipt(tmp_path: Path) -> None:
    output = tmp_path / "receipts"
    result = subprocess.run(
        [
            sys.executable,
            "bin/build_portable_legacy_differential.py",
            "--consumer-revision",
            TEST_REVISION,
            "--form-id",
            "project-narrative-attachments",
            "--output-dir",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "."},
    )

    assert result.returncode == 0, result.stderr
    assert sorted(path.name for path in output.iterdir()) == [
        "project-narrative-attachments.json",
        "summary.json",
    ]
    summary = json.loads((output / "summary.json").read_text())
    assert summary["forms"] == 1
    assert summary["oracleReceipts"] == 1
    assert summary["noOracleDispositions"] == 0


def test_cli_writes_explicit_disposition_for_banked_form_without_oracle(tmp_path: Path) -> None:
    output = tmp_path / "receipts"
    result = subprocess.run(
        [
            sys.executable,
            "bin/build_portable_legacy_differential.py",
            "--consumer-revision",
            TEST_REVISION,
            "--form-id",
            "sf424c",
            "--output-dir",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "."},
    )

    assert result.returncode == 0, result.stderr
    disposition = json.loads((output / "sf424c.json").read_text())
    summary = json.loads((output / "summary.json").read_text())
    assert disposition["contract"] == DISPOSITION_CONTRACT
    assert summary["selectedForms"] == ["sf424c"]
    assert summary["oracleReceipts"] == 0
    assert summary["noOracleDispositions"] == 1
    assert summary["forms"] == summary["oracleReceipts"] + summary["noOracleDispositions"]


def test_cli_accounts_for_every_selected_form_across_both_outcomes(tmp_path: Path) -> None:
    output = tmp_path / "receipts"
    result = subprocess.run(
        [
            sys.executable,
            "bin/build_portable_legacy_differential.py",
            "--consumer-revision",
            TEST_REVISION,
            "--pr-head-revision",
            "2" * 40,
            "--form-id",
            "project-narrative-attachments",
            "--form-id",
            "sf424c",
            "--output-dir",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "."},
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads((output / "summary.json").read_text())
    assert summary["selectedForms"] == ["project-narrative-attachments", "sf424c"]
    assert summary["forms"] == 2
    assert summary["oracleReceipts"] == 1
    assert summary["noOracleDispositions"] == 1
    for form_id in summary["selectedForms"]:
        outcome = json.loads((output / f"{form_id}.json").read_text())
        assert outcome["source"]["testedRevision"] == TEST_REVISION
        assert outcome["source"]["prHeadRevision"] == "2" * 40


def test_cli_rejects_unbanked_form(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "bin/build_portable_legacy_differential.py",
            "--consumer-revision",
            TEST_REVISION,
            "--form-id",
            "not-banked",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "."},
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "not banked" in result.stderr
