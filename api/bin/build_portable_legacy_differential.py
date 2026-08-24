#!/usr/bin/env python3
"""Build uniform portable-versus-existing Simpler differential receipts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.form_schema.form_spec.differential import COHORT_PATH, compare_cohort


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, default=COHORT_PATH)
    parser.add_argument("--output-dir", type=Path, default=Path("test-results/legacy-differential"))
    parser.add_argument(
        "--consumer-revision",
        help="Full lowercase 40-character Git SHA (defaults to local Git HEAD)",
    )
    args = parser.parse_args()
    try:
        receipts = compare_cohort(args.cohort, consumer_revision=args.consumer_revision)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for receipt in receipts:
            path = args.output_dir / f"{receipt['portableFormId']}.json"
            path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        dimension_statuses = {
            dimension: {
                status: sum(
                    receipt["dimensions"][dimension]["status"] == status for receipt in receipts
                )
                for status in ("parity", "intentional_delta", "not_applicable", "failed")
            }
            for dimension in ("schema", "ui", "validation", "rules")
        }
        summary = {
            "contract": "sgg-portable-legacy-differential-summary/v2",
            "forms": len(receipts),
            "passed": sum(receipt["comparisonGate"] for receipt in receipts),
            "failed": sum(not receipt["comparisonGate"] for receipt in receipts),
            "dimensionStatuses": dimension_statuses,
            "receipts": [f"{receipt['portableFormId']}.json" for receipt in receipts],
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
        f"  passed: {summary['passed']}\n"
        f"  failed: {summary['failed']}\n"
        f"  output_directory: {args.output_dir}\n"
    )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
