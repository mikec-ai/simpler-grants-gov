#!/usr/bin/env python3
"""Classify and verify attributable portable-form changes.

The lightweight CI lanes are intentionally narrow. New vendored artifacts and
exact XSD fixtures can use bank-only CI. Existing form-local artifacts can use
focused CI when their exact mapped tests are selected. A test-only change can
also use focused CI, but only when every changed path is an exact, unambiguous
entry in the versioned portable CI maps. Consumer code, registration, projection,
shared files, unknown evidence, mixed-form changes, and deletions fail closed to full CI.
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
FORM_ARTIFACT_PREFIX = f"{ARTIFACTS.as_posix()}/forms/"
PORTABLE_TEST_PREFIX = "api/tests/src/form_schema/form_spec/"
PORTABLE_CI_MAP = Path("api/src/form_schema/form_spec/portable-form-ci-map.json")
PORTABLE_CI_MAP_CONTRACT = "sgg-portable-form-ci-map/v1"
FRONTEND_EVIDENCE_MAP = Path(
    "api/src/form_schema/form_spec/portable-form-frontend-evidence-map.json"
)
FRONTEND_EVIDENCE_MAP_CONTRACT = "sgg-portable-form-frontend-evidence-map/v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TIER_BANK_ONLY = "bank_only"
TIER_PORTABLE_FOCUSED = "portable_focused"
TIER_FULL = "full"


@dataclass(frozen=True)
class Change:
    status: str
    path: str


@dataclass(frozen=True)
class Classification:
    tier: str
    reason: str
    form_ids: tuple[str, ...] = ()
    test_files: tuple[str, ...] = ()
    frontend_evidence_files: tuple[str, ...] = ()

    @property
    def bank_only(self) -> bool:
        return self.tier == TIER_BANK_ONLY


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


def _form_id_from_artifact(path: str) -> str | None:
    if not path.startswith(FORM_ARTIFACT_PREFIX):
        return None
    remainder = path.removeprefix(FORM_ARTIFACT_PREFIX)
    form_id, separator, child = remainder.partition("/")
    return form_id if separator and child else None


def load_portable_ci_map(path: Path = PORTABLE_CI_MAP) -> dict[str, tuple[str, ...]]:
    resolved_path = path if path.is_absolute() else REPOSITORY_ROOT / path
    payload = json.loads(resolved_path.read_text())
    if payload.get("contract") != PORTABLE_CI_MAP_CONTRACT:
        raise ValueError("unsupported portable form CI map contract")
    forms = payload.get("forms")
    if not isinstance(forms, dict) or not forms:
        raise ValueError("portable form CI map must contain forms")
    mapping: dict[str, tuple[str, ...]] = {}
    for form_id, test_files in forms.items():
        if not isinstance(form_id, str) or not isinstance(test_files, list) or not test_files:
            raise ValueError("portable form CI map entries require a form id and tests")
        if any(
            not isinstance(test_file, str)
            or not test_file.startswith(PORTABLE_TEST_PREFIX)
            or not test_file.endswith(".py")
            for test_file in test_files
        ):
            raise ValueError(f"portable form CI map has invalid tests for {form_id}")
        if len(test_files) != len(set(test_files)):
            raise ValueError(f"portable form CI map has duplicate tests for {form_id}")
        missing = [
            test_file for test_file in test_files if not (REPOSITORY_ROOT / test_file).is_file()
        ]
        if missing:
            raise ValueError(f"portable form CI map has missing tests for {form_id}: {missing}")
        mapping[form_id] = tuple(sorted(test_files))
    return mapping


def _is_frontend_evidence_path(path: str) -> bool:
    if path.startswith("frontend/"):
        return path.endswith((".test.ts", ".test.tsx")) or (
            "/__fixtures__/" in path and path.endswith(".json")
        )
    return path.startswith(PORTABLE_TEST_PREFIX) and path.endswith(".json")


def load_frontend_evidence_map(
    path: Path = FRONTEND_EVIDENCE_MAP,
) -> dict[str, tuple[str, ...]]:
    resolved_path = path if path.is_absolute() else REPOSITORY_ROOT / path
    payload = json.loads(resolved_path.read_text())
    if payload.get("contract") != FRONTEND_EVIDENCE_MAP_CONTRACT:
        raise ValueError("unsupported portable form frontend evidence map contract")
    forms = payload.get("forms")
    if not isinstance(forms, dict) or not forms:
        raise ValueError("portable form frontend evidence map must contain forms")
    mapping: dict[str, tuple[str, ...]] = {}
    for form_id, evidence_files in forms.items():
        if (
            not isinstance(form_id, str)
            or not isinstance(evidence_files, list)
            or not evidence_files
        ):
            raise ValueError(
                "portable form frontend evidence map entries require a form id and evidence"
            )
        if any(
            not isinstance(evidence_file, str) or not _is_frontend_evidence_path(evidence_file)
            for evidence_file in evidence_files
        ):
            raise ValueError(
                f"portable form frontend evidence map has invalid evidence for {form_id}"
            )
        if len(evidence_files) != len(set(evidence_files)):
            raise ValueError(
                f"portable form frontend evidence map has duplicate evidence for {form_id}"
            )
        missing = [
            evidence_file
            for evidence_file in evidence_files
            if not (REPOSITORY_ROOT / evidence_file).is_file()
        ]
        if missing:
            raise ValueError(
                f"portable form frontend evidence map has missing evidence for {form_id}: {missing}"
            )
        mapping[form_id] = tuple(sorted(evidence_files))
    return mapping


def _reverse_mapping(mapping: dict[str, tuple[str, ...]]) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {}
    for form_id, paths in mapping.items():
        for path in paths:
            reverse.setdefault(path, set()).add(form_id)
    return reverse


def classify_change(
    changes: list[Change],
    *,
    portable_ci_map: dict[str, tuple[str, ...]] | None = None,
    frontend_evidence_map: dict[str, tuple[str, ...]] | None = None,
) -> Classification:
    if not changes:
        return Classification(TIER_FULL, "no changed files")

    deleted = [change.path for change in changes if change.status == "D"]
    if deleted:
        return Classification(TIER_FULL, f"deletions require full CI: {', '.join(deleted)}")

    outside_bank = [
        change.path
        for change in changes
        if not any(change.path.startswith(prefix) for prefix in BANKABLE_PREFIXES)
    ]
    if outside_bank:
        bank_reason = f"consumer or workflow changes require full CI: {', '.join(outside_bank)}"
    else:
        bank_reason = ""

    modified_existing = [
        change.path
        for change in changes
        if change.status != "A" and change.path != MANIFEST.as_posix()
    ]
    if modified_existing and not outside_bank:
        bank_reason = "existing portable artifacts or XSD fixtures require full CI: " + ", ".join(
            modified_existing
        )

    added_artifacts = [
        change.path
        for change in changes
        if change.status == "A" and change.path.startswith(f"{ARTIFACTS.as_posix()}/")
    ]
    if not added_artifacts and not bank_reason:
        bank_reason = "lightweight CI requires at least one new portable artifact"

    if not outside_bank and not modified_existing and added_artifacts:
        return Classification(
            TIER_BANK_ONLY, "only new portable artifacts and exact XSD fixtures were added"
        )

    mapping = portable_ci_map if portable_ci_map is not None else load_portable_ci_map()
    frontend_mapping = (
        frontend_evidence_map
        if frontend_evidence_map is not None
        else (load_frontend_evidence_map() if portable_ci_map is None else {})
    )
    unknown_frontend_forms = sorted(set(frontend_mapping) - set(mapping))
    if unknown_frontend_forms:
        raise ValueError(
            "portable form frontend evidence map references forms without API tests: "
            + ", ".join(unknown_frontend_forms)
        )

    # Evidence-only closure is focused only when every changed path is an exact
    # map entry and the complete change resolves to exactly one form. API tests
    # and frontend tests/fixtures remain distinct output classes.
    api_reverse_mapping = _reverse_mapping(mapping)
    frontend_reverse_mapping = _reverse_mapping(frontend_mapping)
    evidence_only_owners: set[str] = set()
    exact_evidence_only = True
    for change in changes:
        owners = api_reverse_mapping.get(change.path, set()) | frontend_reverse_mapping.get(
            change.path, set()
        )
        if not owners:
            exact_evidence_only = False
            break
        evidence_only_owners.update(owners)
    if exact_evidence_only and len(evidence_only_owners) == 1:
        evidence_form_id = next(iter(evidence_only_owners))
        return Classification(
            TIER_PORTABLE_FOCUSED,
            "only exact single-form CI-mapped API and frontend evidence changed",
            (evidence_form_id,),
            mapping[evidence_form_id],
            frontend_mapping.get(evidence_form_id, ()),
        )

    # Existing-form changes are focused only when every non-manifest artifact is
    # form-local and every other changed path is that form's exact mapped evidence.
    # XSD, question-bank, governance, registration, projection, runtime, frontend,
    # workflow, unknown evidence, and multiple-form changes fail closed to full CI.
    form_ids: set[str] = set()
    for change in changes:
        candidate_form_id = _form_id_from_artifact(change.path)
        if candidate_form_id is not None:
            form_ids.add(candidate_form_id)
    selected_form_id = next(iter(form_ids)) if len(form_ids) == 1 else None
    mapped_tests = set(mapping.get(selected_form_id, ())) if selected_form_id is not None else set()
    mapped_frontend_evidence = (
        set(frontend_mapping.get(selected_form_id, ())) if selected_form_id is not None else set()
    )
    focused_paths = True
    for change in changes:
        if change.path == MANIFEST.as_posix() or _form_id_from_artifact(change.path):
            continue
        owners = api_reverse_mapping.get(change.path, set()) | frontend_reverse_mapping.get(
            change.path, set()
        )
        if owners != ({selected_form_id} if selected_form_id is not None else set()):
            focused_paths = False
            break

    missing_mappings = sorted(form_ids - mapping.keys())
    if selected_form_id is not None and focused_paths and not missing_mappings:
        return Classification(
            TIER_PORTABLE_FOCUSED,
            "only attributable single-form artifacts and their exact mapped evidence changed",
            (selected_form_id,),
            tuple(sorted(mapped_tests)),
            tuple(sorted(mapped_frontend_evidence)),
        )

    return Classification(
        TIER_FULL, bank_reason or "ambiguous portable-form change requires full CI"
    )


def classify(changes: list[Change]) -> tuple[bool, str]:
    """Backward-compatible bank-only classification used by existing callers."""
    classification = classify_change(changes)
    return classification.bank_only, classification.reason


def manifest_at(revision: str) -> dict:
    result = subprocess.run(
        ["git", "show", f"{revision}:{MANIFEST.as_posix()}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def verify_portable_ci_map_selection(
    manifest: dict, *, portable_ci_map: dict[str, tuple[str, ...]] | None = None
) -> None:
    selected_forms = set(manifest["selection"]["forms"])
    mapping = portable_ci_map if portable_ci_map is not None else load_portable_ci_map()
    mapped_forms = set(mapping)
    missing = sorted(selected_forms - mapped_forms)
    stale = sorted(mapped_forms - selected_forms)
    if missing or stale:
        details = []
        if missing:
            details.append(f"missing selected forms: {missing}")
        if stale:
            details.append(f"stale unselected forms: {stale}")
        raise ValueError(
            "portable form CI map does not match artifact selection: " + "; ".join(details)
        )


def verify_additive_bank(base: str) -> dict[str, object]:
    previous = manifest_at(base)
    current = verify_artifact_selection(artifacts=ARTIFACTS, manifest_path=MANIFEST)
    verify_artifact_xsds(artifacts=ARTIFACTS, xsd_directory=XSD_DIRECTORY)
    verify_portable_ci_map_selection(current)

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
    added_files = sorted(current_files - previous_files)
    if not added_files:
        raise ValueError("lightweight CI requires a newly selected artifact")

    return {
        "addedForms": sorted(current_forms - previous_forms),
        "addedArtifacts": added_files,
        "selectedForms": len(current_forms),
        "selectedArtifacts": len(current_files),
    }


def verify_focused_forms(
    base: str, form_ids: tuple[str, ...], *, allow_unchanged_artifacts: bool = False
) -> dict[str, object]:
    previous = manifest_at(base)
    current = verify_artifact_selection(artifacts=ARTIFACTS, manifest_path=MANIFEST)
    verify_artifact_xsds(artifacts=ARTIFACTS, xsd_directory=XSD_DIRECTORY)

    previous_forms = set(previous["selection"]["forms"])
    current_forms = set(current["selection"]["forms"])
    if current_forms != previous_forms:
        raise ValueError("focused form CI cannot change the selected form set")
    missing = sorted(set(form_ids) - current_forms)
    if missing:
        raise ValueError(f"focused form CI selected unknown forms: {missing}")

    previous_files = {record["path"]: record for record in previous["files"]}
    current_files = {record["path"]: record for record in current["files"]}
    changed_records = sorted(
        path
        for path in set(previous_files) | set(current_files)
        if previous_files.get(path) != current_files.get(path)
    )
    allowed_prefixes = tuple(f"dist/forms/{form_id}/" for form_id in form_ids)
    outside_forms = [path for path in changed_records if not path.startswith(allowed_prefixes)]
    if outside_forms:
        raise ValueError(
            "focused form CI cannot change shared artifact closure: " + ", ".join(outside_forms)
        )
    if not changed_records and not allow_unchanged_artifacts:
        raise ValueError("focused form CI requires a changed selected form artifact")

    return {
        "focusedForms": list(form_ids),
        "changedArtifacts": changed_records,
        "selectedForms": len(current_forms),
        "selectedArtifacts": len(current_files),
    }


def write_output(stream: TextIO, *, classification: Classification) -> None:
    stream.write(f"bank_only={'true' if classification.bank_only else 'false'}\n")
    stream.write(f"tier={classification.tier}\n")
    stream.write(f"portable_form_ids={','.join(classification.form_ids)}\n")
    stream.write(f"portable_test_files={','.join(classification.test_files)}\n")
    stream.write(
        "portable_frontend_evidence_files=" f"{','.join(classification.frontend_evidence_files)}\n"
    )
    stream.write(f"reason={classification.reason}\n")


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
    classification = classify_change(changes)
    receipt: dict[str, object] = {
        "bankOnly": classification.bank_only,
        "tier": classification.tier,
        "reason": classification.reason,
        "portableFormIds": list(classification.form_ids),
        "portableTestFiles": list(classification.test_files),
        "portableFrontendEvidenceFiles": list(classification.frontend_evidence_files),
        "changedFiles": [change.path for change in changes],
    }
    if classification.bank_only:
        receipt.update(verify_additive_bank(args.base))
    elif classification.tier == TIER_PORTABLE_FOCUSED:
        exact_evidence_paths = set(classification.test_files) | set(
            classification.frontend_evidence_files
        )
        evidence_only = all(change.path in exact_evidence_paths for change in changes)
        receipt.update(
            verify_focused_forms(
                args.base,
                classification.form_ids,
                allow_unchanged_artifacts=evidence_only,
            )
        )

    if args.github_output is not None:
        with args.github_output.open("a") as stream:
            write_output(stream, classification=classification)
    sys.stdout.write(f"{json.dumps(receipt, indent=2, sort_keys=True)}\n")


if __name__ == "__main__":
    main()
