import {
  evaluateConditionalUiPredicate,
  resolveConditionalUiState,
} from "src/utils/applyForm/evaluateConditionalUi";

describe("conditional UI evaluation", () => {
  const rootData = {
    submission_type_code: "Change/Corrected Application",
    applicant_type: { applicant_type_code: "R: Small Business" },
  };

  it("evaluates an exact root-data reference", () => {
    expect(
      evaluateConditionalUiPredicate(
        {
          op: "equals",
          ref: { scope: "root", pointer: "/submission_type_code" },
          value: "Change/Corrected Application",
        },
        { rootData },
      ),
    ).toBe(true);
  });

  it("supports nested references and boolean composition", () => {
    expect(
      evaluateConditionalUiPredicate(
        {
          op: "all",
          predicates: [
            {
              op: "present",
              ref: { scope: "root", pointer: "/applicant_type" },
            },
            {
              op: "in",
              ref: {
                scope: "root",
                pointer: "/applicant_type/applicant_type_code",
              },
              values: ["R: Small Business", "X: Other (specify)"],
            },
          ],
        },
        { rootData },
      ),
    ).toBe(true);
  });

  it("treats missing references as false rather than throwing", () => {
    expect(
      evaluateConditionalUiPredicate(
        {
          op: "equals",
          ref: { scope: "root", pointer: "/missing" },
          value: "anything",
        },
        { rootData },
      ),
    ).toBe(false);
  });

  it("evaluates array-count thresholds", () => {
    expect(
      evaluateConditionalUiPredicate(
        {
          op: "countAtLeast",
          ref: { scope: "root", pointer: "/sites" },
          minimum: 2,
        },
        { rootData: { sites: [{}, {}] } },
      ),
    ).toBe(true);
    expect(
      evaluateConditionalUiPredicate(
        {
          op: "countAtLeast",
          ref: { scope: "root", pointer: "/sites" },
          minimum: 3,
        },
        { rootData: { sites: [{}, {}] } },
      ),
    ).toBe(false);
  });

  it("resolves the selected branch over safe defaults", () => {
    expect(
      resolveConditionalUiState(
        {
          when: {
            op: "equals",
            ref: { scope: "root", pointer: "/submission_type_code" },
            value: "New",
          },
          then: { visible: true },
          otherwise: { visible: false },
        },
        { rootData },
      ),
    ).toEqual({ visible: false, interaction: "enabled" });
  });
});
