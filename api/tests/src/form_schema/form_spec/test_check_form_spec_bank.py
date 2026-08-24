from bin.check_form_spec_bank import Change, classify


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


def test_existing_artifact_or_xsd_modification_requires_full_ci():
    for path in (
        "api/src/form_schema/form_spec/artifacts/forms/sf424/schema.json",
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
