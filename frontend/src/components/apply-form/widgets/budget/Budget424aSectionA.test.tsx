import { render, screen } from "@testing-library/react";
import { RJSFSchema } from "@rjsf/utils";

import Budget424aSectionA from "src/components/apply-form/widgets/budget/Budget424aSectionA";
import budget424a from "./budget424a.mock.json";

jest.mock("src/components/core/tooltip/InfoTooltip", () => ({
  __esModule: true,
  default: ({ text, title }: { text: string; title: string }) => (
    <span aria-label={title}>{text}</span>
  ),
}));

const WidgetProps = {
  id: "test",
  schema: {},
  value: {
    ...budget424a.activity_line_items,
    ...budget424a.total_budget_summary,
  },
  options: {},
  formContext: {
    rootFormData: budget424a,
    rootSchema: {
      type: "object",
      $defs: {
        ActivityLineItem: {
          type: "object",
          properties: {
            activity_title: {
              type: "string",
              title: "Grant program, function, or activity",
            },
            assistance_listing_number: {
              type: "string",
              title: "Assistance Listing number",
            },
          },
        },
      },
      properties: {
        activity_line_items: {
          type: "array",
          items: {
            properties: {
              activity_title: {
                description: "Enter the program or activity identifier.",
              },
              assistance_listing_number: {
                description: "Enter the Assistance Listing number.",
              },
            },
          },
        },
        total_budget_summary: {
          type: "object",
          properties: {
            federal_estimated_unobligated_amount: {
              type: "string",
              title: "Estimated unobligated federal funds",
              description: "Federal funds not yet obligated.",
            },
            non_federal_estimated_unobligated_amount: {
              type: "string",
              title: "Estimated unobligated non-federal funds",
              description: "Non-federal funds not yet obligated.",
            },
            federal_new_or_revised_amount: {
              type: "string",
              title: "New or revised federal budget",
              description: "Federal funds needed for the upcoming period.",
            },
            non_federal_new_or_revised_amount: {
              type: "string",
              title: "New or revised non-federal budget",
              description: "Non-federal funds needed for the upcoming period.",
            },
            total_amount: {
              type: "string",
              title: "Total",
              description:
                "Enter the total budgeted amount. It is not calculated automatically.",
            },
          },
        },
      },
    } as RJSFSchema,
  },
};

describe("Budget424aSectionA", () => {
  it("sets the correct default value", () => {
    render(<Budget424aSectionA {...WidgetProps} />);
    const A1 = screen.getByTestId("activity_line_items[0]--activity_title");
    expect(A1).toHaveValue("ABCDEFGHIJKLMNOPQRSTUVWXYZABC");

    const B1 = screen.getByTestId(
      "activity_line_items[0]--assistance_listing_number",
    );
    expect(B1).toHaveValue("ABCDFC");

    const C1 = screen.getByTestId(
      "activity_line_items[0]--budget_summary--federal_estimated_unobligated_amount",
    );
    expect(C1).toHaveValue("12.30");

    const D1 = screen.getByTestId(
      "activity_line_items[0]--budget_summary--non_federal_estimated_unobligated_amount",
    );
    expect(D1).toHaveValue("4.53");

    const E1 = screen.getByTestId(
      "activity_line_items[0]--budget_summary--federal_new_or_revised_amount",
    );
    expect(E1).toHaveValue("24.23");

    const F1 = screen.getByTestId(
      "activity_line_items[0]--budget_summary--non_federal_new_or_revised_amount",
    );
    expect(F1).toHaveValue("32.43");
  });

  it("uses portable field meaning for accessible table inputs", () => {
    render(<Budget424aSectionA {...WidgetProps} />);

    expect(
      screen.getByRole("textbox", {
        name: "Grant program, function, or activity, row 1",
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Total, row 1" })).toBeEnabled();
    expect(
      screen.getByRole("columnheader", { name: "Column G" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/sum of C-F/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sum of row 1/i)).not.toBeInTheDocument();
  });

  it("locks every applicant-entered value, including Column G", () => {
    render(<Budget424aSectionA {...WidgetProps} disabled />);

    expect(
      screen.getByRole("textbox", { name: "Total, row 1" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("textbox", {
        name: "New or revised federal budget, row 1",
      }),
    ).toBeDisabled();
  });
});
