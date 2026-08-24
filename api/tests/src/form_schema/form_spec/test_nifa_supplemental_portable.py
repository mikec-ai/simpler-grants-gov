import json
from pathlib import Path

from src.form_schema.form_spec.bank import ARTIFACTS

FORM = ARTIFACTS / "forms" / "nifa-supplemental"


def read(relative: str):
    return json.loads((FORM / relative).read_text())


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def test_nifa_package_is_banked_with_portable_behavior_and_provenance() -> None:
    manifest = read("manifest.json")
    schema = read("schema.json")
    ui = read("sgg/ui-schema.json")
    evidence = read("evidence.json")

    assert manifest["form"]["legacyFormId"] == 483
    assert manifest["form"]["formVersion"] == "1.2"
    assert schema["required"] == [
        "fundingOpportunity",
        "program",
        "applicantType",
        "asapRecipientInformation",
        "keywords",
    ]
    additional = next(
        node
        for node in walk(ui)
        if node.get("definition", "").endswith(
            "/additionalApplicantType/properties/additionalApplicantType"
        )
    )
    assert additional["conditional"]["when"] == {
        "op": "in",
        "ref": {"scope": "root", "pointer": "/applicantType/applicantTypeCode"},
        "values": [
            "H: Public/state Controlled Institution of Higher Education",
            "X: Other (specify)",
        ],
    }
    assert evidence["semanticReview"]["status"] == "proposed"
    assert len(evidence["semanticReview"]["mappings"]) == 22
    assert not any(row["status"] == "accepted" for row in evidence["semanticReview"]["mappings"])


def test_nifa_xml_profile_is_generic_and_uses_the_exact_official_xsd() -> None:
    profile = read("targets/grants-gov-xml.json")
    xsd = Path("src/services/xml_generation/xsds/NIFA_Supplemental_Info_1_2-V1.2.xsd")

    assert (
        profile["xsd"]["sha256"]
        == "9fd2d43797ec5fe17a9c29f073295e1c459b13d39346b3422de036d51c1d69e2"
    )
    assert xsd.is_file()
    assert profile["mapping"]["fields"]["applicantType"]["source"] == (
        "/applicantType/applicantTypeCode"
    )
    assert profile["mapping"]["fields"]["asapRecipientInformation"]["fields"][
        "hasActiveAsapRecipientId"
    ]["valueMap"] == {"true": "Y: Yes", "false": "N: No"}
    assert not Path("src/form_schema/form_spec/projections/nifa-supplemental.json").exists()
