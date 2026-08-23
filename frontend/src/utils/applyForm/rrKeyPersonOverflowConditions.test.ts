import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ConditionalUi } from "src/types/applyForm/conditionalUiTypes";
import type { UiSchema, UiSchemaNode } from "src/types/applyForm/types";
import { resolveConditionalUiState } from "src/utils/applyForm/evaluateConditionalUi";

const artifact = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      "../../../../api/src/form_schema/form_spec/artifacts/forms/rr-key-person-expanded/sgg/ui-schema.json",
    ),
    "utf8",
  ),
) as UiSchema;

const nodes = (schema: UiSchema): UiSchemaNode[] =>
  schema.flatMap((node) => [
    node,
    ...(node.type === "section" || node.type === "fieldList"
      ? nodes(node.children as UiSchema)
      : []),
  ]);

const overflowFields = [
  "additionalProfiles",
  "additionalBiographicalSketches",
  "additionalCurrentPendingSupport",
] as const;

const conditionFor = (
  fieldName: (typeof overflowFields)[number],
): ConditionalUi => {
  const definition = `/properties/${fieldName}`;
  const field = nodes(artifact).find(
    (candidate) =>
      candidate.type === "field" && candidate.definition === definition,
  );
  if (!field?.conditional) {
    throw new Error(
      `Missing artifact-backed overflow condition for ${definition}`,
    );
  }
  return field.conditional;
};

const interactionFor = (
  fieldName: (typeof overflowFields)[number],
  rootData: object,
) =>
  resolveConditionalUiState(conditionFor(fieldName), { rootData }).interaction;

describe("R&R Senior/Key Person overflow conditions", () => {
  it.each(overflowFields)(
    "enables %s when 99 structured people are present",
    (fieldName) => {
      expect(
        interactionFor(fieldName, {
          seniorKeyPersons: Array.from({ length: 99 }, () => ({})),
        }),
      ).toBe("enabled");
    },
  );

  it.each(overflowFields)(
    "keeps %s enabled for its own saved attachment",
    (fieldName) => {
      expect(
        interactionFor(fieldName, {
          seniorKeyPersons: [],
          [fieldName]: "00000000-0000-0000-0000-000000000001",
        }),
      ).toBe("enabled");
    },
  );

  it.each(overflowFields)(
    "disables %s below capacity without a saved value",
    (fieldName) => {
      expect(interactionFor(fieldName, { seniorKeyPersons: [] })).toBe(
        "disabled",
      );
    },
  );

  it("does not let one saved overflow upload keep sibling uploads enabled", () => {
    const rootData = {
      seniorKeyPersons: [],
      additionalProfiles: "00000000-0000-0000-0000-000000000001",
    };

    expect(interactionFor("additionalProfiles", rootData)).toBe("enabled");
    expect(interactionFor("additionalBiographicalSketches", rootData)).toBe(
      "disabled",
    );
    expect(interactionFor("additionalCurrentPendingSupport", rootData)).toBe(
      "disabled",
    );
  });
});
