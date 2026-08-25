#!/usr/bin/env python3
"""Build uniform portable-versus-existing Simpler differential receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.form_schema.form_spec.differential import (
    COHORT_PATH,
    _load_cohort,
    compare_cohort,
    no_oracle_disposition,
)

ARTIFACT_MANIFEST = Path("src/form_schema/form_spec/artifacts/artifact-manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=COHORT_PATH)
    parser.add_argument("--output-dir", type=Path, default=Path("test-results/legacy-differential"))
    parser.add_argument(
        "--consumer-revision",
        help="actually tested full Git revision (defaults to local Git HEAD)",
    )
    parser.add_argument(
        "--pr-head-revision",
        help="PR head Git revision; recorded separately from the tested checkout",
    )
    parser.add_argument(
        "--form-id",
        action="append",
        dest="form_ids",
        help="portable form id to compare (repeat for an exact subset)",
    )
    args = parser.parse_args()
    try:
        cohort = _load_cohort(args.cohort)
        cohort_ids = {record["portableFormId"] for record in cohort["forms"]}
        selected_ids = (
            tuple(args.form_ids)
            if args.form_ids is not None
            else tuple(record["portableFormId"] for record in cohort["forms"])
        )
        if not selected_ids:
            raise ValueError("differential form selection cannot be empty")
        if len(selected_ids) != len(set(selected_ids)):
            raise ValueError("differential form selection contains duplicate portable form ids")
        banked_ids = set(json.loads(ARTIFACT_MANIFEST.read_text())["selection"]["forms"])
        unknown_ids = sorted(set(selected_ids) - banked_ids)
        if unknown_ids:
            raise ValueError("differential form selection is not banked: " + ", ".join(unknown_ids))
        oracle_ids = tuple(form_id for form_id in selected_ids if form_id in cohort_ids)
        no_oracle_ids = tuple(form_id for form_id in selected_ids if form_id not in cohort_ids)
        receipts = (
            compare_cohort(
                args.cohort,
                consumer_revision=args.consumer_revision,
                pr_head_revision=args.pr_head_revision,
                form_ids=oracle_ids,
            )
            if oracle_ids
            else []
        )
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for receipt in receipts:
            path = args.output_dir / f"{receipt['portableFormId']}.json"
            path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        dispositions = [
            no_oracle_disposition(
                form_id,
                cohort_path=args.cohort,
                consumer_revision=args.consumer_revision,
                pr_head_revision=args.pr_head_revision,
            )
            for form_id in no_oracle_ids
        ]
        for disposition in dispositions:
            path = args.output_dir / f"{disposition['portableFormId']}.json"
            path.write_text(json.dumps(disposition, indent=2, sort_keys=True) + "\n")
        if len(selected_ids) != len(receipts) + len(dispositions):
            raise ValueError("selected form count does not equal receipts plus dispositions")
        dimension_statuses = {
            dimension: {
                status: sum(
                    receipt["dimensions"][dimension]["status"] == status for receipt in receipts
                )
                for status in (
                    "parity",
                    "reviewed_delta",
                    "proposed_delta",
                    "unresolved",
                    "not_applicable",
                    "failed",
                )
            }
            for dimension in ("schema", "ui", "validation", "rules")
        }
        failed_forms = sum(
            any(
                dimension["status"] in {"failed", "unresolved"}
                for dimension in receipt["dimensions"].values()
            )
            for receipt in receipts
        )
        summary = {
            "contract": "sgg-portable-legacy-differential-summary/v3",
            "forms": len(selected_ids),
            "selectedForms": list(selected_ids),
            "oracleReceipts": len(receipts),
            "noOracleDispositions": len(dispositions),
            "comparisonGatePassed": sum(receipt["comparisonGate"] for receipt in receipts),
            "comparisonGateBlocked": sum(not receipt["comparisonGate"] for receipt in receipts),
            "failed": failed_forms,
            "dimensionStatuses": dimension_statuses,
            "receipts": [f"{receipt['portableFormId']}.json" for receipt in receipts],
            "dispositions": [
                f"{disposition['portableFormId']}.json" for disposition in dispositions
            ],
        }
        (args.output_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1
    sys.stdout.write(
        "legacy_differential:\n"
        f"  forms: {summary['forms']}\n"
        f"  comparison_gate_passed: {summary['comparisonGatePassed']}\n"
        f"  comparison_gate_blocked: {summary['comparisonGateBlocked']}\n"
        f"  failed: {summary['failed']}\n"
        f"  output_directory: {args.output_dir}\n"
    )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
