"""PHS Human Subjects technical handoff evidence.

The form remains an unregistered preview with proposed semantics. These tests
exercise only its banked package through Simpler's generic adapter, rule, and
XML paths. Source-bound conditions and unresolved calculations stay explicit.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
import xmlschema
from lxml import etree

from src.db.models.competition_models import ApplicationForm
from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import _load_banked_form
from src.form_schema.form_spec.preview import build_preview_form
from src.form_schema.form_spec.registrations import REGISTRATIONS
from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.utils.attachment_mapping import AttachmentInfo

FORM_ID = "phs-human-subjects"
FORM_ROOT = ARTIFACTS / "forms" / FORM_ID
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
FORM_XSD = "PHSHumanSubjectsAndClinicalTrialsInfo_3_0-V3.0.xsd"
FORM_NAMESPACE = "http://apply.grants.gov/forms/PHSHumanSubjectsAndClinicalTrialsInfo_3_0-V3.0"
STUDY_NAMESPACE = "http://apply.grants.gov/forms/HumanSubjectStudy_3_0-V3.0"
ATTACHMENT_NAMESPACE = "http://apply.grants.gov/system/Attachments-V1.0"
PINNED_XSDS = {
    FORM_XSD: "29d859de80cc9febbd1599c28f5db9a3ec82bff26a4d32f4dbbc372effb56bf3",
    "HumanSubjectStudy_3_0-V3.0.xsd": (
        "799205dea5eddcf13f926cc39d5fc7de27c6a6cdcc68eff4d49e1b629d4351cf"
    ),
    "Attachments-V1.0.xsd": ("ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d"),
    "Global-V1.0.xsd": ("4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb"),
    "GlobalLibrary-V2.0.xsd": ("ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8"),
    "UniversalCodes-V2.0.xsd": ("78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a"),
}
ATTACHMENT_PATHS = (
    "specimens_explanation",
    "other_requested_information",
    "studies[].population_characteristics.inclusion_across_lifespan",
    "studies[].population_characteristics.inclusion_women_minorities",
    "studies[].population_characteristics.recruitment_retention_plan",
    "studies[].population_characteristics.study_timeline",
    "studies[].protection_monitoring_plans.protection_of_human_subjects",
    "studies[].protection_monitoring_plans.single_irb_plan",
    "studies[].protection_monitoring_plans.data_safety_monitoring_plan",
    "studies[].protection_monitoring_plans.study_team_structure",
    "studies[].protocol_synopsis.statistical_design_and_power",
    "studies[].protocol_synopsis.investigational_product_availability",
    "studies[].protocol_synopsis.dissemination_plan",
    "studies[].other_clinical_trial_attachments[]",
    "delayed_onset_studies[].justification",
)
ATTACHMENT_IDS = {
    path: f"00000000-0000-0000-0000-{index:012d}"
    for index, path in enumerate(ATTACHMENT_PATHS, start=1)
}
ATTACHMENT_VALIDATION_FIELDS = {
    "specimens_explanation": "$.specimens_explanation",
    "other_requested_information": "$.other_requested_information",
    "studies[].population_characteristics.inclusion_across_lifespan": (
        "$.studies[0].population_characteristics.inclusion_across_lifespan"
    ),
    "studies[].population_characteristics.inclusion_women_minorities": (
        "$.studies[0].population_characteristics.inclusion_women_minorities"
    ),
    "studies[].population_characteristics.recruitment_retention_plan": (
        "$.studies[0].population_characteristics.recruitment_retention_plan"
    ),
    "studies[].population_characteristics.study_timeline": (
        "$.studies[0].population_characteristics.study_timeline"
    ),
    "studies[].protection_monitoring_plans.protection_of_human_subjects": (
        "$.studies[0].protection_monitoring_plans.protection_of_human_subjects"
    ),
    "studies[].protection_monitoring_plans.single_irb_plan": (
        "$.studies[0].protection_monitoring_plans.single_irb_plan"
    ),
    "studies[].protection_monitoring_plans.data_safety_monitoring_plan": (
        "$.studies[0].protection_monitoring_plans.data_safety_monitoring_plan"
    ),
    "studies[].protection_monitoring_plans.study_team_structure": (
        "$.studies[0].protection_monitoring_plans.study_team_structure"
    ),
    "studies[].protocol_synopsis.statistical_design_and_power": (
        "$.studies[0].protocol_synopsis.statistical_design_and_power"
    ),
    "studies[].protocol_synopsis.investigational_product_availability": (
        "$.studies[0].protocol_synopsis.investigational_product_availability"
    ),
    "studies[].protocol_synopsis.dissemination_plan": (
        "$.studies[0].protocol_synopsis.dissemination_plan"
    ),
    "studies[].other_clinical_trial_attachments[]": (
        "$.studies[0].other_clinical_trial_attachments[0]"
    ),
    "delayed_onset_studies[].justification": "$.delayed_onset_studies[0].justification",
}
SOURCE_BOUND_CONDITIONS = (
    ("1-07", "/exemptFromFederalRegulations"),
    ("1-08", "/exemptions"),
    ("1-15-1", "/studies"),
    ("1-15-2", "/studies"),
    ("1-16", "/studies"),
    ("1-19-1", "/delayedOnsetStudies"),
    ("1-19-2", "/delayedOnsetStudies/[]/studyTitle"),
    ("1-19-3", "/delayedOnsetStudies/[]/anticipatedClinicalTrial"),
    ("1-19-4", "/delayedOnsetStudies/[]/justification"),
)
EXPECTED_SOURCE_RECORDS = (
    (
        "phs-human-subjects-parent-xsd-v3-0",
        "xsd",
        "https://apply07.grants.gov/apply/forms/schemas/PHSHumanSubjectsAndClinicalTrialsInfo_3_0-V3.0.xsd",
        "3.0",
        "29d859de80cc9febbd1599c28f5db9a3ec82bff26a4d32f4dbbc372effb56bf3",
    ),
    (
        "human-subject-study-xsd-v3-0",
        "xsd",
        "https://apply07.grants.gov/apply/forms/schemas/HumanSubjectStudy_3_0-V3.0.xsd",
        "3.0",
        "799205dea5eddcf13f926cc39d5fc7de27c6a6cdcc68eff4d49e1b629d4351cf",
    ),
    (
        "attachments-xsd-v1-0",
        "xsd",
        "https://apply07.grants.gov/apply/system/schemas/Attachments-V1.0.xsd",
        "1.0",
        "ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d",
    ),
    (
        "global-xsd-v1-0",
        "xsd",
        "https://apply07.grants.gov/apply/system/schemas/Global-V1.0.xsd",
        "1.0",
        "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb",
    ),
    (
        "global-library-xsd-v2-0",
        "xsd",
        "https://apply07.grants.gov/apply/system/schemas/GlobalLibrary-V2.0.xsd",
        "2.0",
        "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8",
    ),
    (
        "universal-codes-xsd-v2-0",
        "xsd",
        "https://apply07.grants.gov/apply/system/schemas/UniversalCodes-V2.0.xsd",
        "2.0",
        "78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a",
    ),
    (
        "phs-human-subjects-dat-f705",
        "dat",
        "https://apply07.grants.gov/apply/forms/sample/PHSHumanSubjectsAndClinicalTrialsInfo_3_0-V3.0_F705.xls",
        "3.0",
        "b02d18779d7eca89ca552056cb6d62d001dbaebd366f7b67b93b4dc7667c4dbd",
    ),
    (
        "phs-human-subjects-readonly-pdf-v3-0",
        "pdf",
        "https://apply07.grants.gov/apply/forms/readonly/PHSHumanSubjectsAndClinicalTrialsInfo_3_0-V3.0.pdf",
        "3.0",
        "b56ab18e6b9c6df8bcc49b3ba1a5ae8cbfa8f2684646a6b927f5ac021d7c3d4a",
    ),
    (
        "phs-human-subjects-xfa-pdf-v3-0",
        "pdf",
        "https://apply07.grants.gov/apply/forms/sample/PHSHumanSubjectsAndClinicalTrialsInfo_3_0-V3.0.pdf",
        "3.0",
        "1b478db394ebe672d5452ed8ddd59493a30fc566622e68d281261487c87f267e",
    ),
    (
        "nih-forms-i-general-application-guide",
        "instructions",
        "https://grants.nih.gov/grants/how-to-apply-application-guide/forms-i/general-forms-i.pdf",
        "Forms I",
        "97b323be4e8ca90a0a5f69fe46b7762e45188088dc220efd846e008df3c13588",
    ),
)


def read(relative: str) -> Any:
    return json.loads((FORM_ROOT / relative).read_text())


def walk(value: object) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def enrollment_coordinate_mappings(
    fields: dict[str, Any],
    canonical: tuple[str, ...] = (),
    wire: tuple[str, ...] = (),
) -> set[tuple[str, str]]:
    coordinate_elements = {
        "AmericanIndian",
        "Asian",
        "Hawaiian",
        "Black",
        "White",
        "MultipleRace",
        "UnknownRace",
        "Total",
    }
    mappings: set[tuple[str, str]] = set()
    for source_name, node in fields.items():
        canonical_path = canonical + (source_name,)
        element = node.get("element")
        wire_path = wire + ((element,) if element else ())
        if node.get("kind") == "value" and element in coordinate_elements:
            mappings.add(("/".join(canonical_path), "/".join(wire_path)))
        mappings.update(
            enrollment_coordinate_mappings(node.get("fields", {}), canonical_path, wire_path)
        )
    return mappings


def expected_enrollment_coordinate_mappings() -> set[tuple[str, str]]:
    race_names = {
        "americanIndianAlaskaNative": "AmericanIndian",
        "asian": "Asian",
        "nativeHawaiianPacificIslander": "Hawaiian",
        "blackAfricanAmerican": "Black",
        "white": "White",
        "moreThanOneRace": "MultipleRace",
    }
    planned_races = {**race_names, "total": "Total"}
    cumulative_races = {
        **race_names,
        "unknownNotReported": "UnknownRace",
        "total": "Total",
    }
    planned_ethnicities = {
        "notHispanicLatino": "NotHispanic",
        "hispanicLatino": "Hispanic",
    }
    cumulative_ethnicities = {
        **planned_ethnicities,
        "unknownNotReportedEthnicity": "UnknownEthnicity",
    }
    planned_sexes = {"female": "Female", "male": "Male"}
    cumulative_sexes = {**planned_sexes, "unknownNotReportedSex": "UnknownGender"}
    expected = {
        (
            f"planned/{ethnicity}/{sex}/{race}",
            f"Planned/{wire_ethnicity}/{wire_sex}/{wire_race}",
        )
        for ethnicity, wire_ethnicity in planned_ethnicities.items()
        for sex, wire_sex in planned_sexes.items()
        for race, wire_race in planned_races.items()
    }
    expected.update(
        (f"planned/total/{race}", f"Planned/Total/{wire_race}")
        for race, wire_race in planned_races.items()
    )
    expected.update(
        (
            f"cumulativeActual/{ethnicity}/{sex}/{race}",
            f"Cumulative/{wire_ethnicity}/{wire_sex}/{wire_race}",
        )
        for ethnicity, wire_ethnicity in cumulative_ethnicities.items()
        for sex, wire_sex in cumulative_sexes.items()
        for race, wire_race in cumulative_races.items()
    )
    expected.update(
        (f"cumulativeActual/total/{race}", f"Cumulative/Total/{wire_race}")
        for race, wire_race in cumulative_races.items()
    )
    return expected


def representative_response() -> dict[str, object]:
    study = {
        "study_title": "Structured study",
        "exempt_from_federal_regulations": "N: No",
        "exemption_numbers": ["E1", "E2"],
        "clinical_trial_questionnaire": {
            "human_participants": "Y: Yes",
            "prospectively_assigned_intervention": "Y: Yes",
            "evaluates_intervention": "Y: Yes",
            "health_related_outcome": "Y: Yes",
        },
        "population_characteristics": {
            "conditions_or_focus": ["Condition A", "Condition B"],
            "inclusion_across_lifespan": ATTACHMENT_IDS[
                "studies[].population_characteristics.inclusion_across_lifespan"
            ],
            "inclusion_women_minorities": ATTACHMENT_IDS[
                "studies[].population_characteristics.inclusion_women_minorities"
            ],
            "recruitment_retention_plan": ATTACHMENT_IDS[
                "studies[].population_characteristics.recruitment_retention_plan"
            ],
            "study_timeline": ATTACHMENT_IDS["studies[].population_characteristics.study_timeline"],
            "inclusion_enrollment_reports": [
                {
                    "title": "Enrollment report",
                    "uses_existing_dataset_or_resource": "N: No",
                    "location_type": "Domestic",
                    "enrollment_countries": ["USA: UNITED STATES", "CAN: CANADA"],
                    "planned": {
                        "not_hispanic_latino": {"female": {"asian": 7}},
                        "total": {"asian": 7},
                    },
                    "cumulative_actual": {
                        "unknown_not_reported_ethnicity": {
                            "unknown_not_reported_sex": {"unknown_not_reported": 3}
                        },
                        "total": {"unknown_not_reported": 3},
                    },
                }
            ],
        },
        "protection_monitoring_plans": {
            "protection_of_human_subjects": ATTACHMENT_IDS[
                "studies[].protection_monitoring_plans.protection_of_human_subjects"
            ],
            "single_irb_plan": ATTACHMENT_IDS[
                "studies[].protection_monitoring_plans.single_irb_plan"
            ],
            "data_safety_monitoring_plan": ATTACHMENT_IDS[
                "studies[].protection_monitoring_plans.data_safety_monitoring_plan"
            ],
            "study_team_structure": ATTACHMENT_IDS[
                "studies[].protection_monitoring_plans.study_team_structure"
            ],
        },
        "protocol_synopsis": {
            "statistical_design_and_power": ATTACHMENT_IDS[
                "studies[].protocol_synopsis.statistical_design_and_power"
            ],
            "investigational_product_availability": ATTACHMENT_IDS[
                "studies[].protocol_synopsis.investigational_product_availability"
            ],
            "dissemination_plan": ATTACHMENT_IDS["studies[].protocol_synopsis.dissemination_plan"],
        },
        "other_clinical_trial_attachments": [
            ATTACHMENT_IDS["studies[].other_clinical_trial_attachments[]"]
        ],
    }
    return {
        "involves_human_specimens_or_data": "N: No",
        "specimens_explanation": ATTACHMENT_IDS["specimens_explanation"],
        "involves_human_subjects": "Y: Yes",
        "exempt_from_federal_regulations": "Y: Yes",
        "exemptions": ["E1", "E2"],
        "other_requested_information": ATTACHMENT_IDS["other_requested_information"],
        "studies": [study],
        "delayed_onset_studies": [
            {
                "study_title": "Delayed study",
                "anticipated_clinical_trial": "N: No",
                "justification": ATTACHMENT_IDS["delayed_onset_studies[].justification"],
            }
        ],
    }


def attachment_mapping() -> dict[str, AttachmentInfo]:
    return {
        attachment_id: AttachmentInfo(
            filename=f"evidence-{index:02d}.pdf",
            mime_type="application/pdf",
            file_location=f"./attachments/evidence-{index:02d}.pdf",
            hash_value="YWJjZA==",
        )
        for index, attachment_id in enumerate(ATTACHMENT_IDS.values(), start=1)
    }


def rule_context(available_ids: set[str]) -> JsonRuleContext:
    projected = _load_banked_form(FORM_ID, project_xml=False)
    application_form = cast(
        ApplicationForm,
        SimpleNamespace(
            application_response=representative_response(),
            application=SimpleNamespace(
                application_attachments=[
                    SimpleNamespace(application_attachment_id=attachment_id)
                    for attachment_id in available_ids
                ]
            ),
            application_form_id="phs-human-subjects-rule-test",
            form_id="phs-human-subjects-preview",
            form=projected,
        ),
    )
    context = JsonRuleContext(
        application_form,
        JsonRuleConfig(
            do_pre_population=False,
            do_post_population=False,
            do_field_validation=True,
        ),
    )
    process_rule_schema_for_context(context)
    return context


def test_human_subjects_loads_complete_portable_inventory() -> None:
    form = build_preview_form(FORM_ID)
    projected = _load_banked_form(FORM_ID, project_xml=True)
    fields = [
        node
        for node in walk(form.form_ui_schema)
        if node.get("type") in {"field", "input", "readOnly"}
        and isinstance(node.get("definition"), str)
    ]
    lists = [node for node in walk(form.form_ui_schema) if node.get("type") == "fieldList"]
    tables = [node for node in walk(form.form_ui_schema) if node.get("widget") == "Table"]

    assert form.form_name == (
        "[Portable preview] PHS Human Subjects and Clinical Trials Information"
    )
    assert form.form_version == "3.0"
    assert form.legacy_form_id == 705
    assert len(fields) == 184
    assert [table["name"] for table in tables] == ["planned", "cumulativeActual"]
    assert len(lists) == 5
    assert {node["name"] for node in lists} == {
        "studies",
        "inclusion_enrollment_reports",
        "interventions",
        "outcome_measures",
        "delayed_onset_studies",
    }
    reusable_lists = {node["name"]: node for node in lists}
    expected_human_subjects_gate = {
        "when": {
            "op": "equals",
            "ref": {"scope": "root", "pointer": "/involves_human_subjects"},
            "value": "Y: Yes",
        },
        "then": {"interaction": "enabled"},
        "otherwise": {"interaction": "disabled"},
    }
    assert reusable_lists["studies"]["label"] == "Human Subject Study"
    assert reusable_lists["studies"]["conditional"] == expected_human_subjects_gate
    assert reusable_lists["delayed_onset_studies"]["label"] == "Delayed Onset Study"
    assert reusable_lists["delayed_onset_studies"]["conditional"] == expected_human_subjects_gate
    assert reusable_lists["inclusion_enrollment_reports"]["label"] == "Inclusion Enrollment Report"
    assert projected.form_rule_schema is not None
    assert projected.json_to_xml_schema is not None

    xml_profile = read("targets/grants-gov-xml.json")
    mappings = list(walk(xml_profile["mapping"]["fields"]))
    assert len([row for row in mappings if row.get("kind") == "attachment"]) == 15
    enrollment = xml_profile["mapping"]["fields"]["studies"]["items"]["fields"][
        "populationCharacteristics"
    ]["fields"]["inclusionEnrollmentReports"]["items"]
    actual_coordinates = enrollment_coordinate_mappings(enrollment["fields"])
    expected_coordinates = expected_enrollment_coordinate_mappings()
    assert len(expected_coordinates) == 115
    assert actual_coordinates == expected_coordinates


def test_human_subjects_preserves_exact_provenance_and_open_behavior_gates() -> None:
    evidence = read("evidence.json")
    source_records = tuple(
        (
            source["id"],
            source["type"],
            source["uri"],
            source["nativeVersion"],
            source["sha256"],
        )
        for source in evidence["sources"]
    )
    condition_records = [
        row for row in evidence["behaviorEvidence"] if row["ruleKind"] == "condition"
    ]
    calculations = [row for row in evidence["behaviorEvidence"] if row["ruleKind"] == "calculation"]

    assert evidence["extraction"] == {
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "4312f6504b060e2b9ffdbd2307fc41130c3123a0",
        "artifact": "artifacts/proof/grantsgov-PHSHumanSubjects.jsonl.manifest.json",
        "sourceSetSha256": ("0ea2ffec7e91299638cc4e63415ee8da6c32ef07fdd91bffb8d44241053ab72f"),
        "extractedAt": "2026-08-18T17:32:15.841439Z",
    }
    assert source_records == EXPECTED_SOURCE_RECORDS
    assert [
        (
            row["sourcePath"],
            row["canonicalPath"],
            row["ruleKind"],
            row["authority"],
            row["executionStatus"],
            row["sourceId"],
            row["sourceRecord"],
        )
        for row in condition_records
    ] == [
        (
            "1-07",
            "/exemptFromFederalRegulations",
            "condition",
            "official_source",
            "source-bound-uncompiled",
            "phs-human-subjects-dat-f705",
            "Required if HumanSubjectsIndicator is yes.",
        ),
        (
            "1-08",
            "/exemptions",
            "condition",
            "official_source",
            "source-bound-uncompiled",
            "phs-human-subjects-dat-f705",
            "One selection required if ExemptFedReg is yes.",
        ),
        (
            "1-14",
            "studies",
            "condition",
            "official_source",
            "compiled",
            "phs-human-subjects-dat-f705",
            "The Adobe PDF version of the Human Subject Study form will be compressed and "
            "embedded into this form. The applicant will click the button and a dialog box will "
            "appear where applicant indicates where to save the file. Disabled if "
            "HumanSubjectsIndicator is not Yes.",
        ),
        (
            "1-15-1",
            "/studies",
            "condition",
            "official_source",
            "source-bound-uncompiled",
            "phs-human-subjects-dat-f705",
            "Delete the row. Disabled if only one entry exists. Disabled if "
            "HumanSubjectsIndicator is not Yes.",
        ),
        (
            "1-15-2",
            "/studies",
            "condition",
            "official_source",
            "source-bound-uncompiled",
            "phs-human-subjects-dat-f705",
            "The number 1 in field label will vary from 1 to 150 to reflect the attachment number. "
            'Verify the attachment is a PDF format. Provide standard "Add", "Delete" and "View" '
            "features. Disabled if HumanSubjectsIndicator is not Yes.",
        ),
        (
            "1-16",
            "/studies",
            "condition",
            "official_source",
            "source-bound-uncompiled",
            "phs-human-subjects-dat-f705",
            "Adds another entry. Disabled on 150th entry. Disabled if HumanSubjectsIndicator is "
            "not Yes.",
        ),
        (
            "1-19-1",
            "/delayedOnsetStudies",
            "condition",
            "official_source",
            "source-bound-uncompiled",
            "phs-human-subjects-dat-f705",
            "Delete the row. Disabled if only one entry exists. Disabled if "
            "HumanSubjectsIndicator is not Yes.",
        ),
        (
            "1-19-2",
            "/delayedOnsetStudies/[]/studyTitle",
            "condition",
            "official_source",
            "source-bound-uncompiled",
            "phs-human-subjects-dat-f705",
            "Required for each row entered. Disabled if HumanSubjectsIndicator is not Yes.",
        ),
        (
            "1-19-3",
            "/delayedOnsetStudies/[]/anticipatedClinicalTrial",
            "condition",
            "official_source",
            "source-bound-uncompiled",
            "phs-human-subjects-dat-f705",
            "Disabled if HumanSubjectsIndicator is not Yes.",
        ),
        (
            "1-19-4",
            "/delayedOnsetStudies/[]/justification",
            "condition",
            "official_source",
            "source-bound-uncompiled",
            "phs-human-subjects-dat-f705",
            'Required for each row entered. Provide standard "Add", "Delete" and "View" features. '
            "Disabled if HumanSubjectsIndicator is not Yes.",
        ),
        (
            "1-20",
            "delayedOnsetStudies",
            "condition",
            "official_source",
            "compiled",
            "phs-human-subjects-dat-f705",
            "Adds another entry. Disabled on 150th entry. Disabled if HumanSubjectsIndicator is "
            "not Yes.",
        ),
    ]
    assert len(condition_records) == 11
    assert [
        (row["sourcePath"], row["canonicalPath"])
        for row in condition_records
        if row["executionStatus"] == "source-bound-uncompiled"
    ] == list(SOURCE_BOUND_CONDITIONS)
    assert [
        (row["sourcePath"], row["canonicalPath"])
        for row in condition_records
        if row["executionStatus"] == "compiled"
    ] == [("1-14", "studies"), ("1-20", "delayedOnsetStudies")]
    assert calculations == [
        {
            "canonicalPath": "/studies/[]/populationCharacteristics/"
            "inclusionEnrollmentReports/[]",
            "ruleKind": "calculation",
            "authority": "unresolved",
            "executionStatus": "source-bound-uncompiled",
            "owner": "source-review",
            "reason": "One unresolved disposition covers all 28 total-like enrollment "
            "coordinates. The pinned parent XSD and F705 DAT contain zero calculation records, "
            "so no arithmetic is inferred.",
            "removalCondition": "Pin exact version-matched embedded-study calculation evidence "
            "and review every one of the 28 coordinate bindings.",
        }
    ]
    assert evidence["semanticReview"]["status"] == "proposed"
    assert {row["status"] for row in evidence["semanticReview"]["mappings"]} == {"proposed"}


def test_all_fifteen_attachments_execute_through_shared_rule_processing() -> None:
    expected_ids = set(ATTACHMENT_IDS.values())
    valid = rule_context(expected_ids)
    assert valid.attachment_ids == expected_ids
    assert valid.validation_issues == []


@pytest.mark.parametrize(("role", "expected_field"), ATTACHMENT_VALIDATION_FIELDS.items())
def test_each_attachment_role_fails_at_its_exact_field_when_missing(
    role: str, expected_field: str
) -> None:
    expected_ids = set(ATTACHMENT_IDS.values())
    missing_id = ATTACHMENT_IDS[role]
    missing = rule_context(expected_ids - {missing_id})
    assert missing.attachment_ids == expected_ids
    assert len(missing.validation_issues) == 1
    assert missing.validation_issues[0].field == expected_field
    assert missing.validation_issues[0].value == missing_id


def test_representative_nested_response_emits_exact_source_valid_xml() -> None:
    context = rule_context(set(ATTACHMENT_IDS.values()))
    assert context.validation_issues == []
    projected = _load_banked_form(FORM_ID, project_xml=True)
    assert projected.json_to_xml_schema is not None
    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=cast(dict[str, Any], context.json_data),
            transform_config=projected.json_to_xml_schema,
            attachment_mapping=attachment_mapping(),
        )
    )
    assert generated.success, generated.error_message
    assert generated.xml_data is not None

    locations: dict[str, str] = {}
    for filename, digest in PINNED_XSDS.items():
        path = XSD_DIRECTORY / filename
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        namespace = etree.parse(path).getroot().get("targetNamespace")
        assert namespace is not None
        locations[namespace] = str(path.resolve())
    schema = xmlschema.XMLSchema(
        str((XSD_DIRECTORY / FORM_XSD).resolve()), locations=locations, allow="local"
    )
    errors = list(schema.iter_errors(generated.xml_data))
    assert not errors, "\n".join(str(error) for error in errors)

    root = etree.fromstring(generated.xml_data.encode())
    assert root.tag == f"{{{FORM_NAMESPACE}}}PHSHumanSubjectsAndClinicalTrialsInfo_3_0"
    assert root.get(f"{{{FORM_NAMESPACE}}}FormVersion") == "3.0"
    assert [node.text for node in root.findall(f".//{{{STUDY_NAMESPACE}}}EnrollmentCountry")] == [
        "USA: UNITED STATES",
        "CAN: CANADA",
    ]
    assert [node.text for node in root.findall(f".//{{{STUDY_NAMESPACE}}}StudyConditions")] == [
        "Condition A",
        "Condition B",
    ]
    enrollment_sentinels = {
        ".//study:Planned/study:NotHispanic/study:Female/study:Asian": "7",
        ".//study:Planned/study:Total/study:Asian": "7",
        ".//study:Cumulative/study:UnknownEthnicity/study:UnknownGender/" "study:UnknownRace": "3",
        ".//study:Cumulative/study:Total/study:UnknownRace": "3",
    }
    for path, expected_value in enrollment_sentinels.items():
        assert root.xpath(f"{path}/text()", namespaces={"study": STUDY_NAMESPACE}) == [
            expected_value
        ]
    assert root.findtext(
        f"{{{FORM_NAMESPACE}}}DelayedOnsetStudy/{{{FORM_NAMESPACE}}}StudyTitle"
    ) == ("Delayed study")
    filenames = root.findall(f".//{{{ATTACHMENT_NAMESPACE}}}FileName")
    assert {node.text for node in filenames} == {
        f"evidence-{index:02d}.pdf" for index in range(1, 16)
    }
    assert len(filenames) == 15
    namespaces = {
        "phs": FORM_NAMESPACE,
        "study": STUDY_NAMESPACE,
        "att": ATTACHMENT_NAMESPACE,
    }
    exact_attachment_roles = {
        "phs:Explanation/phs:attFile": "evidence-01.pdf",
        "phs:OtherRequestedInformation/phs:attFile": "evidence-02.pdf",
        ".//study:InclusionOfIndividualsAcrossLifespan/study:attFile": "evidence-03.pdf",
        ".//study:InclusionOfWomenAndMinorities/study:attFile": "evidence-04.pdf",
        ".//study:RecruitmentAndRetentionPlan/study:attFile": "evidence-05.pdf",
        ".//study:StudyTimeline/study:attFile": "evidence-06.pdf",
        ".//study:ProtectionOfHumanSubjects/study:attFile": "evidence-07.pdf",
        ".//study:IRBPlan/study:attFile": "evidence-08.pdf",
        ".//study:DataSafetyMonitoringPlan/study:attFile": "evidence-09.pdf",
        ".//study:StudyTeamStructure/study:attFile": "evidence-10.pdf",
        ".//study:StatisticalDesignPower/study:attFile": "evidence-11.pdf",
        ".//study:InvestigationalAvailability/study:attFile": "evidence-12.pdf",
        ".//study:DisseminationPlan/study:attFile": "evidence-13.pdf",
        ".//study:OtherClinicalTrialAttachment/att:AttachedFile": "evidence-14.pdf",
        "phs:DelayedOnsetStudy/phs:Justification/phs:attFile": "evidence-15.pdf",
    }
    for attachment_path, expected_filename in exact_attachment_roles.items():
        assert root.xpath(f"{attachment_path}/att:FileName/text()", namespaces=namespaces) == [
            expected_filename
        ]


def test_human_subjects_remains_unregistered_with_proposed_semantics() -> None:
    registrations = json.loads(REGISTRATIONS.read_text())
    evidence = read("evidence.json")

    assert FORM_ID not in registrations["forms"]
    assert evidence["semanticReview"]["status"] == "proposed"
    assert not (ARTIFACTS.parent / "projections" / f"{FORM_ID}.json").exists()
