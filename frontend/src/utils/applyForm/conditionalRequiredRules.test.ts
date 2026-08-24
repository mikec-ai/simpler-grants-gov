import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { RJSFSchema } from "@rjsf/utils";
import Ajv2020 from "ajv/dist/2020";

import {
  evaluateConditionalRequiredRules,
  extractConditionalRequiredRules,
} from "./conditionalRequiredRules";

describe("conditional required rules", () => {
  const schema: RJSFSchema = {
    type: "object",
    properties: {
      applicantType: { type: "string" },
      organizationName: { type: "string" },
      contacts: {
        type: "array",
        items: {
          type: "object",
          properties: {
            primary: { type: "boolean" },
            email: { type: "string" },
          },
          allOf: [
            {
              if: {
                properties: { primary: { const: true } },
                required: ["primary"],
              },
              then: { required: ["email"] },
            },
          ],
        },
      },
    },
    allOf: [
      {
        if: {
          properties: { applicantType: { const: "organization" } },
          required: ["applicantType"],
        },
        then: { required: ["organizationName"] },
      },
    ],
  };

  it("extracts exact full-schema conditions with their source locations", () => {
    const rules = extractConditionalRequiredRules(schema);
    expect(rules).toHaveLength(2);
    expect(rules.map((rule) => rule.schemaPointer)).toEqual([
      "#/allOf/0",
      "#/properties/contacts/items/allOf/0",
    ]);
  });

  it("evaluates root and per-row requiredness without leaking between rows", () => {
    const result = evaluateConditionalRequiredRules(
      extractConditionalRequiredRules(schema),
      {
        applicantType: "organization",
        contacts: [{ primary: true }, { primary: false }],
      },
    );
    expect(result.activeRequiredPaths).toEqual([
      "$.organizationName",
      "$.contacts[0].email",
    ]);
    expect(result.warnings.map((warning) => warning.field)).toEqual([
      "$.organizationName",
      "$.contacts[0].email",
    ]);
    expect(result.managedPaths).toEqual([
      "$.organizationName",
      "$.contacts[0].email",
      "$.contacts[1].email",
    ]);
  });

  it("honors else-required and considers false and zero present values", () => {
    const rules = extractConditionalRequiredRules({
      type: "object",
      properties: { flag: { type: "boolean" }, count: { type: "integer" } },
      allOf: [
        {
          if: { properties: { flag: { const: true } } },
          then: { required: ["count"] },
          else: { required: ["flag"] },
        },
      ],
    });
    expect(
      evaluateConditionalRequiredRules(rules, { flag: false, count: 0 })
        .warnings,
    ).toEqual([]);
  });

  it("extracts a conditional directly on an object schema", () => {
    const rules = extractConditionalRequiredRules({
      type: "object",
      if: { required: ["kind"] },
      then: { required: ["detail"] },
    });
    expect(rules).toHaveLength(1);
    expect(rules[0]?.schemaPointer).toBe("#");
  });

  it("evaluates nested required effects declared through properties", () => {
    const rules = extractConditionalRequiredRules({
      type: "object",
      properties: {
        domestic: { type: "boolean" },
        contact: {
          type: "object",
          properties: {
            address: {
              type: "object",
              properties: { state: { type: "string" } },
            },
          },
        },
      },
      if: {
        properties: { domestic: { const: true } },
        required: ["domestic"],
      },
      then: {
        required: ["contact"],
        properties: {
          contact: {
            required: ["address"],
            properties: { address: { required: ["state"] } },
          },
        },
      },
    });

    const result = evaluateConditionalRequiredRules(rules, {
      domestic: true,
      contact: { address: {} },
    });
    expect(result.activeRequiredPaths).toEqual([
      "$.contact",
      "$.contact.address",
      "$.contact.address.state",
    ]);
    expect(result.warnings.map((warning) => warning.field)).toEqual([
      "$.contact.address.state",
    ]);
  });

  it("does not apply nested required effects below an absent optional parent", () => {
    const rules = extractConditionalRequiredRules({
      type: "object",
      if: true,
      then: {
        properties: {
          contact: {
            properties: { address: { required: ["state"] } },
          },
        },
      },
    });

    expect(evaluateConditionalRequiredRules(rules, {}).warnings).toEqual([]);
    expect(evaluateConditionalRequiredRules(rules, {}).managedPaths).toEqual(
      [],
    );
    expect(
      evaluateConditionalRequiredRules(rules, { contact: "invalid" }).warnings,
    ).toEqual([]);
  });

  it("retains instance scopes while resolving reusable local definitions", () => {
    const rules = extractConditionalRequiredRules({
      type: "object",
      properties: {
        primary_site: { $ref: "#/$defs/site" },
        additional_sites: {
          type: "array",
          items: { $ref: "#/$defs/site" },
        },
      },
      $defs: {
        site: {
          type: "object",
          properties: {
            country: { type: "string" },
            state: { type: "string" },
          },
          allOf: [
            {
              if: {
                properties: { country: { const: "US" } },
                required: ["country"],
              },
              then: { required: ["state"] },
            },
          ],
        },
      },
    });
    const result = evaluateConditionalRequiredRules(rules, {
      primary_site: { country: "US" },
      additional_sites: [{ country: "CA" }, { country: "US" }],
    });
    expect(result.warnings.map((warning) => warning.field)).toEqual([
      "$.primary_site.state",
      "$.additional_sites[1].state",
    ]);
  });

  it("resolves local references used inside an if condition", () => {
    const schema: RJSFSchema = {
      type: "object",
      properties: { kind: { type: "string" }, detail: { type: "string" } },
      $defs: { organizationKind: { const: "organization" } },
      if: {
        properties: { kind: { $ref: "#/$defs/organizationKind" } },
        required: ["kind"],
      },
      then: { required: ["detail"] },
    };
    const result = evaluateConditionalRequiredRules(
      extractConditionalRequiredRules(schema),
      { kind: "organization" },
    );
    expect(result.activeRequiredPaths).toEqual(["$.detail"]);
  });

  it("skips disjunctive R&R Budget effects without weakening them", () => {
    const periodArtifact = JSON.parse(
      readFileSync(
        resolve(
          __dirname,
          "../../../../api/src/form_schema/form_spec/artifacts/question-bank/budget/research/period/schema.json",
        ),
        "utf8",
      ),
    ) as RJSFSchema;
    const conditional = periodArtifact.allOf?.[0] as RJSFSchema;
    const thenSchema = conditional.then as RJSFSchema;

    expect(thenSchema.anyOf).toHaveLength(10);
    expect(
      extractConditionalRequiredRules({
        type: "object",
        allOf: [conditional],
      }),
    ).toEqual([]);

    const validate = new Ajv2020({ strict: false }).compile({
      type: "object",
      allOf: [conditional],
    });
    expect(validate({ participantTraineeSupportCosts: { other: "10" } })).toBe(
      false,
    );
    expect(validate.errors?.some((error) => error.keyword === "anyOf")).toBe(
      true,
    );
  });

  it.each([
    {
      type: "object",
      if: true,
      then: {
        required: ["detail"],
        properties: { detail: { minLength: 1 } },
      },
    },
    {
      type: "object",
      if: false,
      then: { required: ["detail"] },
      else: { properties: { detail: { minLength: 1 } } },
    },
    {
      type: "object",
      if: true,
      then: false,
    },
  ])(
    "skips conditional effects the required-style projection cannot represent",
    (nonProjectableSchema) => {
      expect(
        extractConditionalRequiredRules(nonProjectableSchema as RJSFSchema),
      ).toEqual([]);
    },
  );

  it.each([
    [
      "unsupported applicator",
      {
        type: "object",
        anyOf: [{ if: true, then: { required: ["detail"] } }],
      },
      /contains unsupported conditional requiredness/,
    ],
    [
      "unresolved reference",
      { type: "object", $ref: "https://example.test/schema.json" },
      /contains an unresolved \$ref/,
    ],
    [
      "malformed required effect",
      {
        type: "object",
        if: true,
        then: { required: "detail" },
      },
      /required must contain supported property names/,
    ],
    [
      "nested condition under an unhandled keyword",
      {
        type: "object",
        additionalProperties: {
          if: true,
          then: { required: ["detail"] },
        },
      },
      /contains unsupported conditional requiredness/,
    ],
    [
      "non-2020 schema dialect",
      {
        $schema: "http://json-schema.org/draft-07/schema#",
        type: "object",
      },
      /Unsupported JSON Schema dialect/,
    ],
    [
      "non-definitions condition reference",
      {
        type: "object",
        properties: { kind: { const: "organization" } },
        if: { $ref: "#/properties/kind" },
        then: { required: ["detail"] },
      },
      /unsupported condition \$ref/,
    ],
  ])("fails closed for %s", (_name, unsupportedSchema, expected) => {
    expect(() =>
      extractConditionalRequiredRules(unsupportedSchema as RJSFSchema),
    ).toThrow(expected);
  });
});
