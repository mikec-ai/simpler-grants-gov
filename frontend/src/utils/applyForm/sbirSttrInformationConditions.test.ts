import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ConditionalUi } from "src/types/applyForm/conditionalUiTypes";
import { resolveConditionalUiState } from "src/utils/applyForm/evaluateConditionalUi";

const artifact = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      "../../../../api/tests/src/form_schema/form_spec/sbir_sttr_projected_conditions.json",
    ),
    "utf8",
  ),
) as Array<{ definition: string; conditional: ConditionalUi }>;

const conditionFor = (definition: string): ConditionalUi => {
  const field = artifact.find(
    (candidate) => candidate.definition === definition,
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
    "/properties/other_agency",
    { agency: { value: "Other" } },
    { agency: { value: "NIH" } },
  ],
  [
    "/properties/federal_subcontractor_names",
    { federal_subcontracts_included: { value: "Y: Yes" } },
    { federal_subcontracts_included: { value: "N: No" } },
  ],
  [
    "/properties/non_domestic_performance_explanation",
    { domestic_performance: { value: "N: No" } },
    { domestic_performance: { value: "Y: Yes" } },
  ],
  [
    "/properties/equivalent_work_federal_agencies",
    { equivalent_federal_work: { value: "Y: Yes" } },
    { equivalent_federal_work: { value: "N: No" } },
  ],
  [
    "/properties/phase_iiawards_received/properties/value",
    { program_type: { value: "SBIR" } },
    { program_type: { value: "STTR" } },
  ],
  [
    "/properties/commercialization_history",
    { phase_iiawards_received: { value: "Y: Yes" } },
    { phase_iiawards_received: { value: "N: No" } },
  ],
  [
    "/properties/pdpi_primary_employment/properties/value",
    { program_type: { value: "Both" } },
    { program_type: { value: "STTR" } },
  ],
  [
    "/properties/pdpi_appointment_and_effort/properties/value",
    { program_type: { value: "STTR" } },
    { program_type: { value: "SBIR" } },
  ],
  [
    "/properties/joint_performance_percentage/properties/value",
    { program_type: { value: "Both" } },
    { program_type: { value: "SBIR" } },
  ],
  [
    "/properties/nonprofit_research_partner_uei",
    { program_type: { value: "STTR" } },
    { program_type: { value: "SBIR" } },
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
