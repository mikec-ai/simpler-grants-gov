"""Tests for json_rule_validator, focusing on attachment ID collection."""

import uuid
from types import SimpleNamespace

from src.form_schema.rule_processing.json_rule_context import JsonRuleConfig, JsonRuleContext
from src.form_schema.rule_processing.json_rule_processor import process_rule_schema_for_context
from src.validation.validation_constants import ValidationErrorType
from tests.src.form_schema.rule_processing.conftest import setup_context


class TestScalarAttachmentIdCollection:
    def test_valid_attachment_id_collected(self, enable_factory_create):
        att_id = str(uuid.uuid4())
        context = setup_context(
            {"att_field": att_id},
            rule_schema={"att_field": {"gg_validation": {"rule": "attachment"}}},
            attachment_ids=[att_id],
        )
        process_rule_schema_for_context(context)
        assert att_id in context.attachment_ids

    def test_invalid_attachment_id_still_collected(self, enable_factory_create):
        """An ID not on the application is still added to attachment_ids (validation adds an error,
        but collection is unconditional)."""
        att_id = str(uuid.uuid4())
        context = setup_context(
            {"att_field": att_id},
            rule_schema={"att_field": {"gg_validation": {"rule": "attachment"}}},
            attachment_ids=[],
        )
        process_rule_schema_for_context(context)
        assert att_id in context.attachment_ids

    def test_none_value_not_collected(self, enable_factory_create):
        context = setup_context(
            {},
            rule_schema={"att_field": {"gg_validation": {"rule": "attachment"}}},
            attachment_ids=[],
        )
        process_rule_schema_for_context(context)
        assert context.attachment_ids == set()


class TestDateOrderValidation:
    RULE_SCHEMA = {
        "period": {
            "end": {
                "gg_validation": {
                    "rule": "date_not_before",
                    "fields": ["@THIS.start"],
                }
            }
        }
    }

    @classmethod
    def context(cls, response):
        application_form = SimpleNamespace(
            application_response=response,
            application_form_id="date-order-test",
            form_id="date-order-form",
            form=SimpleNamespace(form_rule_schema=cls.RULE_SCHEMA),
        )
        return JsonRuleContext(application_form, JsonRuleConfig())

    def test_rejects_end_date_before_start_date(self):
        context = self.context({"period": {"start": "2027-10-01", "end": "2027-09-30"}})

        process_rule_schema_for_context(context)

        assert len(context.validation_issues) == 1
        assert context.validation_issues[0].type == ValidationErrorType.INVALID_DATE_ORDER
        assert context.validation_issues[0].field == "$.period.end"

    def test_accepts_equal_or_later_end_date(self):
        for end in ("2027-10-01", "2030-09-30"):
            context = self.context({"period": {"start": "2027-10-01", "end": end}})

            process_rule_schema_for_context(context)

            assert context.validation_issues == []

    def test_leaves_missing_and_invalid_dates_to_json_schema(self):
        for response in (
            {"period": {"end": "2027-10-01"}},
            {"period": {"start": "not-a-date", "end": "2027-10-01"}},
        ):
            context = self.context(response)

            process_rule_schema_for_context(context)

            assert context.validation_issues == []


class TestCollectionAttachmentIdCollection:
    def test_list_field_all_ids_collected(self, enable_factory_create):
        id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
        context = setup_context(
            {"att_list_field": [id1, id2]},
            rule_schema={"att_list_field": {"gg_validation": {"rule": "attachment"}}},
            attachment_ids=[id1, id2],
        )
        process_rule_schema_for_context(context)
        assert context.attachment_ids == {id1, id2}

    def test_multiple_fields_all_collected(self, enable_factory_create):
        id1, id2 = str(uuid.uuid4()), str(uuid.uuid4())
        context = setup_context(
            {"att_field": id1, "att_list_field": [id2]},
            rule_schema={
                "att_field": {"gg_validation": {"rule": "attachment"}},
                "att_list_field": {"gg_validation": {"rule": "attachment"}},
            },
            attachment_ids=[id1, id2],
        )
        process_rule_schema_for_context(context)
        assert context.attachment_ids == {id1, id2}

    def test_non_attachment_fields_not_collected(self, enable_factory_create):
        """A UUID in a plain (non-attachment) field is not collected."""
        att_id = str(uuid.uuid4())
        other_id = str(uuid.uuid4())
        context = setup_context(
            {"att_field": att_id, "plain_field": other_id},
            rule_schema={"att_field": {"gg_validation": {"rule": "attachment"}}},
            attachment_ids=[att_id],
        )
        process_rule_schema_for_context(context)
        assert context.attachment_ids == {att_id}
        assert other_id not in context.attachment_ids

    def test_no_rule_schema_empty_collection(self, enable_factory_create):
        att_id = str(uuid.uuid4())
        context = setup_context(
            {"att_field": att_id},
            rule_schema=None,
            attachment_ids=[att_id],
        )
        process_rule_schema_for_context(context)
        assert context.attachment_ids == set()
