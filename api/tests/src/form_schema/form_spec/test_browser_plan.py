import json
import os
import subprocess
import sys

import pytest

from src.form_schema.form_spec.browser_plan import (
    PLAN_CONTRACT,
    SEED_COMPETITION_ID,
    SEED_OPPORTUNITY_ID,
    _resolve_schema_pointer,
    browser_seed_ids,
    build_browser_plan,
)
from src.form_schema.form_spec.preview import BROWSER_FORM_IDS, banked_form_ids, preview_form_id


@pytest.fixture(autouse=True)
def _enable_portable_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("ENABLE_PORTABLE_FORM_PREVIEW", "true")


def test_browser_plan_follows_live_manifest_and_discovers_capabilities() -> None:
    plan = build_browser_plan()

    assert plan["contract"] == PLAN_CONTRACT
    assert [form["portableFormId"] for form in plan["forms"]] == list(banked_form_ids())
    assert [form["previewFormId"] for form in plan["forms"]] == [
        str(preview_form_id(form_id)) for form_id in banked_form_ids()
    ]
    assert all(form["artifactDigests"] for form in plan["forms"])
    assert all(form["counts"]["uiNodes"] > 0 for form in plan["forms"])

    capability_names = {
        capability
        for form in plan["forms"]
        for capability, declaration in form["capabilities"].items()
        if declaration["applicability"] == "applicable"
    }
    assert capability_names == {
        "attachment",
        "calculation",
        "conditional",
        "editableScalar",
        "readOnly",
        "repeater",
        "requiredField",
        "schemaImplication",
        "staticContent",
    }


@pytest.mark.parametrize(
    "form_id",
    [
        "sf424b",
        "mandatory-sf424b",
        "individual-sf424b",
        "sf424d",
        "mandatory-sf424d",
        "individual-sf424d",
    ],
)
def test_browser_plan_exposes_assurance_policy_content_without_form_logic(
    monkeypatch: pytest.MonkeyPatch,
    form_id: str,
) -> None:
    monkeypatch.setenv(BROWSER_FORM_IDS, form_id)

    capability = build_browser_plan()["forms"][0]["capabilities"]["staticContent"]

    assert capability["applicability"] == "applicable"
    assert [declaration["sectionName"] for declaration in capability["declarations"]] == (
        ["directions", "acknowledgement"]
        if form_id.endswith("sf424b") or form_id == "sf424b"
        else ["burden_statement", "directions"]
    )
    assert all(len(declaration["sha256"]) == 64 for declaration in capability["declarations"])
    assert all(declaration["paragraphs"] for declaration in capability["declarations"])


@pytest.mark.parametrize("form_id", ["sf424", "sf424-short"])
def test_browser_plan_can_target_a_family_member_without_a_second_harness(
    monkeypatch: pytest.MonkeyPatch, form_id: str
) -> None:
    monkeypatch.setenv(BROWSER_FORM_IDS, form_id)

    plan = build_browser_plan()

    assert [form["portableFormId"] for form in plan["forms"]] == [form_id]
    assert plan["forms"][0]["previewFormId"] == str(preview_form_id(form_id))
    assert plan["consumerSeed"] == {
        "opportunityId": browser_seed_ids((form_id,))[0],
        "competitionId": browser_seed_ids((form_id,))[1],
    }


def test_browser_plan_does_not_treat_prepopulated_fields_as_editable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BROWSER_FORM_IDS, "sf424-short")

    capabilities = build_browser_plan()["forms"][0]["capabilities"]
    editable_definitions = {
        declaration["definition"] for declaration in capabilities["editableScalar"]["declarations"]
    }

    assert "/properties/agency_name" not in editable_definitions
    assert "/properties/assistance_listing_number" not in editable_definitions
    assert "/properties/organization_name" in editable_definitions


def test_browser_plan_classifies_attachment_controls_separately_from_editable_scalars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BROWSER_FORM_IDS, "attachment-form")

    capabilities = build_browser_plan()["forms"][0]["capabilities"]

    assert capabilities["editableScalar"] == {
        "applicability": "not_applicable",
        "declarations": [],
        "reason": "no editable scalar is declared",
    }
    assert capabilities["attachment"]["applicability"] == "applicable"
    assert {
        declaration["definition"]
        for declaration in capabilities["attachment"]["declarations"]
        if "definition" in declaration
    } == {f"/properties/att{index}" for index in range(1, 16)}


def test_browser_plan_exposes_modular_budget_review_surfaces_without_form_logic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BROWSER_FORM_IDS, "phs398-modular-budget")

    form = build_browser_plan()["forms"][0]
    capabilities = form["capabilities"]

    assert form["counts"] == {"uiNodes": 26, "uiFields": 23, "schemaFields": 26}
    assert capabilities["repeater"]["declarations"] == [
        {"definition": "/properties/periods", "name": "periods"},
        {
            "definition": (
                "/properties/periods/items/properties/indirect_costs/"
                "properties/indirect_cost_items"
            ),
            "name": "indirect_cost_items",
        },
    ]
    assert len(capabilities["attachment"]["declarations"]) == 6
    assert sorted(
        declaration["declaration"]["order"]
        for declaration in capabilities["calculation"]["declarations"]
    ) == list(range(1, 9))
    calculated_paths = {
        declaration["rulePath"] for declaration in capabilities["calculation"]["declarations"]
    }
    editable_paths = {
        declaration["definition"] for declaration in capabilities["editableScalar"]["declarations"]
    }
    assert calculated_paths.isdisjoint(editable_paths)
    assert len(capabilities["readOnly"]["declarations"]) == 8


def test_browser_plan_discovers_multifield_editable_surface(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BROWSER_FORM_IDS, "sf424a")

    form = build_browser_plan()["forms"][0]

    assert form["counts"]["uiFields"] == 6
    assert form["stablePaths"]["uiDefinitions"] == [
        "/properties/activity_line_items",
        "/properties/confirmation",
        "/properties/direct_charges_explanation",
        "/properties/forecasted_cash_needs",
        "/properties/indirect_charges_explanation",
        "/properties/remarks",
        "/properties/total_budget_categories",
        "/properties/total_budget_summary",
        "/properties/total_federal_fund_estimates",
        "/properties/total_non_federal_resources",
    ]
    assert form["capabilities"]["editableScalar"] == {
        "applicability": "applicable",
        "declarations": [
            {"definition": "/properties/activity_line_items"},
            {"definition": "/properties/total_budget_summary"},
            {"definition": "/properties/activity_line_items"},
            {"definition": "/properties/total_budget_categories"},
            {"definition": "/properties/activity_line_items"},
            {"definition": "/properties/total_non_federal_resources"},
            {"definition": "/properties/forecasted_cash_needs"},
            {"definition": "/properties/activity_line_items"},
            {"definition": "/properties/total_federal_fund_estimates"},
            {"definition": "/properties/direct_charges_explanation"},
            {"definition": "/properties/indirect_charges_explanation"},
            {"definition": "/properties/remarks"},
            {"definition": "/properties/confirmation"},
        ],
        "reason": None,
    }


def test_browser_plan_preserves_ordinary_field_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(BROWSER_FORM_IDS, "sf424")

    form = build_browser_plan()["forms"][0]

    assert form["counts"]["uiFields"] == 66
    declarations = form["capabilities"]["editableScalar"]["declarations"]
    definitions = {declaration["definition"] for declaration in declarations}
    assert "/properties/submission_type" in definitions
    assert "/properties/organization_name" in definitions
    assert "/properties/funding_total" not in definitions
    assert all(
        list(declaration) == ["definition"] and isinstance(declaration["definition"], str)
        for declaration in declarations
    )


@pytest.mark.parametrize(
    ("form_id", "prefix"),
    [
        ("rr-budget", "/budget_year/*"),
        ("rr-subaward-budget", "/budget_attachments/*/budget_year/*"),
    ],
)
def test_browser_plan_projects_budget_attachment_implications_without_form_logic(
    monkeypatch: pytest.MonkeyPatch,
    form_id: str,
    prefix: str,
) -> None:
    monkeypatch.setenv(BROWSER_FORM_IDS, form_id)

    capability = build_browser_plan()["forms"][0]["capabilities"]["schemaImplication"]

    assert capability["applicability"] == "applicable"
    assert len(capability["declarations"]) == 4
    assert {
        (
            declaration["trigger"]["responsePath"],
            declaration["consequence"]["responsePath"],
        )
        for declaration in capability["declarations"]
    } == {
        (
            f"{prefix}/equipment/total_fund_for_attached_equipment",
            f"{prefix}/equipment/additional_equipments_attachment",
        ),
        (
            f"{prefix}/equipment/additional_equipments_attachment",
            f"{prefix}/equipment/total_fund_for_attached_equipment",
        ),
        (
            f"{prefix}/key_persons/total_fund_for_attached_key_persons",
            f"{prefix}/key_persons/attached_key_persons",
        ),
        (
            f"{prefix}/key_persons/attached_key_persons",
            f"{prefix}/key_persons/total_fund_for_attached_key_persons",
        ),
    }
    patterned_triggers = [
        declaration
        for declaration in capability["declarations"]
        if declaration["trigger"]["constraint"] is not None
    ]
    assert len(patterned_triggers) == 2
    assert all(
        declaration["trigger"]["constraint"] == {"pattern": "^(?=.*[1-9])\\d+(?:\\.\\d+)?$"}
        for declaration in patterned_triggers
    )


def test_browser_seed_ids_preserve_full_catalog_and_isolate_canaries() -> None:
    assert browser_seed_ids(banked_form_ids()) == (SEED_OPPORTUNITY_ID, SEED_COMPETITION_ID)
    assert browser_seed_ids(("sf424",)) == browser_seed_ids(("sf424",))
    assert browser_seed_ids(("sf424",)) != browser_seed_ids(("sf424a",))


def test_browser_plan_cli_writes_json_and_structured_stdout(tmp_path) -> None:
    output = tmp_path / "plan.json"
    result = subprocess.run(
        [
            sys.executable,
            "bin/build_portable_browser_plan.py",
            "--out",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "ENVIRONMENT": "test",
            "ENABLE_PORTABLE_FORM_PREVIEW": "true",
        },
    )

    assert result.returncode == 0
    assert result.stdout.startswith("browser_plan:\n  contract:")
    assert result.stderr == ""
    assert json.loads(output.read_text())["contract"] == PLAN_CONTRACT


@pytest.mark.parametrize("form_id", ["sf424", "sf424-short"])
def test_browser_plan_cli_honors_one_form_selection(tmp_path, form_id: str) -> None:
    output = tmp_path / "plan.json"
    result = subprocess.run(
        [sys.executable, "bin/build_portable_browser_plan.py", "--out", str(output)],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "ENVIRONMENT": "test",
            "ENABLE_PORTABLE_FORM_PREVIEW": "true",
            BROWSER_FORM_IDS: form_id,
        },
    )

    assert result.returncode == 0
    assert "forms: 1" in result.stdout
    assert [form["portableFormId"] for form in json.loads(output.read_text())["forms"]] == [form_id]


def test_browser_plan_cli_rejects_unknown_flags() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "bin/build_portable_browser_plan.py",
            "--out",
            "unused.json",
            "--unknown",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "unrecognized arguments: --unknown" in result.stderr


def test_browser_plan_cli_requires_preview_gate(tmp_path) -> None:
    environment = dict(os.environ)
    environment.pop("ENVIRONMENT", None)
    environment.pop("ENABLE_PORTABLE_FORM_PREVIEW", None)
    result = subprocess.run(
        [
            sys.executable,
            "bin/build_portable_browser_plan.py",
            "--out",
            str(tmp_path / "plan.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "ENVIRONMENT=local|test|dev" in result.stderr


def test_browser_plan_fails_closed_without_preview_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENABLE_PORTABLE_FORM_PREVIEW")

    with pytest.raises(ValueError, match="ENVIRONMENT=local\\|test\\|dev"):
        build_browser_plan()


def test_schema_pointer_resolution_fails_closed() -> None:
    schema = {"properties": {"name": {"type": "string"}}}

    assert _resolve_schema_pointer(schema, "/properties/name") == {"type": "string"}
    with pytest.raises(ValueError, match="does not resolve"):
        _resolve_schema_pointer(schema, "/properties/missing")
