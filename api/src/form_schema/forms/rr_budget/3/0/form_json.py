from src.constants.lookup_constants import FormType
from src.form_schema.form_spec.loader import build_runtime_form
from src.form_schema.forms.rr_budget.config import FORM_INSTRUCTION_ID

RRBudget_v3_0 = build_runtime_form(
    "rr-budget",
    form_type=FormType.RR_BUDGET,
    form_instruction_id=FORM_INSTRUCTION_ID,
)

FORM_JSON_SCHEMA = RRBudget_v3_0.form_json_schema
FORM_UI_SCHEMA = RRBudget_v3_0.form_ui_schema
FORM_RULE_SCHEMA = RRBudget_v3_0.form_rule_schema
FORM_XML_TRANSFORM_RULES = RRBudget_v3_0.json_to_xml_schema
