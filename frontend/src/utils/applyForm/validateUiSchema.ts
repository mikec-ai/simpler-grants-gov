import { RJSFSchema } from "@rjsf/utils";
import Ajv, { ValidateFunction } from "ajv";
import addFormats from "ajv-formats";

// JSON Schema for the UiSchema, accepts a "field", "fieldList", "multiField", or "section"
export const UiJsonSchema: RJSFSchema = {
  $schema: "http://json-schema.org/draft-07/schema#",
  type: "array",
  items: {
    anyOf: [
      {
        $ref: "#/$defs/field",
      },
      {
        $ref: "#/$defs/multiField",
      },
      {
        $ref: "#/$defs/fieldList",
      },
      {
        $ref: "#/$defs/section",
      },
    ],
  },
  $defs: {
    field: {
      type: "object",
      properties: {
        type: {
          type: "string",
          enum: ["field", "null"],
        },
        name: { type: "string" },
        schema: {
          $ref: "#/$defs/schema",
        },
        definition: {
          oneOf: [
            {
              type: "string",
              pattern: "^/(properties|\\$defs)(/[a-zA-Z0-9_]+)+$",
            },
            {
              type: "array",
              items: {
                type: "string",
                pattern: "^/(properties|\\$defs)(/[a-zA-Z0-9_]+)+$",
              },
            },
          ],
        },
        widget: {
          type: "string",
          enum: [
            "Attachment",
            "AttachmentArray",
            "Checkbox",
            "EncodedCheckboxGroup",
            "Text",
            "TextArea",
            "Radio",
            "Select",
            "MultiSelect",
            "Budget424a",
            "Budget424aSectionA",
            "Budget424aSectionB",
            "Budget424aSectionC",
            "Budget424aSectionD",
            "Budget424aSectionE",
            "Budget424aSectionF",
            "Budget424aTotalBudgetSummary",
          ],
        },
        attachmentType: { type: "string" },
        printDescription: { type: "boolean" },
        conditional: { $ref: "#/$defs/conditional" },
      },
      required: ["type"],
      anyOf: [
        {
          required: ["schema"],
        },
        {
          required: ["definition"],
        },
      ],
      additionalProperties: false,
    },
    multiField: {
      type: "object",
      properties: {
        type: {
          type: "string",
          enum: ["multiField"],
        },
        name: { type: "string" },
        schema: {
          $ref: "#/$defs/schema",
        },
        definition: {
          oneOf: [
            {
              type: "string",
              pattern: "^/(properties|\\$defs)(/[a-zA-Z0-9_]+)+$",
            },
            {
              type: "array",
              items: {
                type: "string",
                pattern: "^/(properties|\\$defs)(/[a-zA-Z0-9_]+)+$",
              },
            },
          ],
        },
        widget: {
          type: "string",
          enum: [
            "Budget424a",
            "Budget424aSectionA",
            "Budget424aSectionB",
            "Budget424aSectionC",
            "Budget424aSectionD",
            "Budget424aSectionE",
            "Budget424aSectionF",
            "Budget424aTotalBudgetSummary",
            "Table",
          ],
        },
        children: {
          $ref: "#/$defs/tableChildren",
        },
        conditional: { $ref: "#/$defs/conditional" },
      },
      required: ["type"],
      allOf: [
        {
          if: {
            properties: {
              widget: {
                const: "Table",
              },
            },
            required: ["widget"],
          },
          then: {
            required: ["name", "definition", "children"],
            properties: {
              definition: {
                type: "array",
                minItems: 1,
                items: {
                  type: "string",
                  pattern: "^/(properties|\\$defs)(/[a-zA-Z0-9_]+)+$",
                },
              },
            },
            not: {
              required: ["schema"],
            },
          },
          else: {
            anyOf: [
              {
                required: ["schema"],
              },
              {
                required: ["definition"],
              },
            ],
          },
        },
      ],
      additionalProperties: false,
    },
    schema: {
      type: "object",
      properties: {
        schema: {
          type: "object",
          properties: {
            title: {
              type: "string",
            },
            type: {
              type: "string",
              enum: ["boolean", "string", "number", "integer", "null"],
            },
            enum: {
              type: "array",
            },
            pattern: {
              type: "string",
              enum: ["date", "email"],
            },
          },
          required: ["title", "type"],
          additionalProperties: false,
        },
      },
    },
    section: {
      type: "object",
      properties: {
        type: {
          type: "string",
          enum: ["section"],
        },
        label: {
          type: "string",
        },
        name: {
          type: "string",
        },
        description: {
          type: "string",
        },
        conditional: { $ref: "#/$defs/conditional" },
        children: {
          type: "array",
          items: {
            anyOf: [
              {
                $ref: "#/$defs/field",
              },
              {
                $ref: "#/$defs/multiField",
              },
              {
                $ref: "#/$defs/fieldList",
              },
              {
                $ref: "#/$defs/section",
              },
            ],
          },
        },
      },
      required: ["type", "label", "name", "children"],
      additionalProperties: false,
    },
    fieldList: {
      type: "object",
      properties: {
        type: {
          type: "string",
          enum: ["fieldList"],
        },
        label: {
          type: "string",
        },
        hideFieldListHeading: { type: "boolean" },
        validateBeforeAdd: { type: "boolean" },
        minItemsHeading: { type: "string" },
        minItemsHelperText: { type: "string" },
        maxItemsHeading: { type: "string" },
        maxItemsHelperText: { type: "string" },
        name: {
          type: "string",
        },
        definition: {
          type: "string",
          pattern: "^/(properties|\\$defs)(/[a-zA-Z0-9_]+)+$",
        },
        description: {
          type: "string",
        },
        conditional: { $ref: "#/$defs/conditional" },
        children: {
          type: "array",
          items: {
            anyOf: [
              {
                $ref: "#/$defs/field",
              },
              {
                $ref: "#/$defs/multiField",
              },
              {
                $ref: "#/$defs/fieldList",
              },
            ],
          },
        },
      },
      required: ["type", "label", "name", "children"],
      additionalProperties: false,
    },
    tableChildren: {
      type: "object",
      properties: {
        columns: {
          type: "array",
          minItems: 1,
          items: {
            $ref: "#/$defs/tableColumn",
          },
        },
        rows: {
          type: "array",
          minItems: 1,
          items: {
            $ref: "#/$defs/tableRow",
          },
        },
      },
      required: ["columns", "rows"],
      additionalProperties: false,
    },
    conditional: {
      type: "object",
      properties: {
        when: { $ref: "#/$defs/conditionalPredicate" },
        then: { $ref: "#/$defs/conditionalUiState" },
        otherwise: { $ref: "#/$defs/conditionalUiState" },
      },
      required: ["when", "then"],
      additionalProperties: false,
    },
    conditionalUiState: {
      type: "object",
      properties: {
        visible: { type: "boolean" },
        interaction: {
          type: "string",
          enum: ["enabled", "disabled", "readOnly"],
        },
      },
      minProperties: 1,
      additionalProperties: false,
    },
    conditionalValueRef: {
      type: "object",
      properties: {
        scope: { type: "string", enum: ["root", "item"] },
        pointer: {
          type: "string",
          pattern: "^(/([^/~]|~[01])*)*$",
        },
        ancestor: { type: "integer", minimum: 0 },
      },
      required: ["scope", "pointer"],
      additionalProperties: false,
      allOf: [
        {
          if: {
            properties: { scope: { const: "root" } },
            required: ["scope"],
          },
          then: { not: { required: ["ancestor"] } },
        },
      ],
    },
    conditionalScalar: {
      anyOf: [
        { type: "string" },
        { type: "number" },
        { type: "boolean" },
        { type: "null" },
      ],
    },
    conditionalPredicate: {
      oneOf: [
        {
          type: "object",
          properties: {
            op: { type: "string", enum: ["equals", "notEquals"] },
            ref: { $ref: "#/$defs/conditionalValueRef" },
            value: { $ref: "#/$defs/conditionalScalar" },
          },
          required: ["op", "ref", "value"],
          additionalProperties: false,
        },
        {
          type: "object",
          properties: {
            op: { const: "in" },
            ref: { $ref: "#/$defs/conditionalValueRef" },
            values: {
              type: "array",
              minItems: 1,
              items: { $ref: "#/$defs/conditionalScalar" },
            },
          },
          required: ["op", "ref", "values"],
          additionalProperties: false,
        },
        {
          type: "object",
          properties: {
            op: { const: "present" },
            ref: { $ref: "#/$defs/conditionalValueRef" },
          },
          required: ["op", "ref"],
          additionalProperties: false,
        },
        {
          type: "object",
          properties: {
            op: { const: "countAtLeast" },
            ref: { $ref: "#/$defs/conditionalValueRef" },
            minimum: { type: "integer", minimum: 0 },
          },
          required: ["op", "ref", "minimum"],
          additionalProperties: false,
        },
        {
          type: "object",
          properties: {
            op: { type: "string", enum: ["all", "any"] },
            predicates: {
              type: "array",
              minItems: 1,
              items: { $ref: "#/$defs/conditionalPredicate" },
            },
          },
          required: ["op", "predicates"],
          additionalProperties: false,
        },
        {
          type: "object",
          properties: {
            op: { const: "not" },
            predicate: { $ref: "#/$defs/conditionalPredicate" },
          },
          required: ["op", "predicate"],
          additionalProperties: false,
        },
      ],
    },
    tableColumn: {
      type: "object",
      properties: {
        columnHeader: {
          type: "string",
        },
        width: {
          type: "number",
          minimum: 1,
          maximum: 100,
          description:
            "Optional column width as a percentage. Configured column widths cannot total more than 100.",
        },
      },
      required: ["columnHeader"],
      additionalProperties: false,
    },
    tableRow: {
      type: "object",
      properties: {
        cells: {
          type: "array",
          minItems: 1,
          items: {
            $ref: "#/$defs/tableCell",
          },
        },
      },
      required: ["cells"],
      additionalProperties: false,
    },
    tableCell: {
      type: "object",
      properties: {
        type: {
          type: "string",
          enum: ["input", "select", "readOnly", "plainText"],
        },
        definition: {
          type: "string",
          pattern: "^/(properties|\\$defs)(/[a-zA-Z0-9_]+)+$",
        },
        staticContent: {
          type: "string",
        },
        format: {
          type: "string",
          enum: ["integer", "decimal", "currency", "dollar", "percentage"],
        },
        options: {
          type: "array",
          minItems: 1,
          uniqueItems: true,
          items: {
            type: ["string", "number"],
          },
        },
      },
      required: ["type"],
      allOf: [
        {
          if: {
            properties: {
              type: {
                const: "select",
              },
            },
          },
          then: {
            required: ["definition", "options"],
            not: {
              anyOf: [
                {
                  required: ["staticContent"],
                },
                {
                  required: ["format"],
                },
              ],
            },
          },
        },
        {
          if: {
            properties: {
              type: {
                enum: ["input", "readOnly"],
              },
            },
          },
          then: {
            required: ["definition"],
            not: {
              required: ["staticContent"],
            },
          },
        },
        {
          if: {
            properties: {
              type: {
                const: "plainText",
              },
            },
          },
          then: {
            required: ["staticContent"],
            not: {
              anyOf: [
                {
                  required: ["definition"],
                },
                {
                  required: ["format"],
                },
              ],
            },
          },
        },
      ],
      additionalProperties: false,
    },
  },
};

const buildAjv = () => {
  const ajv = new Ajv({ allErrors: true, coerceTypes: true });
  addFormats(ajv);

  return ajv;
};

/*
  Compiling a schema is codegen plus eval, and the ui schema is validated on every
  application form request, so the validator for it is built once per process. Reading
  `errors` straight after the synchronous call keeps this safe to share across requests.
*/
let uiSchemaValidator: ValidateFunction | undefined;

export const validateUiSchema = (data: object) => {
  uiSchemaValidator = uiSchemaValidator ?? buildAjv().compile(UiJsonSchema);

  if (uiSchemaValidator(data)) {
    return false;
  } else {
    return uiSchemaValidator.errors;
  }
};

export const validateJsonBySchema = (json: object, schema: RJSFSchema) => {
  const validate = buildAjv().compile(schema);

  if (validate(json)) {
    return false;
  } else {
    return validate.errors;
  }
};
