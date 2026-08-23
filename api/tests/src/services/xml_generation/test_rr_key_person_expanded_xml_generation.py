"""R&R Key Person XML conformance from the pinned portable producer declaration."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from lxml import etree

from src.form_schema.form_spec.loader import load_form
from src.form_schema.jsonschema_resolver import resolve_jsonschema
from src.services.xml_generation.models import XMLGenerationRequest
from src.services.xml_generation.service import XMLGenerationService
from src.services.xml_generation.utils.attachment_mapping import AttachmentInfo
from src.services.xml_generation.validation.xsd_validator import XSDValidator


XSD_DIRECTORY = Path("src/services/xml_generation/xsds")
XSD_NAME = "RR_KeyPersonExpanded_4_0-V4.0.xsd"
XSD_CLOSURE_SHA256 = {
    "RR_KeyPersonExpanded_4_0-V4.0.xsd": (
        "c1522304f37bb91a1fc18f2b84656c570581969f9c1795d18352bc273d691b8b"
    ),
    "GlobalLibrary-V2.0.xsd": ("ff0214de91b95a4209f50f0fe08a18d0f3d17f280ab8c8bbcb52878f37de7be8"),
    "Global-V1.0.xsd": "4b338db919152eb8b96a1a846902d04ef8bca8d08127b21f80f927eaa62283cb",
    "Attachments-V1.0.xsd": ("ae2ebb3618f7d8fb337be2309b3096e9121b4af659e913af423aab85d13dcb1d"),
    "UniversalCodes-V2.0.xsd": ("78f33338e9319ef31a052d1328b8984931a4380db2485493bcc78ab9e2c11f3a"),
}
FORM_NS = "http://apply.grants.gov/forms/RR_KeyPersonExpanded_4_0-V4.0"
ATT_NS = "http://apply.grants.gov/system/Attachments-V1.0"
GLOB_NS = "http://apply.grants.gov/system/Global-V1.0"
GLOB_LIB_NS = "http://apply.grants.gov/system/GlobalLibrary-V2.0"
XSD_NS = "http://www.w3.org/2001/XMLSchema"

ATTACHMENT_IDS = {
    name: f"00000000-0000-0000-0000-{index:012d}"
    for index, name in enumerate(
        (
            "pi-bio",
            "senior-us-bio",
            "senior-us-support",
            "senior-foreign-bio",
            "senior-foreign-support",
            "overflow-profiles",
            "overflow-bios",
            "overflow-support",
        ),
        start=1,
    )
}


def _attachment(name: str) -> AttachmentInfo:
    return AttachmentInfo(
        filename=f"{name}.pdf",
        mime_type="application/pdf",
        file_location=f"./attachments/{name}.pdf",
        hash_value="2jmj7l5rSw0yVb/vlWAYkK/YBwk=",
    )


def _person(first_name: str, last_name: str, *, country: str, **address: str) -> dict[str, Any]:
    return {
        "name": {"first_name": first_name, "last_name": last_name},
        "address": {
            "street1": "1 Research Way",
            "city": "Science City",
            "country": country,
            **address,
        },
        "phone": "202-555-0100",
        "email": f"{first_name.lower()}@example.org",
        "project_role": "PD/PI",
    }


def _response() -> dict[str, Any]:
    pi = _person(
        "Ada",
        "Lovelace",
        country="USA: UNITED STATES",
        state="CA: California",
        zip_code="940431234",
    )
    pi["biographical_sketch"] = ATTACHMENT_IDS["pi-bio"]
    senior_us = _person(
        "Grace",
        "Hopper",
        country="USA: UNITED STATES",
        state="VA: Virginia",
        zip_code="222011234",
    )
    senior_us.update({
        "project_role": "Co-Investigator",
        "biographical_sketch": ATTACHMENT_IDS["senior-us-bio"],
        "current_pending_support": ATTACHMENT_IDS["senior-us-support"],
    })
    senior_foreign = _person(
        "Katherine",
        "Johnson",
        country="CAN: CANADA",
        province="Ontario",
        zip_code="K1A0B1",
    )
    senior_foreign.update({
        "project_role": "Co-Investigator",
        "biographical_sketch": ATTACHMENT_IDS["senior-foreign-bio"],
        "current_pending_support": ATTACHMENT_IDS["senior-foreign-support"],
    })
    return {
        "principal_investigator": pi,
        "senior_key_persons": [senior_us, senior_foreign],
        "additional_profiles": ATTACHMENT_IDS["overflow-profiles"],
        "additional_biographical_sketches": ATTACHMENT_IDS["overflow-bios"],
        "additional_current_pending_support": ATTACHMENT_IDS["overflow-support"],
    }


def _assemble_submission_xml() -> str:
    response = _response()
    form = load_form("rr-key-person-expanded")
    schema = resolve_jsonschema(copy.deepcopy(form.form_json_schema))
    assert list(Draft202012Validator(schema).iter_errors(response)) == []
    assert form.json_to_xml_schema is not None
    attachment_mapping = {
        attachment_id: _attachment(name) for name, attachment_id in ATTACHMENT_IDS.items()
    }
    result = XMLGenerationService().generate_xml(
        XMLGenerationRequest(
            application_data=response,
            transform_config=form.json_to_xml_schema,
            attachment_mapping=attachment_mapping,
        )
    )
    assert result.success, result.error_message
    assert result.xml_data is not None
    return result.xml_data


def _assert_attachment(
    parent: etree._Element,
    wrapper_name: str,
    leaf_name: str,
    attachment_name: str,
) -> None:
    wrappers = parent.findall(f"{{{FORM_NS}}}{wrapper_name}")
    assert len(wrappers) == 1
    wrapper = wrappers[0]
    assert [child.tag for child in wrapper] == [f"{{{FORM_NS}}}{leaf_name}"]
    leaf = wrapper[0]
    assert [child.tag for child in leaf] == [
        f"{{{ATT_NS}}}FileName",
        f"{{{ATT_NS}}}MimeType",
        f"{{{ATT_NS}}}FileLocation",
        f"{{{GLOB_NS}}}HashValue",
    ]
    assert leaf[0].text == f"{attachment_name}.pdf"
    assert leaf[1].text == "application/pdf"
    assert leaf[2].text is None
    assert leaf[2].attrib == {f"{{{ATT_NS}}}href": f"./attachments/{attachment_name}.pdf"}
    assert leaf[3].text == "2jmj7l5rSw0yVb/vlWAYkK/YBwk="
    assert leaf[3].attrib == {f"{{{GLOB_NS}}}hashAlgorithm": "SHA-1"}


def _assert_person(
    profile: etree._Element,
    *,
    first_name: str,
    last_name: str,
    state_or_province: tuple[str, str],
    zip_code: str,
    country: str,
    email: str,
    project_role: str,
) -> None:
    name = profile.find(f"{{{FORM_NS}}}Name")
    assert name is not None
    assert [(child.tag, child.text) for child in name] == [
        (f"{{{GLOB_LIB_NS}}}FirstName", first_name),
        (f"{{{GLOB_LIB_NS}}}LastName", last_name),
    ]

    address = profile.find(f"{{{FORM_NS}}}Address")
    assert address is not None
    subdivision_name, subdivision_value = state_or_province
    assert [(child.tag, child.text) for child in address] == [
        (f"{{{GLOB_LIB_NS}}}Street1", "1 Research Way"),
        (f"{{{GLOB_LIB_NS}}}City", "Science City"),
        (f"{{{GLOB_LIB_NS}}}{subdivision_name}", subdivision_value),
        (f"{{{GLOB_LIB_NS}}}ZipPostalCode", zip_code),
        (f"{{{GLOB_LIB_NS}}}Country", country),
    ]
    assert profile.findtext(f"{{{FORM_NS}}}Phone") == "202-555-0100"
    assert profile.findtext(f"{{{FORM_NS}}}Email") == email
    assert profile.findtext(f"{{{FORM_NS}}}ProjectRole") == project_role


def _assert_exact_xsd_dependency_closure() -> None:
    pending = [XSD_NAME]
    visited: set[str] = set()
    while pending:
        schema_name = pending.pop()
        if schema_name in visited:
            continue
        assert schema_name in XSD_CLOSURE_SHA256
        schema_path = XSD_DIRECTORY / schema_name
        assert (
            hashlib.sha256(schema_path.read_bytes()).hexdigest() == XSD_CLOSURE_SHA256[schema_name]
        )
        visited.add(schema_name)

        schema = etree.parse(schema_path)
        for imported in schema.findall(f"{{{XSD_NS}}}import"):
            location = imported.get("schemaLocation")
            assert location is not None
            imported_name = location.rsplit("/", 1)[-1]
            assert imported_name in XSD_CLOSURE_SHA256
            pending.append(imported_name)

    assert visited == set(XSD_CLOSURE_SHA256)


def test_key_person_submission_assembler_preserves_exact_wire_shape_and_data() -> None:
    root = etree.fromstring(_assemble_submission_xml().encode())
    assert [child.tag for child in root] == [
        f"{{{FORM_NS}}}PDPI",
        f"{{{FORM_NS}}}KeyPerson",
        f"{{{FORM_NS}}}KeyPerson",
        f"{{{FORM_NS}}}AdditionalProfilesAttached",
        f"{{{FORM_NS}}}BioSketchsAttached",
        f"{{{FORM_NS}}}SupportsAttached",
    ]

    pdpis = root.findall(f"{{{FORM_NS}}}PDPI")
    assert len(pdpis) == 1
    assert [child.tag for child in pdpis[0]] == [f"{{{FORM_NS}}}Profile"]
    pi_profile = pdpis[0][0]
    assert [child.tag for child in pi_profile] == [
        f"{{{FORM_NS}}}Name",
        f"{{{FORM_NS}}}Address",
        f"{{{FORM_NS}}}Phone",
        f"{{{FORM_NS}}}Email",
        f"{{{FORM_NS}}}ProjectRole",
        f"{{{FORM_NS}}}BioSketchsAttached",
    ]
    _assert_person(
        pi_profile,
        first_name="Ada",
        last_name="Lovelace",
        state_or_province=("State", "CA: California"),
        zip_code="940431234",
        country="USA: UNITED STATES",
        email="ada@example.org",
        project_role="PD/PI",
    )
    _assert_attachment(pi_profile, "BioSketchsAttached", "BioSketchAttached", "pi-bio")

    key_people = root.findall(f"{{{FORM_NS}}}KeyPerson")
    assert len(key_people) == 2
    profiles: list[etree._Element] = []
    for key_person in key_people:
        assert [child.tag for child in key_person] == [f"{{{FORM_NS}}}Profile"]
        profile = key_person[0]
        profiles.append(profile)
        assert [child.tag for child in profile] == [
            f"{{{FORM_NS}}}Name",
            f"{{{FORM_NS}}}Address",
            f"{{{FORM_NS}}}Phone",
            f"{{{FORM_NS}}}Email",
            f"{{{FORM_NS}}}ProjectRole",
            f"{{{FORM_NS}}}BioSketchsAttached",
            f"{{{FORM_NS}}}SupportsAttached",
        ]
    _assert_person(
        profiles[0],
        first_name="Grace",
        last_name="Hopper",
        state_or_province=("State", "VA: Virginia"),
        zip_code="222011234",
        country="USA: UNITED STATES",
        email="grace@example.org",
        project_role="Co-Investigator",
    )
    _assert_person(
        profiles[1],
        first_name="Katherine",
        last_name="Johnson",
        state_or_province=("Province", "Ontario"),
        zip_code="K1A0B1",
        country="CAN: CANADA",
        email="katherine@example.org",
        project_role="Co-Investigator",
    )
    _assert_attachment(profiles[0], "BioSketchsAttached", "BioSketchAttached", "senior-us-bio")
    _assert_attachment(profiles[0], "SupportsAttached", "SupportAttached", "senior-us-support")
    _assert_attachment(profiles[1], "BioSketchsAttached", "BioSketchAttached", "senior-foreign-bio")
    _assert_attachment(profiles[1], "SupportsAttached", "SupportAttached", "senior-foreign-support")
    _assert_attachment(
        root,
        "AdditionalProfilesAttached",
        "AdditionalProfileAttached",
        "overflow-profiles",
    )
    _assert_attachment(root, "BioSketchsAttached", "BioSketchAttached", "overflow-bios")
    _assert_attachment(root, "SupportsAttached", "SupportAttached", "overflow-support")


def test_key_person_submission_validates_against_exact_pinned_xsd() -> None:
    _assert_exact_xsd_dependency_closure()
    xsd_path = XSD_DIRECTORY / XSD_NAME

    result = XSDValidator(XSD_DIRECTORY).validate_xml(
        _assemble_submission_xml(),
        xsd_path,
    )

    assert result["valid"], result
