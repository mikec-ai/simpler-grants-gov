#!/usr/bin/env python3
"""Classify and verify strictly additive portable-form banking changes.

The lightweight CI lane is intentionally narrow: it applies only when a pull
request adds new vendored artifacts and exact XSD fixtures. Updating an existing
artifact may change a runtime-enabled form, so modifications, consumer code,
tests, registration, projection, and deletions all require full CI.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from src.form_schema.form_spec_integrity import verify_artifact_selection, verify_artifact_xsds

ARTIFACTS = Path("api/src/form_schema/form_spec/artifacts")
MANIFEST = ARTIFACTS / "artifact-manifest.json"
XSD_DIRECTORY = Path("api/src/services/xml_generation/xsds")
BANKABLE_PREFIXES = (
    f"{ARTIFACTS.as_posix()}/",
    f"{XSD_DIRECTORY.as_posix()}/",
)


@dataclass(frozen=True)
class Change:
    status: str
    path: str


def git_changes(base: str, head: str) -> list[Change]:
    result = subprocess.run(
        ["git", "diff", "--name-status", "--no-renames", "-z", base, head],
        check=True,
        capture_output=True,
    )
    fields = result.stdout.decode().split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) % 2:
        raise ValueError("unexpected git diff --name-status output")
    return [Change(status, path) for status, path in zip(fields[::2], fields[1::2], strict=True)]


def classify(changes: list[Change]) -> tuple[bool, str]:
    if not changes:
        return False, "no changed files"

    deleted = [change.path for change in changes if change.status == "D"]
    if deleted:
        return False, f"deletions require full CI: {', '.join(deleted)}"

    outside_bank = [
        change.path
        for change in changes
        if not any(change.path.startswith(prefix) for prefix in BANKABLE_PREFIXES)
    ]
    if outside_bank:
        return False, f"consumer or workflow changes require full CI: {', '.join(outside_bank)}"

    modified_existing = [
        change.path
        for change in changes
        if change.status != "A" and change.path != MANIFEST.as_posix()
    ]
    if modified_existing:
        return (
            False,
            "existing portable artifacts or XSD fixtures require full CI: "
            + ", ".join(modified_existing),
        )

    return True, "only new portable artifacts and exact XSD fixtures were added"


def manifest_at(revision: str) -> dict:
    result = subprocess.run(
        ["git", "show", f"{revision}:{MANIFEST.as_posix()}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def verify_additive_bank(base: str) -> dict[str, object]:
    previous = manifest_at(base)
    current = verify_artifact_selection(artifacts=ARTIFACTS, manifest_path=MANIFEST)
    verify_artifact_xsds(artifacts=ARTIFACTS, xsd_directory=XSD_DIRECTORY)

    previous_forms = set(previous["selection"]["forms"])
    current_forms = set(current["selection"]["forms"])
    removed_forms = sorted(previous_forms - current_forms)
    if removed_forms:
        raise ValueError(f"banking removed selected forms: {removed_forms}")

    previous_files = {record["path"] for record in previous["files"]}
    current_files = {record["path"] for record in current["files"]}
    removed_files = sorted(previous_files - current_files)
    if removed_files:
        raise ValueError(f"banking removed selected artifact closure: {removed_files}")

    return {
        "addedForms": sorted(current_forms - previous_forms),
        "selectedForms": len(current_forms),
        "selectedArtifacts": len(current_files),
    }


def write_output(stream: TextIO, *, bank_only: bool, reason: str) -> None:
    stream.write(f"bank_only={'true' if bank_only else 'false'}\n")
    stream.write(f"reason={reason}\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="pull-request base commit")
    parser.add_argument("--head", required=True, help="pull-request head commit")
    parser.add_argument(
        "--github-output",
        type=Path,
        default=Path(os.environ["GITHUB_OUTPUT"]) if "GITHUB_OUTPUT" in os.environ else None,
        help="optional GitHub Actions output file",
    )
    args = parser.parse_args()

    changes = git_changes(args.base, args.head)
    bank_only, reason = classify(changes)
    receipt: dict[str, object] = {
        "bankOnly": bank_only,
        "reason": reason,
        "changedFiles": [change.path for change in changes],
    }
    if bank_only:
        receipt.update(verify_additive_bank(args.base))

    if args.github_output is not None:
        with args.github_output.open("a") as stream:
            write_output(stream, bank_only=bank_only, reason=reason)
    sys.stdout.write(f"{json.dumps(receipt, indent=2, sort_keys=True)}\n")


if __name__ == "__main__":
    main()
