"""Project Abstract Summary canary for the portable form specification.

The existing Simpler form remains registered because it owns the production XML
transformation. This canary proves that the portable declaration matches the applicant-facing
schema, UI, and rules before that final adapter capability is moved to declarative data.
"""

import copy
import json
from pathlib import Path

import src.form_schema.forms as forms_package
from src.form_schema.form_spec.bank import ARTIFACTS
from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms._loader import load_versioned_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from tests.src.form_schema.form_spec import parity

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


def test_project_abstract_summary_identity_and_evidence_are_exact() -> None:
    projected = load_form("project-abstract-summary")
    assert projected.meta == {
        "id": "project-abstract-summary",
        "formId": "bf683068-23a4-43fa-ac7a-0f046b83cb14",
        "legacyFormId": 591,
        "formName": "Project Abstract Summary",
        "shortFormName": "Project_AbstractSummary_2_0",
        "formVersion": "2.0",
        "agencyCode": "SGG",
        "ombNumber": "4040-0019",
        "formType": "ProjectAbstractSummary",
        "sggVersion": "1.0",
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


def test_existing_xml_transform_remains_the_runtime_authority() -> None:
    golden = _golden()
    portable_manifest = json.loads(
        (ARTIFACTS / "forms" / "project-abstract-summary" / "manifest.json").read_text()
    )

    assert golden.ProjectAbstractSummary_v2_0.json_to_xml_schema
    assert "xml-schema.json" not in portable_manifest["artifacts"]
