from pathlib import Path

from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms._loader import load_versioned_form

_mod = load_versioned_form(Path(__file__).parent, "1.0")
_portable = load_form("sf424-short")
FORM_JSON_SCHEMA = _portable.form_json_schema
FORM_UI_SCHEMA = _portable.form_ui_schema
FORM_RULE_SCHEMA = _portable.form_rule_schema
FORM_XML_TRANSFORM_RULES = _mod.FORM_XML_TRANSFORM_RULES
SF424Short_v3_0 = _mod.SF424Short_v3_0
SF424Short_v3_0.form_json_schema = FORM_JSON_SCHEMA
SF424Short_v3_0.form_ui_schema = FORM_UI_SCHEMA
SF424Short_v3_0.form_rule_schema = FORM_RULE_SCHEMA
del _mod
del _portable
