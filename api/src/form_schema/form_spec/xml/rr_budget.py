"""Grants.gov XML projection for the portable R&R Budget 3.0 form.

The form's questions, validation, UI, and calculations remain canonical artifacts from
``grants-form-spec``. This module is deliberately consumer-owned: it maps Simpler's projected
snake-case response shape to the Grants.gov XML wire contract.
"""

from typing import Any

FORM_NAMESPACE = "http://apply.grants.gov/forms/RR_Budget_3_0-V3.0"
XSD_URL = "https://apply07.grants.gov/apply/forms/schemas/RR_Budget_3_0-V3.0.xsd"


def _field(target: str, *, namespace: str | None = None) -> dict[str, Any]:
    transform: dict[str, Any] = {"target": target}
    if namespace is not None:
        transform["namespace"] = namespace
    return {"xml_transform": transform}


def _object(target: str, fields: dict[str, Any], *, namespace: str | None = None) -> dict[str, Any]:
    transform: dict[str, Any] = {"target": target, "type": "nested_object"}
    if namespace is not None:
        transform["namespace"] = namespace
    return {"xml_transform": transform, **fields}


def _array(target: str, fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "xml_transform": {"target": target, "type": "array"},
        "items": fields,
    }


def _attachment(target: str) -> dict[str, Any]:
    # Child declarations make the generic XML writer assign the imported attachment
    # namespace. The attachment transform itself resolves the UUID to these wire fields.
    return {
        "xml_transform": {"target": target, "type": "attachment"},
        "file_name": _field("FileName", namespace="att"),
        "mime_type": _field("MimeType", namespace="att"),
        "file_location": _field("FileLocation", namespace="att"),
        "hash_value": _field("HashValue", namespace="glob"),
    }


def _personnel_fields() -> dict[str, Any]:
    return {
        "number_of_personnel": _field("NumberOfPersonnel"),
        "project_role": _field("ProjectRole"),
        "calendar_months": _field("CalendarMonths"),
        "academic_months": _field("AcademicMonths"),
        "summer_months": _field("SummerMonths"),
        "requested_salary": _field("RequestedSalary"),
        "fringe_benefits": _field("FringeBenefits"),
        "funds_requested": _field("FundsRequested"),
    }


def _other_direct_cost(target: str) -> dict[str, Any]:
    return _object(
        target,
        {
            "description": _field("Description"),
            "cost": _field("Cost"),
        },
    )


KEY_PERSON_FIELDS = {
    "name": _object(
        "Name",
        {
            "prefix_name": _field("PrefixName", namespace="globLib"),
            "first_name": _field("FirstName", namespace="globLib"),
            "middle_name": _field("MiddleName", namespace="globLib"),
            "last_name": _field("LastName", namespace="globLib"),
            "suffix_name": _field("SuffixName", namespace="globLib"),
        },
        namespace="default",
    ),
    "project_role": _field("ProjectRole"),
    "base_salary": _field("BaseSalary"),
    "calendar_months": _field("CalendarMonths"),
    "academic_months": _field("AcademicMonths"),
    "summer_months": _field("SummerMonths"),
    "requested_salary": _field("RequestedSalary"),
    "fringe_benefits": _field("FringeBenefits"),
    "funds_requested": _field("FundsRequested"),
}
KEY_PERSONS_FIELDS = {
    "key_person": _array("KeyPerson", KEY_PERSON_FIELDS),
    "total_fund_for_attached_key_persons": _field("TotalFundForAttachedKeyPersons"),
    "total_fund_for_key_persons": _field("TotalFundForKeyPersons"),
    "attached_key_persons": _attachment("AttachedKeyPersons"),
}

OTHER_PERSONNEL_FIELDS = {
    "post_doc_associates": _object("PostDocAssociates", _personnel_fields()),
    "graduate_students": _object("GraduateStudents", _personnel_fields()),
    "undergraduate_students": _object("UndergraduateStudents", _personnel_fields()),
    "secretarial_clerical": _object("SecretarialClerical", _personnel_fields()),
    "other": _array("Other", _personnel_fields()),
    "other_personnel_total_number": _field("OtherPersonnelTotalNumber"),
    "total_other_personnel_fund": _field("TotalOtherPersonnelFund"),
}

EQUIPMENT_FIELDS = {
    "equipment_list": _array(
        "EquipmentList",
        {
            "equipment_item": _field("EquipmentItem"),
            "funds_requested": _field("FundsRequested"),
        },
    ),
    "total_fund_for_attached_equipment": _field("TotalFundForAttachedEquipment"),
    "total_fund": _field("TotalFund"),
    "additional_equipments_attachment": _attachment("AdditionalEquipmentsAttachment"),
}

TRAVEL_FIELDS = {
    "domestic_travel_cost": _field("DomesticTravelCost"),
    "foreign_travel_cost": _field("ForeignTravelCost"),
    "total_travel_cost": _field("TotalTravelCost"),
}

PARTICIPANT_TRAINEE_FIELDS = {
    "tuition_fee_health_insurance": _field("TuitionFeeHealthInsurance"),
    "stipends": _field("Stipends"),
    "travel": _field("Travel"),
    "subsistence": _field("Subsistence"),
    "other": _object(
        "Other",
        {
            "description": _field("Description"),
            "cost": _field("Cost"),
        },
    ),
    "participant_trainee_number": _field("ParticipantTraineeNumber"),
    "total_cost": _field("TotalCost"),
}

OTHER_DIRECT_COST_FIELDS = {
    "materials_supplies": _field("MaterialsSupplies"),
    "publication_costs": _field("PublicationCosts"),
    "consultant_services": _field("ConsultantServices"),
    "adp_computer_services": _field("ADPComputerServices"),
    "subaward_consortium_contractual_costs": _field("SubawardConsortiumContractualCosts"),
    "equipment_rental_fee": _field("EquipmentRentalFee"),
    "alterations_renovations": _field("AlterationsRenovations"),
    **{
        f"other_direct_cost_{index}": _other_direct_cost(f"OtherDirectCost{index}")
        for index in range(1, 11)
    },
    "total_other_direct_cost": _field("TotalOtherDirectCost"),
}

INDIRECT_COST_FIELDS = {
    "indirect_cost": _array(
        "IndirectCost",
        {
            "cost_type": _field("CostType"),
            "rate": _field("Rate"),
            "base": _field("Base"),
            "fund_requested": _field("FundRequested"),
        },
    ),
    "total_indirect_costs": _field("TotalIndirectCosts"),
}

BUDGET_YEAR_FIELDS = {
    "budget_period_start_date": _field("BudgetPeriodStartDate"),
    "budget_period_end_date": _field("BudgetPeriodEndDate"),
    "key_persons": _object("KeyPersons", KEY_PERSONS_FIELDS),
    "other_personnel": _object("OtherPersonnel", OTHER_PERSONNEL_FIELDS),
    "total_compensation": _field("TotalCompensation"),
    "equipment": _object("Equipment", EQUIPMENT_FIELDS),
    "travel": _object("Travel", TRAVEL_FIELDS),
    "participant_trainee_support_costs": _object(
        "ParticipantTraineeSupportCosts", PARTICIPANT_TRAINEE_FIELDS
    ),
    "other_direct_costs": _object("OtherDirectCosts", OTHER_DIRECT_COST_FIELDS),
    "direct_costs": _field("DirectCosts"),
    "indirect_costs": _object("IndirectCosts", INDIRECT_COST_FIELDS),
    "cognizant_federal_agency": _field("CognizantFederalAgency"),
    "total_costs": _field("TotalCosts"),
    "fee": _field("Fee"),
    "total_costs_fee": _field("TotalCostsFee"),
}

BUDGET_SUMMARY_FIELDS = {
    "cumulative_total_funds_requested_senior_key_person": _field(
        "CumulativeTotalFundsRequestedSeniorKeyPerson"
    ),
    "cumulative_total_funds_requested_other_personnel": _field(
        "CumulativeTotalFundsRequestedOtherPersonnel"
    ),
    "cumulative_total_no_other_personnel": _field("CumulativeTotalNoOtherPersonnel"),
    "cumulative_total_funds_requested_personnel": _field("CumulativeTotalFundsRequestedPersonnel"),
    "cumulative_total_funds_requested_equipment": _field("CumulativeTotalFundsRequestedEquipment"),
    "cumulative_total_funds_requested_travel": _field("CumulativeTotalFundsRequestedTravel"),
    "cumulative_domestic_travel_costs": _field("CumulativeDomesticTravelCosts"),
    "cumulative_foreign_travel_costs": _field("CumulativeForeignTravelCosts"),
    "cumulative_total_funds_requested_trainee_costs": _field(
        "CumulativeTotalFundsRequestedTraineeCosts"
    ),
    "cumulative_trainee_tuition_fees_health_insurance": _field(
        "CumulativeTraineeTuitionFeesHealthInsurance"
    ),
    "cumulative_trainee_stipends": _field("CumulativeTraineeStipends"),
    "cumulative_trainee_travel": _field("CumulativeTraineeTravel"),
    "cumulative_trainee_subsistence": _field("CumulativeTraineeSubsistence"),
    "cumulative_other_trainee_cost": _field("CumulativeOtherTraineeCost"),
    "cumulative_noof_trainees": _field("CumulativeNoofTrainees"),
    "cumulative_total_funds_requested_other_direct_costs": _field(
        "CumulativeTotalFundsRequestedOtherDirectCosts"
    ),
    "cumulative_material_and_supplies": _field("CumulativeMaterialAndSupplies"),
    "cumulative_publication_costs": _field("CumulativePublicationCosts"),
    "cumulative_consultant_services": _field("CumulativeConsultantServices"),
    "cumulative_adp_computer_services": _field("CumulativeADPComputerServices"),
    "cumulative_subaward_consortium_contractual_costs": _field(
        "CumulativeSubawardConsortiumContractualCosts"
    ),
    "cumulative_equipment_facility_rental_fees": _field("CumulativeEquipmentFacilityRentalFees"),
    "cumulative_alterations_and_renovations": _field("CumulativeAlterationsAndRenovations"),
    **{
        f"cumulative_other_{index}_direct_cost": _field(f"CumulativeOther{index}DirectCost")
        for index in range(1, 11)
    },
    "cumulative_total_funds_requested_direct_costs": _field(
        "CumulativeTotalFundsRequestedDirectCosts"
    ),
    "cumulative_total_funds_requested_indirect_cost": _field(
        "CumulativeTotalFundsRequestedIndirectCost"
    ),
    "cumulative_total_funds_requested_direct_indirect_costs": _field(
        "CumulativeTotalFundsRequestedDirectIndirectCosts"
    ),
    "cumulative_fee": _field("CumulativeFee"),
    "cumulative_total_costs_fee": _field("CumulativeTotalCostsFee"),
}

RR_BUDGET_XML_TRANSFORM_RULES: dict[str, Any] = {
    "_xml_config": {
        "description": "Grants.gov XML projection for the portable R&R Budget form",
        "version": "1.0",
        "form_name": "RR_Budget_3_0",
        "namespaces": {
            "default": FORM_NAMESPACE,
            "globLib": "http://apply.grants.gov/system/GlobalLibrary-V2.0",
            "glob": "http://apply.grants.gov/system/Global-V1.0",
            "att": "http://apply.grants.gov/system/Attachments-V1.0",
        },
        "xsd_url": XSD_URL,
        "xml_structure": {
            "root_element": "RR_Budget_3_0",
            "root_namespace_prefix": "RR_Budget_3_0",
            "root_attributes": {"FormVersion": "3.0"},
        },
    },
    # Insertion order is the XSD sequence and is consumed by XMLGenerationService.
    "samuei": _field("SAMUEI"),
    "budget_type": _field("BudgetType"),
    "organization_name": _field("OrganizationName"),
    "budget_year": _array("BudgetYear", BUDGET_YEAR_FIELDS),
    "budget_justification_attachment": _attachment("BudgetJustificationAttachment"),
    "budget_summary": _object("BudgetSummary", BUDGET_SUMMARY_FIELDS),
}
