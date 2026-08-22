from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.loader import build_runtime_form
from src.form_schema.forms.rr_subaward_budget30.config import FORM_INSTRUCTION_ID

RRSubawardBudget30_v3_0 = build_runtime_form(
    "rr-subaward-budget-30",
    form_type=FormType.RR_SUBAWARD_BUDGET_30,
    form_instruction_id=FORM_INSTRUCTION_ID,
)

FORM_JSON_SCHEMA = RRSubawardBudget30_v3_0.form_json_schema
FORM_UI_SCHEMA = RRSubawardBudget30_v3_0.form_ui_schema
FORM_RULE_SCHEMA = RRSubawardBudget30_v3_0.form_rule_schema
FORM_XML_TRANSFORM_RULES = RRSubawardBudget30_v3_0.json_to_xml_schema
