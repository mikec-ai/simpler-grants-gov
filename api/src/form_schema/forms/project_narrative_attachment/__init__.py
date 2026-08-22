from pathlib import Path

from src.form_schema.form_spec.loader import load_form
from src.form_schema.forms._loader import load_versioned_form

_mod = load_versioned_form(Path(__file__).parent, "1.0")
_portable = load_form("project-narrative-attachments")
FORM_JSON_SCHEMA = _portable.form_json_schema
FORM_UI_SCHEMA = _portable.form_ui_schema
FORM_RULE_SCHEMA = _portable.form_rule_schema
FORM_XML_TRANSFORM_RULES = _mod.FORM_XML_TRANSFORM_RULES
ProjectNarrativeAttachment_v1_2 = _mod.ProjectNarrativeAttachment_v1_2
ProjectNarrativeAttachment_v1_2.form_json_schema = FORM_JSON_SCHEMA
ProjectNarrativeAttachment_v1_2.form_ui_schema = FORM_UI_SCHEMA
ProjectNarrativeAttachment_v1_2.form_rule_schema = FORM_RULE_SCHEMA
del _mod
del _portable
