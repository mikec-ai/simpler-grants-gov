import json
from pathlib import Path

import pytest

import bin.check_form_spec_bank as checker
from bin.check_form_spec_bank import (
    TIER_FULL,
    TIER_PORTABLE_FOCUSED,
    Change,
    classify,
    classify_change,
    load_portable_ci_map,
    verify_portable_ci_map_selection,
)

ARTIFACT_MANIFEST = Path("src/form_schema/form_spec/artifacts/artifact-manifest.json")


def test_artifact_and_xsd_additions_use_bank_only_ci():
    bank_only, reason = classify(
        [
            Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
            Change("A", "api/src/form_schema/form_spec/artifacts/forms/example/schema.json"),
            Change("A", "api/src/services/xml_generation/xsds/Example-V1.0.xsd"),
        ]
    )

    assert bank_only is True
    assert "new portable artifacts" in reason


def test_shared_artifact_or_xsd_modification_requires_full_ci():
    for path in (
        "api/src/form_schema/form_spec/artifacts/question-bank/generics/email/schema.json",
        "api/src/services/xml_generation/xsds/SF424-V4.0.xsd",
    ):
        bank_only, reason = classify(
            [
                Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
                Change("M", path),
            ]
        )

        assert bank_only is False
        assert "require full CI" in reason


def test_manifest_only_or_xsd_only_change_requires_full_ci():
    for changes in (
        [Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json")],
        [
            Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
            Change("A", "api/src/services/xml_generation/xsds/Unselected-V1.0.xsd"),
        ],
    ):
        bank_only, reason = classify(changes)

        assert bank_only is False
        assert "new portable artifact" in reason


def test_consumer_code_requires_full_ci():
    bank_only, reason = classify(
        [
            Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
            Change("M", "api/src/form_schema/form_spec/loader.py"),
        ]
    )

    assert bank_only is False
    assert "full CI" in reason


def test_tests_and_registration_require_full_ci():
    for path in (
        "api/tests/src/form_schema/form_spec/test_example.py",
        "api/src/form_schema/form_spec/registrations.json",
        "api/src/form_schema/form_spec/runtime-identities.json",
        "api/src/form_schema/form_spec/projections/example.json",
    ):
        bank_only, _ = classify([Change("M", path)])
        assert bank_only is False


def test_deletions_require_full_ci_even_inside_the_artifact_bank():
    bank_only, reason = classify(
        [Change("D", "api/src/form_schema/form_spec/artifacts/forms/example/schema.json")]
    )

    assert bank_only is False
    assert "deletions require full CI" in reason


def test_empty_diff_requires_full_ci():
    bank_only, reason = classify([])

    assert bank_only is False
    assert reason == "no changed files"


def test_existing_form_artifacts_and_exact_test_use_focused_ci():
    classification = classify_change(
        [
            Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
            Change(
                "M",
                "api/src/form_schema/form_spec/artifacts/forms/project-abstract-summary/manifest.json",
            ),
            Change(
                "A",
                "api/src/form_schema/form_spec/artifacts/forms/project-abstract-summary/targets/grants-gov-xml.json",
            ),
            Change(
                "M",
                "api/tests/src/form_schema/form_spec/test_project_abstract_summary_portable.py",
            ),
        ]
    )

    assert classification.tier == TIER_PORTABLE_FOCUSED
    assert classification.form_ids == ("project-abstract-summary",)
    assert classification.test_files == (
        "api/tests/src/form_schema/form_spec/test_project_abstract_summary_portable.py",
    )


def test_registered_form_artifact_without_test_edit_uses_focused_ci():
    classification = classify_change(
        [
            Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
            Change("M", "api/src/form_schema/form_spec/artifacts/forms/sf424c/schema.json"),
        ]
    )

    assert classification.tier == TIER_PORTABLE_FOCUSED
    assert classification.form_ids == ("sf424c",)
    assert classification.test_files == (
        "api/tests/src/form_schema/form_spec/test_sf424c_portable.py",
    )


def test_portable_ci_map_exactly_covers_banked_forms_and_existing_tests():
    mapping = load_portable_ci_map()
    selected = set(json.loads(ARTIFACT_MANIFEST.read_text())["selection"]["forms"])

    assert set(mapping) == selected
    assert all(
        (Path("..").resolve() / test_file).is_file()
        for tests in mapping.values()
        for test_file in tests
    )


def test_additive_bank_rejects_manifest_map_drift_for_new_form(monkeypatch):
    previous = json.loads(ARTIFACT_MANIFEST.read_text())
    current = json.loads(ARTIFACT_MANIFEST.read_text())
    current["selection"]["forms"].append("newly-banked-form")
    monkeypatch.setattr(checker, "manifest_at", lambda _revision: previous)
    monkeypatch.setattr(checker, "verify_artifact_selection", lambda **_kwargs: current)
    monkeypatch.setattr(checker, "verify_artifact_xsds", lambda **_kwargs: None)

    with pytest.raises(ValueError, match="missing selected forms.*newly-banked-form"):
        checker.verify_additive_bank("base-revision")


def test_bank_verification_rejects_stale_unselected_map_entry():
    manifest = json.loads(ARTIFACT_MANIFEST.read_text())
    mapping = load_portable_ci_map()
    mapping["stale-form"] = ("api/tests/src/form_schema/form_spec/test_registrations.py",)

    with pytest.raises(ValueError, match="stale unselected forms.*stale-form"):
        verify_portable_ci_map_selection(manifest, portable_ci_map=mapping)


def test_multiple_focused_forms_are_sorted_deterministically():
    classification = classify_change(
        [
            Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
            Change("M", "api/src/form_schema/form_spec/artifacts/forms/sf424c/schema.json"),
            Change("M", "api/src/form_schema/form_spec/artifacts/forms/cd511/schema.json"),
            Change("M", "api/tests/src/form_schema/form_spec/test_sf424c_portable.py"),
            Change("M", "api/tests/src/form_schema/form_spec/test_cd511_portable.py"),
        ]
    )

    assert classification.tier == TIER_PORTABLE_FOCUSED
    assert classification.form_ids == ("cd511", "sf424c")
    assert classification.test_files == (
        "api/tests/src/form_schema/form_spec/test_cd511_portable.py",
        "api/tests/src/form_schema/form_spec/test_sf424c_portable.py",
    )


@pytest.mark.parametrize(
    "path",
    [
        "api/src/form_schema/form_spec/artifacts/question-bank/generics/email/schema.json",
        "api/src/form_schema/form_spec/artifacts/governance/parity.json",
        "api/src/form_schema/form_spec/loader.py",
        "api/src/form_schema/form_spec/registrations.json",
        "api/src/form_schema/form_spec/projections/sf424c.json",
        "frontend/src/components/apply-form/Form.tsx",
        "api/src/services/xml_generation/xsds/SF424C-V2.0.xsd",
        "api/tests/src/form_schema/form_spec/test_browser_plan.py",
    ],
)
def test_shared_or_ambiguous_changes_require_full_ci(path: str):
    classification = classify_change(
        [
            Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
            Change("M", "api/src/form_schema/form_spec/artifacts/forms/sf424c/schema.json"),
            Change("M", "api/tests/src/form_schema/form_spec/test_sf424c_portable.py"),
            Change("M", path),
        ]
    )

    assert classification.tier == TIER_FULL
    assert classification.form_ids == ()


def test_unmatched_portable_test_requires_full_ci():
    classification = classify_change(
        [
            Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
            Change("M", "api/src/form_schema/form_spec/artifacts/forms/sf424c/schema.json"),
            Change("M", "api/tests/src/form_schema/form_spec/test_sf424d_portable.py"),
        ]
    )

    assert classification.tier == TIER_FULL


def test_form_missing_from_explicit_ci_map_requires_full_ci():
    classification = classify_change(
        [Change("M", "api/src/form_schema/form_spec/artifacts/forms/new-form/schema.json")],
        portable_ci_map={
            "sf424c": ("api/tests/src/form_schema/form_spec/test_sf424c_portable.py",)
        },
    )

    assert classification.tier == TIER_FULL


def test_deletion_never_uses_focused_ci():
    classification = classify_change(
        [
            Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
            Change("D", "api/src/form_schema/form_spec/artifacts/forms/sf424c/schema.json"),
            Change("M", "api/tests/src/form_schema/form_spec/test_sf424c_portable.py"),
        ]
    )

    assert classification.tier == TIER_FULL
    assert "deletions require full CI" in classification.reason
