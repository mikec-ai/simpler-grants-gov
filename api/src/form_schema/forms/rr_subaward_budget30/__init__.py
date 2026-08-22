from pathlib import Path

from src.form_schema.forms._loader import load_versioned_form

_mod = load_versioned_form(Path(__file__).parent, "3.0")
RRSubawardBudget30_v3_0 = _mod.RRSubawardBudget30_v3_0
FORM_JSON_SCHEMA = _mod.FORM_JSON_SCHEMA
FORM_UI_SCHEMA = _mod.FORM_UI_SCHEMA
FORM_RULE_SCHEMA = _mod.FORM_RULE_SCHEMA
FORM_XML_TRANSFORM_RULES = _mod.FORM_XML_TRANSFORM_RULES
del _mod
