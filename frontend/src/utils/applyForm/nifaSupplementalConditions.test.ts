import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ConditionalUi } from "src/types/applyForm/conditionalUiTypes";
import type { UiSchema, UiSchemaNode } from "src/types/applyForm/types";
import { resolveConditionalUiState } from "src/utils/applyForm/evaluateConditionalUi";

const artifact = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      "../../../../api/src/form_schema/form_spec/artifacts/forms/nifa-supplemental/sgg/ui-schema.json",
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
    throw new Error(`Missing artifact-backed NIFA condition for ${definition}`);
  }
  return field.conditional;
};

const additionalApplicantTypeCondition = conditionFor(
  "/properties/additionalApplicantType/properties/additionalApplicantType",
);
const recipientIdCondition = conditionFor(
  "/properties/asapRecipientInformation/properties/recipientId",
);

describe("NIFA Supplemental compiled condition transitions", () => {
  it.each([
    "H: Public/state Controlled Institution of Higher Education",
    "X: Other (specify)",
  ])("enables additional applicant type for %s", (applicantTypeCode) => {
    expect(
      resolveConditionalUiState(additionalApplicantTypeCondition, {
        rootData: { applicantType: { applicantTypeCode } },
      }).interaction,
    ).toBe("enabled");
  });

  it("disables additional applicant type for other applicant types", () => {
    expect(
      resolveConditionalUiState(additionalApplicantTypeCondition, {
        rootData: {
          applicantType: { applicantTypeCode: "A: State Government" },
        },
      }).interaction,
    ).toBe("disabled");
  });

  it("shows recipient ID when the applicant has an active ASAP ID", () => {
    expect(
      resolveConditionalUiState(recipientIdCondition, {
        rootData: {
          asapRecipientInformation: { hasActiveAsapRecipientId: true },
        },
      }).visible,
    ).toBe(true);
  });

  it("hides recipient ID when the applicant does not have an active ASAP ID", () => {
    expect(
      resolveConditionalUiState(recipientIdCondition, {
        rootData: {
          asapRecipientInformation: { hasActiveAsapRecipientId: false },
        },
      }).visible,
    ).toBe(false);
  });
});
