import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ConditionalUi } from "src/types/applyForm/conditionalUiTypes";
import type { UiSchema, UiSchemaNode } from "src/types/applyForm/types";
import { resolveConditionalUiState } from "src/utils/applyForm/evaluateConditionalUi";

const artifact = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      "__fixtures__/phs398-cover-page-supplement-ui-schema.json",
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
    definition: "/properties/vertebrate_animals/properties/avma_consistent",
    pointer: ["vertebrate_animals", "animal_euthanized"],
    enabled: "Y: Yes",
    disabled: "N: No",
  },
  {
    definition: "/properties/vertebrate_animals/properties/method_description",
    pointer: ["vertebrate_animals", "avma_consistent"],
    enabled: "N: No",
    disabled: "Y: Yes",
  },
  ...["specific_line_unavailable", "cell_lines"].map((field) => ({
    definition: `/properties/human_embryonic_stem_cells/properties/${field}`,
    pointer: ["human_embryonic_stem_cells", "involved"],
    enabled: "Y: Yes",
    disabled: "N: No",
  })),
  ...["compliance_assurance", "irb_consent_form"].map((field) => ({
    definition: `/properties/human_fetal_tissue/properties/${field}`,
    pointer: ["human_fetal_tissue", "involved"],
    enabled: "Y: Yes",
    disabled: "N: No",
  })),
  {
    definition:
      "/properties/inventions_and_patents/properties/previously_reported",
    pointer: ["inventions_and_patents", "inventions"],
    enabled: "Y: Yes",
    disabled: "N: No",
  },
  ...["prefix", "first_name", "middle_name", "last_name", "suffix"].map(
    (field) => ({
      definition: `/properties/former_project_director/properties/${field}`,
      pointer: ["changes", "change_of_project_director"],
      enabled: "Y: Yes",
      disabled: "N: No",
    }),
  ),
  {
    definition: "/properties/former_organization_name",
    pointer: ["changes", "change_of_recipient_organization"],
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
