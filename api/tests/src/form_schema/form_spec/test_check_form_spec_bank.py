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
    load_frontend_evidence_map,
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


def test_multiple_form_artifact_owners_require_full_ci():
    classification = classify_change(
        [
            Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
            Change("M", "api/src/form_schema/form_spec/artifacts/forms/sf424c/schema.json"),
            Change("M", "api/src/form_schema/form_spec/artifacts/forms/cd511/schema.json"),
            Change("M", "api/tests/src/form_schema/form_spec/test_sf424c_portable.py"),
            Change("M", "api/tests/src/form_schema/form_spec/test_cd511_portable.py"),
        ]
    )

    assert classification.tier == TIER_FULL
    assert classification.form_ids == ()


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


def test_one_exact_mapped_test_uses_focused_ci_without_an_artifact_change():
    test_file = "api/tests/src/form_schema/form_spec/test_sf424c_portable.py"

    classification = classify_change(
        [Change("M", test_file)],
        portable_ci_map={"sf424c": (test_file,)},
    )

    assert classification == checker.Classification(
        TIER_PORTABLE_FOCUSED,
        "only exact single-form CI-mapped API and frontend evidence changed",
        ("sf424c",),
        (test_file,),
    )


def test_multiple_exact_mapped_form_owners_require_full_ci():
    cd511_test = "api/tests/src/form_schema/form_spec/test_cd511_portable.py"
    sf424c_test = "api/tests/src/form_schema/form_spec/test_sf424c_portable.py"
    sf424c_registration_test = "api/tests/src/form_schema/form_spec/test_registrations.py"

    classification = classify_change(
        [Change("M", sf424c_test), Change("M", cd511_test)],
        portable_ci_map={
            "sf424c": (sf424c_test, sf424c_registration_test),
            "cd511": (cd511_test,),
        },
    )

    assert classification.tier == TIER_FULL
    assert classification.form_ids == ()


def test_unknown_test_only_change_requires_full_ci():
    mapped_test = "api/tests/src/form_schema/form_spec/test_sf424c_portable.py"

    classification = classify_change(
        [Change("M", "api/tests/src/form_schema/form_spec/test_unknown_portable.py")],
        portable_ci_map={"sf424c": (mapped_test,)},
    )

    assert classification.tier == TIER_FULL
    assert classification.form_ids == ()


def test_ambiguous_reverse_test_mapping_requires_full_ci():
    shared_test = "api/tests/src/form_schema/form_spec/test_registrations.py"

    classification = classify_change(
        [Change("M", shared_test)],
        portable_ci_map={
            "cd511": (shared_test,),
            "sf424c": (shared_test,),
        },
    )

    assert classification.tier == TIER_FULL
    assert classification.form_ids == ()


def test_deleted_mapped_test_requires_full_ci():
    mapped_test = "api/tests/src/form_schema/form_spec/test_sf424c_portable.py"

    classification = classify_change(
        [Change("D", mapped_test)],
        portable_ci_map={"sf424c": (mapped_test,)},
    )

    assert classification.tier == TIER_FULL
    assert "deletions require full CI" in classification.reason


@pytest.mark.parametrize(
    "mixed_path",
    [
        "api/src/form_schema/form_spec/loader.py",
        "api/src/form_schema/form_spec/registrations.json",
        "api/src/form_schema/form_spec/artifacts/artifact-manifest.json",
        "api/src/services/xml_generation/xsds/SF424C-V2.0.xsd",
        "frontend/src/components/apply-form/Form.tsx",
        ".github/workflows/ci-api.yml",
    ],
)
def test_mapped_test_mixed_with_any_nonmapped_path_requires_full_ci(mixed_path: str):
    mapped_test = "api/tests/src/form_schema/form_spec/test_sf424c_portable.py"

    classification = classify_change(
        [Change("M", mapped_test), Change("M", mixed_path)],
        portable_ci_map={"sf424c": (mapped_test,)},
    )

    assert classification.tier == TIER_FULL
    assert classification.form_ids == ()


def test_frontend_evidence_map_is_exact_and_pilots_only_two_forms():
    mapping = load_frontend_evidence_map()

    assert set(mapping) == {"phs398-cover-page-supplement", "sbir-sttr-information"}
    assert mapping["phs398-cover-page-supplement"] == (
        "frontend/src/utils/applyForm/__fixtures__/phs398-cover-page-supplement-ui-schema.json",
        "frontend/src/utils/applyForm/phs398CoverPageSupplementConditions.test.ts",
    )
    assert mapping["sbir-sttr-information"] == (
        "api/tests/src/form_schema/form_spec/sbir_sttr_projected_conditions.json",
        "frontend/src/utils/applyForm/sbirSttrInformationConditions.test.ts",
    )
    assert set(mapping) < set(load_portable_ci_map())


def test_sbir_mixed_api_and_frontend_evidence_uses_one_focused_form():
    classification = classify_change(
        [
            Change(
                "M",
                "api/tests/src/form_schema/form_spec/test_sbir_sttr_information_portable.py",
            ),
            Change(
                "M",
                "api/tests/src/form_schema/form_spec/sbir_sttr_projected_conditions.json",
            ),
            Change(
                "M",
                "frontend/src/utils/applyForm/sbirSttrInformationConditions.test.ts",
            ),
        ]
    )

    assert classification.tier == TIER_PORTABLE_FOCUSED
    assert classification.form_ids == ("sbir-sttr-information",)
    assert classification.test_files == (
        "api/tests/src/form_schema/form_spec/test_sbir_sttr_information_portable.py",
    )
    assert classification.frontend_evidence_files == (
        "api/tests/src/form_schema/form_spec/sbir_sttr_projected_conditions.json",
        "frontend/src/utils/applyForm/sbirSttrInformationConditions.test.ts",
    )


def test_cover_artifact_api_test_and_frontend_evidence_use_one_focused_form():
    classification = classify_change(
        [
            Change("M", "api/src/form_schema/form_spec/artifacts/artifact-manifest.json"),
            Change(
                "M",
                "api/src/form_schema/form_spec/artifacts/forms/"
                "phs398-cover-page-supplement/ui.json",
            ),
            Change(
                "M",
                "api/tests/src/form_schema/form_spec/"
                "test_phs398_cover_page_supplement_portable.py",
            ),
            Change(
                "M",
                "frontend/src/utils/applyForm/__fixtures__/"
                "phs398-cover-page-supplement-ui-schema.json",
            ),
            Change(
                "M",
                "frontend/src/utils/applyForm/" "phs398CoverPageSupplementConditions.test.ts",
            ),
        ]
    )

    assert classification.tier == TIER_PORTABLE_FOCUSED
    assert classification.form_ids == ("phs398-cover-page-supplement",)
    assert classification.test_files == (
        "api/tests/src/form_schema/form_spec/" "test_phs398_cover_page_supplement_portable.py",
        "api/tests/src/form_schema/form_spec/test_registrations.py",
    )
    assert classification.frontend_evidence_files == (
        "frontend/src/utils/applyForm/__fixtures__/" "phs398-cover-page-supplement-ui-schema.json",
        "frontend/src/utils/applyForm/phs398CoverPageSupplementConditions.test.ts",
    )


@pytest.mark.parametrize(
    "path",
    [
        "frontend/src/utils/applyForm/unknownConditions.test.ts",
        "frontend/src/utils/applyForm/__fixtures__/unknown.json",
        "frontend/src/components/apply-form/Form.tsx",
        "api/src/form_schema/form_spec/loader.py",
        "api/src/form_schema/form_spec/registrations.json",
        "api/src/form_schema/form_spec/artifacts/question-bank/generics/email/schema.json",
        "api/src/form_schema/form_spec/artifacts/governance/parity.json",
        "api/src/services/xml_generation/xsds/SBIR-V1.0.xsd",
        ".github/workflows/ci-api.yml",
        "api/src/form_schema/form_spec/portable-form-frontend-evidence-map.json",
    ],
)
def test_frontend_evidence_mixed_with_unknown_or_shared_path_requires_full_ci(path: str):
    classification = classify_change(
        [
            Change(
                "M",
                "frontend/src/utils/applyForm/sbirSttrInformationConditions.test.ts",
            ),
            Change("M", path),
        ]
    )

    assert classification.tier == TIER_FULL
    assert classification.form_ids == ()


def test_frontend_evidence_deletion_requires_full_ci():
    classification = classify_change(
        [
            Change(
                "D",
                "frontend/src/utils/applyForm/sbirSttrInformationConditions.test.ts",
            )
        ]
    )

    assert classification.tier == TIER_FULL
    assert "deletions require full CI" in classification.reason


def test_ambiguous_frontend_evidence_owner_requires_full_ci():
    shared_frontend_test = "frontend/src/utils/applyForm/sharedConditions.test.ts"
    sbir_api_test = "api/tests/src/form_schema/form_spec/test_sbir_sttr_information_portable.py"
    cover_api_test = (
        "api/tests/src/form_schema/form_spec/" "test_phs398_cover_page_supplement_portable.py"
    )

    classification = classify_change(
        [Change("M", shared_frontend_test)],
        portable_ci_map={
            "sbir-sttr-information": (sbir_api_test,),
            "phs398-cover-page-supplement": (cover_api_test,),
        },
        frontend_evidence_map={
            "sbir-sttr-information": (shared_frontend_test,),
            "phs398-cover-page-supplement": (shared_frontend_test,),
        },
    )

    assert classification.tier == TIER_FULL
    assert classification.form_ids == ()


def test_api_and_frontend_evidence_for_different_forms_requires_full_ci():
    classification = classify_change(
        [
            Change(
                "M", "api/tests/src/form_schema/form_spec/test_sbir_sttr_information_portable.py"
            ),
            Change(
                "M",
                "frontend/src/utils/applyForm/" "phs398CoverPageSupplementConditions.test.ts",
            ),
        ]
    )

    assert classification.tier == TIER_FULL
    assert classification.form_ids == ()


def test_frontend_evidence_for_different_form_than_artifact_requires_full_ci():
    classification = classify_change(
        [
            Change(
                "M",
                "api/src/form_schema/form_spec/artifacts/forms/" "sbir-sttr-information/ui.json",
            ),
            Change(
                "M",
                "frontend/src/utils/applyForm/" "phs398CoverPageSupplementConditions.test.ts",
            ),
        ]
    )

    assert classification.tier == TIER_FULL
    assert classification.form_ids == ()


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"contract": "wrong", "forms": {}}, "unsupported"),
        (
            {
                "contract": checker.FRONTEND_EVIDENCE_MAP_CONTRACT,
                "forms": {"example": ["frontend/src/example.ts"]},
            },
            "invalid evidence",
        ),
        (
            {
                "contract": checker.FRONTEND_EVIDENCE_MAP_CONTRACT,
                "forms": {
                    "example": [
                        "frontend/src/example.test.ts",
                        "frontend/src/example.test.ts",
                    ]
                },
            },
            "duplicate evidence",
        ),
    ],
)
def test_frontend_evidence_map_rejects_invalid_contract_paths_and_duplicates(
    tmp_path: Path, payload: dict, message: str
):
    evidence_map = tmp_path / "frontend-evidence.json"
    evidence_map.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match=message):
        load_frontend_evidence_map(evidence_map)


def test_frontend_evidence_map_rejects_missing_files(tmp_path: Path, monkeypatch):
    evidence_map = tmp_path / "frontend-evidence.json"
    evidence_map.write_text(
        json.dumps(
            {
                "contract": checker.FRONTEND_EVIDENCE_MAP_CONTRACT,
                "forms": {"example": ["frontend/src/example.test.ts"]},
            }
        )
    )
    monkeypatch.setattr(checker, "REPOSITORY_ROOT", tmp_path)

    with pytest.raises(ValueError, match="missing evidence"):
        load_frontend_evidence_map(evidence_map)


def test_frontend_evidence_form_without_api_test_mapping_is_configuration_error():
    with pytest.raises(ValueError, match="forms without API tests.*frontend-only"):
        classify_change(
            [Change("M", "frontend/src/frontendOnly.test.ts")],
            portable_ci_map={"api-only": ("api/tests/test_api_only.py",)},
            frontend_evidence_map={"frontend-only": ("frontend/src/frontendOnly.test.ts",)},
        )


def test_focused_verification_allows_unchanged_artifacts_only_when_explicit(monkeypatch):
    manifest = json.loads(ARTIFACT_MANIFEST.read_text())
    monkeypatch.setattr(checker, "manifest_at", lambda _revision: manifest)
    monkeypatch.setattr(checker, "verify_artifact_selection", lambda **_kwargs: manifest)
    monkeypatch.setattr(checker, "verify_artifact_xsds", lambda **_kwargs: None)

    with pytest.raises(ValueError, match="requires a changed selected form artifact"):
        checker.verify_focused_forms("base-revision", ("sf424c",))

    receipt = checker.verify_focused_forms(
        "base-revision", ("sf424c",), allow_unchanged_artifacts=True
    )
    assert receipt["focusedForms"] == ["sf424c"]
    assert receipt["changedArtifacts"] == []
