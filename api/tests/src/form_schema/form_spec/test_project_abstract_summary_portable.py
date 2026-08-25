"""Project Abstract Summary portable handoff and oracle-parity evidence."""

import copy
import hashlib
import json
import re
from pathlib import Path

import defusedxml.ElementTree as ET

import src.form_schema.forms as forms_package
from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms._loader import load_versioned_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.validation.xsd_validator import XSDValidator
from tests.src.form_schema.form_spec import parity

FORM_ID = "project-abstract-summary"
INTRODUCED_BY_PRODUCER_REVISION = "b6a584df98570c9ee1c521eda75635e010fa1555"
XSD_NAME = "Project_AbstractSummary_2_0-V2.0.xsd"
XSD_SHA256 = "3022f177a7f0ebb9a1888e9b8a4a644ed2ba7857a775d2d05642a9fbd1cc008f"
XSD_DIRECTORY = Path(__file__).parents[4] / "src/services/xml_generation/xsds"
PRODUCER_FORM_ARTIFACT_SHA256 = {
    "evidence.json": "40d2365535e5af67ed6ed9a93e57528bb7bcf16ac8849e5fc0dab897e62083ee",
    "manifest.json": "095b63e851c2ef84efdc9d48fafec219d8e293709d2113053a8f59727adf7fe6",
    "schema.json": "aff8c3d21ca798205e25156139bee30ee68adefdfd5c36c688ea17dd104e1541",
    "sgg/rule-schema.json": "f12170c71e91d43d1b0fe4e7e6e2cd4acc36608d4bd2d55dbda435f2377be336",
    "sgg/ui-schema.json": "92f7aa57483e04e5baf99bfd914d334c5ff88d478b34d02b8e60418aaf1d9bc9",
    "targets/grants-gov-xml.json": (
        "51fd9698bf5205bb6c655fe25d378bdc00500177c093036731860c029322ac9c"
    ),
}

RENDERED = {
    "/properties/funding_opportunity_number#description": (
        "The portable question carries source-derived guidance that the existing schema omits."
    ),
    "/properties/assistance_listing_number#description": (
        "The portable question carries source-derived guidance that the existing schema omits."
    ),
    "/properties/project_abstract#description": (
        "The portable question carries source-derived guidance that the existing schema omits."
    ),
}


def _golden():
    return load_versioned_form(
        Path(forms_package.__file__).parent / "project_abstract_summary", "1.0"
    )


def test_project_abstract_summary_matches_existing_simpler_behavior() -> None:
    golden = _golden()
    projected = load_form("project-abstract-summary")
    resolved_golden = resolve_jsonschema(copy.deepcopy(golden.FORM_JSON_SCHEMA))
    resolved_projected = resolve_jsonschema(copy.deepcopy(projected.form_json_schema))

    assert projected.form_ui_schema == golden.FORM_UI_SCHEMA
    assert projected.form_rule_schema == golden.FORM_RULE_SCHEMA

    differences = parity.rendered_differences(
        resolved_projected, resolved_golden, golden.FORM_UI_SCHEMA
    )
    assert parity.unexplained(differences, RENDERED) == []
    assert parity.unused(differences, RENDERED) == []

    valid = {
        "funding_opportunity_number": "HHS-2026-EXAMPLE",
        "assistance_listing_number": "93.001",
        "applicant_name": "Example Research Organization",
        "project_title": "A concise project title",
        "project_abstract": "A plain-language summary of the proposed project.",
    }
    payloads = parity.corpus(resolved_golden, [{}, valid])
    assert parity.behavioral_differences(resolved_projected, resolved_golden, payloads) == []


def test_project_abstract_summary_portable_metadata_and_evidence_are_exact() -> None:
    projected = load_form("project-abstract-summary")
    assert projected.meta == {
        "id": "project-abstract-summary",
        "legacyFormId": 591,
        "formName": "Project Abstract Summary",
        "shortFormName": "Project_AbstractSummary_2_0",
        "formVersion": "2.0",
        "agencyCode": "SGG",
        "ombNumber": "4040-0019",
    }

    evidence = json.loads(
        (ARTIFACTS / "forms" / "project-abstract-summary" / "evidence.json").read_text()
    )
    assert evidence["extraction"] == {
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "dfe9e47ffd6a25c967b8ed38703480ccdc15a8ef",
        "artifact": "artifacts/proof/grantsgov-ProjectAbstractSummary.jsonl.manifest.json",
        "sourceSetSha256": "1db2a9accecdd883a73cc4a9622a12ae29772a3cf4a874d1b1f8aa57e2cf9558",
        "extractedAt": "2026-08-18T19:43:17.917258Z",
    }
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}
    assert [(source["type"], source["sha256"]) for source in evidence["sources"]] == [
        ("dat", "75114a512cf3a768a7a20e837d17adaf18a1a5a3ec57523388120e39ee40413c"),
        ("xsd", "3022f177a7f0ebb9a1888e9b8a4a644ed2ba7857a775d2d05642a9fbd1cc008f"),
        ("xsd", "ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8"),
    ]


def _xml(transform: dict, response: dict) -> str:
    generated = XMLGenerationService().generate_xml(
        XMLGenerationRequest(application_data=response, transform_config=transform)
    )
    assert generated.success, generated.error_message
    assert generated.xml_data is not None
    return generated.xml_data


def _tree(xml: str) -> tuple[str, dict[str, str], list[tuple[str, str | None]]]:
    root = ET.fromstring(xml)
    return (
        root.tag,
        root.attrib,
        [(child.tag, child.text) for child in root],
    )


def test_portable_xml_matches_existing_oracle_and_exact_official_xsd() -> None:
    golden = _golden()
    projected = load_form(FORM_ID)
    portable_manifest = json.loads(
        (ARTIFACTS / "forms" / "project-abstract-summary" / "manifest.json").read_text()
    )
    response = {
        "funding_opportunity_number": "HHS-2026-EXAMPLE",
        "assistance_listing_number": "93.001",
        "applicant_name": "Example Research Organization",
        "project_title": "A concise project title",
        "project_abstract": "A plain-language summary of the proposed project.",
    }

    assert golden.ProjectAbstractSummary_v2_0.json_to_xml_schema
    assert projected.json_to_xml_schema is not None
    assert portable_manifest["artifacts"]["targets/grants-gov-xml.json"] == "generated"

    portable_xml = _xml(projected.json_to_xml_schema, response)
    oracle_xml = _xml(golden.FORM_XML_TRANSFORM_RULES, response)
    assert _tree(portable_xml) == _tree(oracle_xml)

    xsd = XSD_DIRECTORY / XSD_NAME
    assert hashlib.sha256(xsd.read_bytes()).hexdigest() == XSD_SHA256
    validation = XSDValidator(XSD_DIRECTORY).validate_xml_for_form(
        portable_xml, XSD_NAME.removesuffix(".xsd")
    )
    assert validation["valid"], validation


def test_portable_xml_preserves_optional_cfda_omission() -> None:
    projected = load_form(FORM_ID)
    assert projected.json_to_xml_schema is not None
    xml = _xml(
        projected.json_to_xml_schema,
        {
            "funding_opportunity_number": "HHS-2026-EXAMPLE",
            "applicant_name": "Example Research Organization",
            "project_title": "A concise project title",
            "project_abstract": "A plain-language summary of the proposed project.",
        },
    )
    assert "CFDANumber" not in xml


def test_current_pin_preserves_producer_receipts_without_semantic_acceptance() -> None:
    artifact_manifest = json.loads((ARTIFACTS / "artifact-manifest.json").read_text())
    form_root = ARTIFACTS / "forms" / FORM_ID
    evidence = json.loads((form_root / "evidence.json").read_text())
    profile = json.loads((form_root / "targets/grants-gov-xml.json").read_text())

    assert INTRODUCED_BY_PRODUCER_REVISION == ("b6a584df98570c9ee1c521eda75635e010fa1555")
    # The selection manifest advances whenever any portable form is promoted. Exact
    # form-scoped hashes are the durable receipt that Project Abstract remains identical
    # to its historical producer handoff after later bundle promotions.
    assert artifact_manifest["source"]["repository"] == (
        "https://github.com/mikec-ai/grants-form-spec.git"
    )
    assert re.fullmatch(r"[0-9a-f]{40}", artifact_manifest["source"]["revision"])
    assert {
        relative_path: hashlib.sha256((form_root / relative_path).read_bytes()).hexdigest()
        for relative_path in PRODUCER_FORM_ARTIFACT_SHA256
    } == PRODUCER_FORM_ARTIFACT_SHA256
    assert profile["xsd"] == {
        "uri": "https://apply07.grants.gov/apply/forms/schemas/Project_AbstractSummary_2_0-V2.0.xsd",
        "sha256": XSD_SHA256,
    }
    assert profile["evidence"] == {
        "status": "source-bound-unreviewed",
        "repository": "https://github.com/mikec-ai/grants-question-crosswalk",
        "revision": "dfe9e47ffd6a25c967b8ed38703480ccdc15a8ef",
        "artifact": "artifacts/proof/grantsgov-ProjectAbstractSummary.jsonl.manifest.json",
    }
    assert evidence["semanticReview"] == {"status": "unreviewed", "mappings": []}
