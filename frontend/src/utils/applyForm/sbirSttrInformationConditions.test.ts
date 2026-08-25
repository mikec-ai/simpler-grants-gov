import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ConditionalUi } from "src/types/applyForm/conditionalUiTypes";
import type { UiSchema, UiSchemaNode } from "src/types/applyForm/types";
import { resolveConditionalUiState } from "src/utils/applyForm/evaluateConditionalUi";

const artifact = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      "../../../../api/src/form_schema/form_spec/artifacts/forms/sbir-sttr-information/sgg/ui-schema.json",
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
      `Missing artifact-backed SBIR/STTR condition for ${definition}`,
    );
  }
  return field.conditional;
};

const cases = [
  [
    "/properties/otherAgency",
    { agency: { value: "Other" } },
    { agency: { value: "NIH" } },
  ],
  [
    "/properties/federalSubcontractorNames",
    { federalSubcontractsIncluded: { value: "Y: Yes" } },
    { federalSubcontractsIncluded: { value: "N: No" } },
  ],
  [
    "/properties/nonDomesticPerformanceExplanation",
    { domesticPerformance: { value: "N: No" } },
    { domesticPerformance: { value: "Y: Yes" } },
  ],
  [
    "/properties/equivalentWorkFederalAgencies",
    { equivalentFederalWork: { value: "Y: Yes" } },
    { equivalentFederalWork: { value: "N: No" } },
  ],
  [
    "/properties/phaseIIAwardsReceived/properties/value",
    { programType: { value: "SBIR" } },
    { programType: { value: "STTR" } },
  ],
  [
    "/properties/commercializationHistory",
    { phaseIIAwardsReceived: { value: "Y: Yes" } },
    { phaseIIAwardsReceived: { value: "N: No" } },
  ],
  [
    "/properties/pdpiPrimaryEmployment/properties/value",
    { programType: { value: "Both" } },
    { programType: { value: "STTR" } },
  ],
  [
    "/properties/pdpiAppointmentAndEffort/properties/value",
    { programType: { value: "STTR" } },
    { programType: { value: "SBIR" } },
  ],
  [
    "/properties/jointPerformancePercentage/properties/value",
    { programType: { value: "Both" } },
    { programType: { value: "SBIR" } },
  ],
  [
    "/properties/nonprofitResearchPartnerUei",
    { programType: { value: "STTR" } },
    { programType: { value: "SBIR" } },
  ],
] as const;

describe("SBIR/STTR compiled condition transitions", () => {
  it.each(cases)(
    "enables and disables %s from source-bound values",
    (definition, active, inactive) => {
      const condition = conditionFor(definition);
      expect(
        resolveConditionalUiState(condition, { rootData: active }).interaction,
      ).toBe("enabled");
      expect(
        resolveConditionalUiState(condition, { rootData: inactive })
          .interaction,
      ).toBe("disabled");
    },
  );
});
