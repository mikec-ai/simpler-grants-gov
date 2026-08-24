from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.form_schema.form_spec.differential import (
    COHORT_PATH,
    CONTRACT,
    Difference,
    _dimension,
    _load_cohort,
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


@pytest.fixture(scope="module")
def receipts() -> list[dict]:
    return compare_cohort(consumer_revision=TEST_REVISION)


def test_uniform_cohort_has_seven_comparison_gated_receipts(receipts: list[dict]) -> None:
    assert [receipt["portableFormId"] for receipt in receipts] == EXPECTED_FORMS
    assert all(receipt["contract"] == CONTRACT for receipt in receipts)
    assert all(receipt["comparisonGate"] for receipt in receipts)
    assert all("releaseGate" not in receipt for receipt in receipts)
    assert all(receipt["source"]["revision"] == TEST_REVISION for receipt in receipts)
    assert len({receipt["source"]["cohortSha256"] for receipt in receipts}) == 1

    for receipt in receipts:
        assert set(receipt["dimensions"]) == {"schema", "ui", "validation", "rules"}
        assert receipt["unsupportedDimensions"]["xml"]["status"] == "unavailable"
        assert receipt["unsupportedDimensions"]["ruleOutcomes"]["status"] == "unavailable"
        assert receipt["unsupportedDimensions"]["runtimeLifecycle"]["status"] == "unavailable"
        assert all(
            dimension["status"] in {"parity", "intentional_delta", "not_applicable"}
            for dimension in receipt["dimensions"].values()
        )


def test_exact_parity_is_distinct_from_intentional_delta_and_not_applicable(
    receipts: list[dict],
) -> None:
    by_form = {receipt["portableFormId"]: receipt for receipt in receipts}
    assert {
        dimension: result["status"]
        for dimension, result in by_form["project-narrative-attachments"]["dimensions"].items()
    } == {"schema": "parity", "ui": "parity", "validation": "parity", "rules": "parity"}
    assert by_form["key-contacts"]["dimensions"]["rules"]["status"] == "not_applicable"
    assert by_form["sf424b"]["dimensions"]["schema"]["status"] == "intentional_delta"


def test_cohort_rejects_delta_without_durable_evidence(tmp_path: Path) -> None:
    cohort = copy.deepcopy(json.loads(COHORT_PATH.read_text()))
    cohort["forms"][0]["intentionalDeltas"]["schema"][0]["evidence"] = "missing.md"
    path = tmp_path / "cohort.json"
    path.write_text(json.dumps(cohort))

    with pytest.raises(ValueError, match="evidence does not exist"):
        _load_cohort(path)


def test_undocumented_differences_and_stale_allowances_fail_closed() -> None:
    unexpected = _dimension([Difference("/field#type", "string", "number")], {})
    stale = _dimension(
        [],
        {
            "/field#type": {
                "reason": "A formerly intentional difference",
                "evidence": "tests/example.py",
            }
        },
    )

    assert unexpected["status"] == "failed"
    assert unexpected["unexpected"][0]["key"] == "/field#type"
    assert stale["status"] == "failed"
    assert stale["staleAllowances"] == ["/field#type"]


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
