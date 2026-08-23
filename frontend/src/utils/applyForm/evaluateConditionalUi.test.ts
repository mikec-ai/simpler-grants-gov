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

  it("keeps an overflow attachment enabled at capacity or while its saved value is present", () => {
    const predicate = {
      op: "any" as const,
      predicates: [
        {
          op: "countAtLeast" as const,
          ref: { scope: "root" as const, pointer: "/people" },
          minimum: 99,
        },
        {
          op: "present" as const,
          ref: { scope: "root" as const, pointer: "/overflow_attachment" },
        },
      ],
    };

    expect(
      evaluateConditionalUiPredicate(predicate, {
        rootData: { people: Array.from({ length: 99 }, () => ({})) },
      }),
    ).toBe(true);
    expect(
      evaluateConditionalUiPredicate(predicate, {
        rootData: { people: [], overflow_attachment: "attachment-uuid" },
      }),
    ).toBe(true);
    expect(
      evaluateConditionalUiPredicate(predicate, {
        rootData: { people: [], overflow_attachment: "" },
      }),
    ).toBe(false);
  });

  it("treats false and zero as present scalar answers but null, blank, and empty lists as absent", () => {
    const present = (value: unknown) =>
      evaluateConditionalUiPredicate(
        {
          op: "present",
          ref: { scope: "root", pointer: "/value" },
        },
        { rootData: { value } },
      );

    expect(present(false)).toBe(true);
    expect(present(0)).toBe(true);
    expect(present("attachment-uuid")).toBe(true);
    expect(present({ id: "attachment-uuid" })).toBe(true);
    expect(present(null)).toBe(false);
    expect(present("")).toBe(false);
    expect(present([])).toBe(false);
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
