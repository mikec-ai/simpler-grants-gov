import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ConditionalUi } from "src/types/applyForm/conditionalUiTypes";
import type { UiSchema, UiSchemaNode } from "src/types/applyForm/types";
import { resolveConditionalUiState } from "src/utils/applyForm/evaluateConditionalUi";

const artifact = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      "../../../../api/src/form_schema/form_spec/artifacts/forms/phs398-cover-page-supplement/sgg/ui-schema.json",
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

const conditionFor = (definition: string): ConditionalUi => {
  const field = nodes(artifact).find(
    (candidate) =>
      candidate.type === "field" && candidate.definition === definition,
  );
  if (!field?.conditional) {
    throw new Error(
      `Missing artifact-backed PHS 398 Cover Page Supplement condition for ${definition}`,
    );
  }
  return field.conditional;
};

const cases = [
  {
    definition: "/properties/vertebrateAnimals/properties/avmaConsistent",
    pointer: ["vertebrateAnimals", "animalEuthanized"],
    enabled: "Y: Yes",
    disabled: "N: No",
  },
  {
    definition: "/properties/vertebrateAnimals/properties/methodDescription",
    pointer: ["vertebrateAnimals", "avmaConsistent"],
    enabled: "N: No",
    disabled: "Y: Yes",
  },
  ...["specificLineUnavailable", "cellLines"].map((field) => ({
    definition: `/properties/humanEmbryonicStemCells/properties/${field}`,
    pointer: ["humanEmbryonicStemCells", "involved"],
    enabled: "Y: Yes",
    disabled: "N: No",
  })),
  ...["complianceAssurance", "irbConsentForm"].map((field) => ({
    definition: `/properties/humanFetalTissue/properties/${field}`,
    pointer: ["humanFetalTissue", "involved"],
    enabled: "Y: Yes",
    disabled: "N: No",
  })),
  {
    definition:
      "/properties/inventionsAndPatents/properties/previouslyReported",
    pointer: ["inventionsAndPatents", "inventions"],
    enabled: "Y: Yes",
    disabled: "N: No",
  },
  ...["prefix", "firstName", "middleName", "lastName", "suffix"].map(
    (field) => ({
      definition: `/properties/formerProjectDirector/properties/${field}`,
      pointer: ["changes", "changeOfProjectDirector"],
      enabled: "Y: Yes",
      disabled: "N: No",
    }),
  ),
  {
    definition: "/properties/formerOrganizationName",
    pointer: ["changes", "changeOfRecipientOrganization"],
    enabled: "Y: Yes",
    disabled: "N: No",
  },
];

const rootData = (pointer: string[], value: string): Record<string, unknown> =>
  pointer.reduceRight<Record<string, unknown>>(
    (nested, segment) => ({ [segment]: nested }),
    value as unknown as Record<string, unknown>,
  );

describe("PHS 398 Cover Page Supplement compiled condition transitions", () => {
  it("accounts for every compiled conditional field", () => {
    expect(cases).toHaveLength(13);
    expect(nodes(artifact).filter((node) => node.conditional)).toHaveLength(13);
  });

  it.each(cases)("enables $definition at its compiled trigger", (row) => {
    expect(
      resolveConditionalUiState(conditionFor(row.definition), {
        rootData: rootData(row.pointer, row.enabled),
      }).interaction,
    ).toBe("enabled");
  });

  it.each(cases)("disables $definition outside its compiled trigger", (row) => {
    expect(
      resolveConditionalUiState(conditionFor(row.definition), {
        rootData: rootData(row.pointer, row.disabled),
      }).interaction,
    ).toBe("disabled");
  });
});
