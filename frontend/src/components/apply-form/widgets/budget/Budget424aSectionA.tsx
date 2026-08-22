"use client";

import { FormContextType, RJSFSchema, StrictRJSFSchema } from "@rjsf/utils";
import {
  FormValidationWarning,
  UswdsWidgetProps,
} from "src/types/applyForm/types";

import React, { JSX } from "react";
import { Table } from "@trussworks/react-uswds";

import TextWidget from "src/components/apply-form/widgets/TextWidget";
import InfoTooltip from "src/components/core/tooltip/InfoTooltip";
import { ACTIVITY_ITEMS } from "./budgetConstants";
import { getErrorsForSection } from "./budgetErrors";
import {
  activityTitleSchema,
  assistanceListingNumberSchema,
} from "./budgetSchemas";
import { BaseActivityItem, MoneyString } from "./budgetTypes";
import { CurrencyInput, DataCell, HelperText } from "./budgetUiComponents";
import { asMoney, isRecord } from "./budgetValueGuards";

interface BudgetSummary {
  federal_estimated_unobligated_amount?: MoneyString;
  non_federal_estimated_unobligated_amount?: MoneyString;
  federal_new_or_revised_amount?: MoneyString;
  non_federal_new_or_revised_amount?: MoneyString;
  total_amount?: MoneyString;
}

interface ActivityItem extends BaseActivityItem {
  budget_summary?: BudgetSummary;
}

type NormalizedA = {
  items: ActivityItem[];
  totals?: BudgetSummary;
};

type SectionAFieldSchemas = {
  activityTitle: RJSFSchema;
  assistanceListingNumber: RJSFSchema;
  federalEstimatedUnobligatedAmount: RJSFSchema;
  nonFederalEstimatedUnobligatedAmount: RJSFSchema;
  federalNewOrRevisedAmount: RJSFSchema;
  nonFederalNewOrRevisedAmount: RJSFSchema;
  totalAmount: RJSFSchema;
};

function propertySchema(value: unknown, name: string): RJSFSchema {
  if (!isRecord(value) || !isRecord(value.properties)) return {};
  const property = value.properties[name];
  return isRecord(property) ? property : {};
}

function sectionAFieldSchemas(rootSchema: unknown): SectionAFieldSchemas {
  const root = isRecord(rootSchema) ? rootSchema : {};
  const definitions = isRecord(root.$defs) ? root.$defs : {};
  const activityDefinition = isRecord(definitions.ActivityLineItem)
    ? definitions.ActivityLineItem
    : {};
  const activityItems = propertySchema(root, "activity_line_items");
  const activityItem = isRecord(activityItems.items) ? activityItems.items : {};
  const totalBudgetSummary = propertySchema(root, "total_budget_summary");
  const mergeActivity = (name: string, fallback: RJSFSchema): RJSFSchema => ({
    ...fallback,
    ...propertySchema(activityDefinition, name),
    ...propertySchema(activityItem, name),
  });

  return {
    activityTitle: mergeActivity("activity_title", activityTitleSchema),
    assistanceListingNumber: mergeActivity(
      "assistance_listing_number",
      assistanceListingNumberSchema,
    ),
    federalEstimatedUnobligatedAmount: propertySchema(
      totalBudgetSummary,
      "federal_estimated_unobligated_amount",
    ),
    nonFederalEstimatedUnobligatedAmount: propertySchema(
      totalBudgetSummary,
      "non_federal_estimated_unobligated_amount",
    ),
    federalNewOrRevisedAmount: propertySchema(
      totalBudgetSummary,
      "federal_new_or_revised_amount",
    ),
    nonFederalNewOrRevisedAmount: propertySchema(
      totalBudgetSummary,
      "non_federal_new_or_revised_amount",
    ),
    totalAmount: propertySchema(totalBudgetSummary, "total_amount"),
  };
}

function title(schema: RJSFSchema, fallback: string): string {
  return typeof schema.title === "string" ? schema.title : fallback;
}

function HeaderHelp({ schema }: { schema: RJSFSchema }): JSX.Element | null {
  if (typeof schema.description !== "string") return null;
  return (
    <InfoTooltip
      text={schema.description}
      title={`Help for ${title(schema, "this field")}`}
      wrapperClasses="margin-left-05"
    />
  );
}

function pickBudgetSummary(value: unknown): BudgetSummary {
  if (!isRecord(value)) return {};
  return {
    federal_estimated_unobligated_amount: asMoney(
      value.federal_estimated_unobligated_amount,
    ),
    non_federal_estimated_unobligated_amount: asMoney(
      value.non_federal_estimated_unobligated_amount,
    ),
    federal_new_or_revised_amount: asMoney(value.federal_new_or_revised_amount),
    non_federal_new_or_revised_amount: asMoney(
      value.non_federal_new_or_revised_amount,
    ),
    total_amount: asMoney(value.total_amount),
  };
}

function pickActivityItemA(value: unknown): ActivityItem {
  if (!isRecord(value)) return {};
  const out: ActivityItem = {};
  if (typeof value.activity_title === "string") {
    out.activity_title = value.activity_title;
  }
  if (typeof value.assistance_listing_number === "string") {
    out.assistance_listing_number = value.assistance_listing_number;
  }
  if (isRecord(value.budget_summary)) {
    out.budget_summary = pickBudgetSummary(value.budget_summary);
  }
  return out;
}

function normalizeSectionAValue(raw: unknown): NormalizedA {
  if (isRecord(raw) && Array.isArray(raw.activity_line_items)) {
    return {
      items: raw.activity_line_items.map(pickActivityItemA),
      totals: pickBudgetSummary(raw.total_budget_summary),
    };
  }

  if (isRecord(raw)) {
    const items: ActivityItem[] = [];
    for (let i = 0; i < 4; i++) {
      items.push(pickActivityItemA(raw[String(i)]));
    }

    const totals =
      pickBudgetSummary(raw.total_budget_summary) || pickBudgetSummary(raw);

    const hasAnyTotal =
      totals.federal_estimated_unobligated_amount ||
      totals.non_federal_estimated_unobligated_amount ||
      totals.federal_new_or_revised_amount ||
      totals.non_federal_new_or_revised_amount ||
      totals.total_amount;

    return { items, totals: hasAnyTotal ? totals : undefined };
  }

  return { items: [] };
}

function Budget424aSectionA<
  T = unknown,
  S extends StrictRJSFSchema = RJSFSchema,
  F extends FormContextType = never,
>({
  id,
  value,
  rawErrors,
  formContext,
  readOnly,
  disabled,
}: UswdsWidgetProps<T, S, F>): JSX.Element {
  const rootFormDataFromContext = formContext?.rootFormData;
  const rawValue: unknown = rootFormDataFromContext ?? value ?? {};
  const errors = (rawErrors as FormValidationWarning[]) || [];
  const { items, totals } = normalizeSectionAValue(rawValue);
  const fieldSchemas = sectionAFieldSchemas(formContext?.rootSchema);
  const getErrorsA = getErrorsForSection("A");
  const itemAt = (row: number): ActivityItem => items[row] ?? {};
  const getItemVal = (
    row: number,
    path: keyof ActivityItem,
  ): string | undefined => itemAt(row)[path] as string | undefined;
  const getBudgetVal = (
    row: number,
    path: keyof BudgetSummary,
  ): string | undefined => itemAt(row).budget_summary?.[path];

  return (
    <div key={id} id={id}>
      <Table
        bordered={false}
        className="sf424__table usa-table--borderless width-full border-1px border-base-light"
      >
        <thead className="text-bold">
          <tr className="bg-base-lighter">
            <th
              scope="col"
              className="bg-base-lightest text-bold border-bottom-0 width-card border-base-light"
              rowSpan={2}
            >
              <div>
                {title(
                  fieldSchemas.activityTitle,
                  "Grant program, function, or activity",
                )}
                <HeaderHelp schema={fieldSchemas.activityTitle} />
              </div>
            </th>
            <th
              scope="col"
              className="bg-base-lightest text-bold border-bottom-0 border-x-1px text-center border-base-light"
              rowSpan={2}
            >
              {title(
                fieldSchemas.assistanceListingNumber,
                "Assistance Listing number",
              )}
              <HeaderHelp schema={fieldSchemas.assistanceListingNumber} />
            </th>
            <th
              scope="colgroup"
              className="bg-base-lightest text-bold border-x-1px border-base-light"
              colSpan={2}
            >
              <span className="text-no-wrap">Estimated unobligated funds</span>
            </th>
            <th
              scope="colgroup"
              className="bg-base-lightest text-bold border-x-1px border-base-light"
              colSpan={2}
            >
              New or revised budget
            </th>
            <th
              scope="col"
              className="bg-base-lightest text-bold border-bottom-0 border-x-1px text-center border-base-light"
              rowSpan={2}
            >
              Total
              <HeaderHelp schema={fieldSchemas.totalAmount} />
            </th>
          </tr>
          <tr>
            <th
              scope="col"
              className="bg-base-lightest text-bold border-bottom-0 border-x-1px border-base-light"
            >
              Federal{" "}
              <HeaderHelp
                schema={fieldSchemas.federalEstimatedUnobligatedAmount}
              />
            </th>
            <th
              scope="col"
              className="bg-base-lightest text-bold border-bottom-0"
            >
              Non-federal{" "}
              <HeaderHelp
                schema={fieldSchemas.nonFederalEstimatedUnobligatedAmount}
              />
            </th>
            <th
              scope="col"
              className="bg-base-lightest text-bold border-bottom-0 border-x-1px border-base-light"
            >
              Federal{" "}
              <HeaderHelp schema={fieldSchemas.federalNewOrRevisedAmount} />
            </th>
            <th
              scope="col"
              className="bg-base-lightest text-bold border-bottom-0"
            >
              Non-federal{" "}
              <HeaderHelp schema={fieldSchemas.nonFederalNewOrRevisedAmount} />
            </th>
          </tr>
          <tr className="bg-base-lightest text-bold text-center">
            <th
              scope="col"
              aria-label="Column A"
              className="bg-base-lightest text-bold border-top-0"
            >
              A
            </th>
            <th
              scope="col"
              aria-label="Column B"
              className="bg-base-lightest text-bold border-top-0 border-x-1px border-base-light"
            >
              B
            </th>
            <th
              scope="col"
              aria-label="Column C"
              className="bg-base-lightest text-bold border-top-0"
            >
              C
            </th>
            <th
              scope="col"
              aria-label="Column D"
              className="bg-base-lightest text-bold border-top-0 border-x-1px border-base-light"
            >
              D
            </th>
            <th
              scope="col"
              aria-label="Column E"
              className="bg-base-lightest text-bold border-top-0 border-x-1px border-base-light"
            >
              E
            </th>
            <th
              scope="col"
              aria-label="Column F"
              className="bg-base-lightest text-bold border-top-0"
            >
              F
            </th>
            <th
              scope="col"
              aria-label="Column G"
              className="bg-base-lightest text-bold border-top-0 border-x-1px border-base-light"
            >
              G
            </th>
          </tr>
        </thead>

        <tbody>
          {ACTIVITY_ITEMS.map((row) => (
            <tr key={row}>
              {/* Column A: activity title */}
              <DataCell className="sf424a-section-a__activity-cell">
                <div className="display-flex flex-align-end">
                  <span className="text-bold text-no-wrap margin-right-2">
                    {row + 1}.
                  </span>
                  <div className="margin-top-05 padding-top-0">
                    <div className="sf424a-application-view-only">
                      <TextWidget
                        schema={fieldSchemas.activityTitle}
                        hideLabel
                        aria-label={`${title(fieldSchemas.activityTitle, "Grant program, function, or activity")}, row ${row + 1}`}
                        id={`activity_line_items[${row}]--activity_title`}
                        rawErrors={getErrorsA({
                          errors,
                          id: `activity_line_items[${row}]--activity_title`,
                        })}
                        formClassName="margin-left-2"
                        inputClassName="minw-10 sf424a-section-a__activity-input"
                        value={getItemVal(row, "activity_title")}
                        disabled={disabled}
                        readOnly={readOnly}
                      />
                    </div>

                    {/*
                    Print only value - we hide the input only for print and show the value here-
                    due to the unpredictability of what the activity names may be,
                    it might get cut off and impossible to read.
                    */}
                    <div className="sf424a-print-only-view sf424a-section-a__activity-print-value">
                      {getItemVal(row, "activity_title") || "—"}
                    </div>
                  </div>
                </div>
              </DataCell>

              {/* Column B: assistance listing */}
              <DataCell className="sf424a-section-a__assistance-cell">
                <div className="display-flex flex-align-end">
                  <div className="margin-top-05 padding-top-0">
                    <div className="sf424a-application-view-only">
                      <TextWidget
                        schema={fieldSchemas.assistanceListingNumber}
                        hideLabel
                        aria-label={`${title(fieldSchemas.assistanceListingNumber, "Assistance Listing number")}, row ${row + 1}`}
                        id={`activity_line_items[${row}]--assistance_listing_number`}
                        rawErrors={getErrorsA({
                          errors,
                          id: `activity_line_items[${row}]--assistance_listing_number`,
                        })}
                        inputClassName="minw-10 sf424a-section-a__assistance-input"
                        value={getItemVal(row, "assistance_listing_number")}
                        disabled={disabled}
                        readOnly={readOnly}
                      />
                    </div>

                    {/*
                    Print only value - we hide the input only for print and show the value here-
                    due to the unpredictability of what the activity names may be,
                    it might get cut off and impossible to read.
                    */}
                    <div className="sf424a-print-only-view sf424a-section-a__activity-print-value">
                      {getItemVal(row, "assistance_listing_number") || "—"}
                    </div>
                  </div>
                </div>
              </DataCell>

              {/* Column C: federal estimated unobligated */}
              <DataCell>
                <div className="display-flex flex-align-end">
                  <div className="margin-top-3 padding-top-0">
                    <CurrencyInput
                      id={`activity_line_items[${row}]--budget_summary--federal_estimated_unobligated_amount`}
                      rawErrors={getErrorsA({
                        errors,
                        id: `activity_line_items[${row}]--budget_summary--federal_estimated_unobligated_amount`,
                      })}
                      value={getBudgetVal(
                        row,
                        "federal_estimated_unobligated_amount",
                      )}
                      disabled={disabled}
                      readOnly={readOnly}
                      schema={fieldSchemas.federalEstimatedUnobligatedAmount}
                      hideLabel
                      ariaLabel={`${title(fieldSchemas.federalEstimatedUnobligatedAmount, "Estimated unobligated federal funds")}, row ${row + 1}`}
                    />
                  </div>
                </div>
              </DataCell>

              {/* Column D: non-federal estimated unobligated */}
              <DataCell>
                <div className="display-flex flex-align-end">
                  <div className="margin-top-3 padding-top-0">
                    <CurrencyInput
                      id={`activity_line_items[${row}]--budget_summary--non_federal_estimated_unobligated_amount`}
                      rawErrors={getErrorsA({
                        errors,
                        id: `activity_line_items[${row}]--budget_summary--non_federal_estimated_unobligated_amount`,
                      })}
                      value={getBudgetVal(
                        row,
                        "non_federal_estimated_unobligated_amount",
                      )}
                      disabled={disabled}
                      readOnly={readOnly}
                      schema={fieldSchemas.nonFederalEstimatedUnobligatedAmount}
                      hideLabel
                      ariaLabel={`${title(fieldSchemas.nonFederalEstimatedUnobligatedAmount, "Estimated unobligated non-federal funds")}, row ${row + 1}`}
                    />
                  </div>
                </div>
              </DataCell>

              {/* Column E: federal new/revised */}
              <DataCell>
                <div className="display-flex flex-align-end">
                  <div className="margin-top-3 padding-top-0">
                    <CurrencyInput
                      id={`activity_line_items[${row}]--budget_summary--federal_new_or_revised_amount`}
                      rawErrors={getErrorsA({
                        errors,
                        id: `activity_line_items[${row}]--budget_summary--federal_new_or_revised_amount`,
                      })}
                      value={getBudgetVal(row, "federal_new_or_revised_amount")}
                      disabled={disabled}
                      readOnly={readOnly}
                      schema={fieldSchemas.federalNewOrRevisedAmount}
                      hideLabel
                      ariaLabel={`${title(fieldSchemas.federalNewOrRevisedAmount, "New or revised federal budget")}, row ${row + 1}`}
                    />
                  </div>
                </div>
              </DataCell>

              {/* Column F: non-federal new/revised */}
              <DataCell>
                <div className="display-flex flex-align-end">
                  <div className="margin-top-3 padding-top-0">
                    <CurrencyInput
                      id={`activity_line_items[${row}]--budget_summary--non_federal_new_or_revised_amount`}
                      rawErrors={getErrorsA({
                        errors,
                        id: `activity_line_items[${row}]--budget_summary--non_federal_new_or_revised_amount`,
                      })}
                      value={getBudgetVal(
                        row,
                        "non_federal_new_or_revised_amount",
                      )}
                      disabled={disabled}
                      readOnly={readOnly}
                      schema={fieldSchemas.nonFederalNewOrRevisedAmount}
                      hideLabel
                      ariaLabel={`${title(fieldSchemas.nonFederalNewOrRevisedAmount, "New or revised non-federal budget")}, row ${row + 1}`}
                    />
                  </div>
                </div>
              </DataCell>

              {/* Column G: total */}
              <DataCell>
                <div className="display-flex flex-align-end">
                  <div>
                    <CurrencyInput
                      id={`activity_line_items[${row}]--budget_summary--total_amount`}
                      rawErrors={getErrorsA({
                        errors,
                        id: `activity_line_items[${row}]--budget_summary--total_amount`,
                      })}
                      value={getBudgetVal(row, "total_amount")}
                      disabled={disabled}
                      readOnly={readOnly}
                      schema={fieldSchemas.totalAmount}
                      hideLabel
                      ariaLabel={`${title(fieldSchemas.totalAmount, "Total budgeted amount")}, row ${row + 1}`}
                    />
                  </div>
                </div>
              </DataCell>
            </tr>
          ))}

          {/* Totals row */}
          <tr>
            <th scope="row" className="padding-05 text-bold" colSpan={2}>
              <div className="display-flex">
                <span className="margin-right-5">5.</span>
                <div>
                  Total
                  <div className="text-normal text-no-wrap text-italic">
                    (sum of 1-4)
                  </div>
                </div>
              </div>
            </th>

            <td className="padding-05">
              <HelperText hasHorizontalLine>Sum of column C</HelperText>
              <CurrencyInput
                disabled
                id={
                  "total_budget_summary--federal_estimated_unobligated_amount"
                }
                rawErrors={getErrorsA({
                  errors,
                  id: "total_budget_summary--federal_estimated_unobligated_amount",
                })}
                value={totals?.federal_estimated_unobligated_amount}
                bordered
                schema={fieldSchemas.federalEstimatedUnobligatedAmount}
                hideLabel
                ariaLabel={`${title(fieldSchemas.federalEstimatedUnobligatedAmount, "Estimated unobligated federal funds")}, total row`}
              />
            </td>

            <td className="padding-05">
              <HelperText hasHorizontalLine>Sum of column D</HelperText>
              <CurrencyInput
                disabled
                id={
                  "total_budget_summary--non_federal_estimated_unobligated_amount"
                }
                rawErrors={getErrorsA({
                  errors,
                  id: "total_budget_summary--non_federal_estimated_unobligated_amount",
                })}
                value={totals?.non_federal_estimated_unobligated_amount}
                bordered
                schema={fieldSchemas.nonFederalEstimatedUnobligatedAmount}
                hideLabel
                ariaLabel={`${title(fieldSchemas.nonFederalEstimatedUnobligatedAmount, "Estimated unobligated non-federal funds")}, total row`}
              />
            </td>

            <td className="padding-05">
              <HelperText hasHorizontalLine>Sum of column E</HelperText>
              <CurrencyInput
                disabled
                id={"total_budget_summary--federal_new_or_revised_amount"}
                rawErrors={getErrorsA({
                  errors,
                  id: "total_budget_summary--federal_new_or_revised_amount",
                })}
                value={totals?.federal_new_or_revised_amount}
                bordered
                schema={fieldSchemas.federalNewOrRevisedAmount}
                hideLabel
                ariaLabel={`${title(fieldSchemas.federalNewOrRevisedAmount, "New or revised federal budget")}, total row`}
              />
            </td>

            <td className="padding-05">
              <HelperText hasHorizontalLine>Sum of column F</HelperText>
              <CurrencyInput
                disabled
                id={"total_budget_summary--non_federal_new_or_revised_amount"}
                rawErrors={getErrorsA({
                  errors,
                  id: "total_budget_summary--non_federal_new_or_revised_amount",
                })}
                value={totals?.non_federal_new_or_revised_amount}
                bordered
                schema={fieldSchemas.nonFederalNewOrRevisedAmount}
                hideLabel
                ariaLabel={`${title(fieldSchemas.nonFederalNewOrRevisedAmount, "New or revised non-federal budget")}, total row`}
              />
            </td>

            <td className="padding-05">
              <HelperText hasHorizontalLine>Sum of column G</HelperText>
              <CurrencyInput
                disabled
                id={"total_budget_summary--total_amount"}
                rawErrors={getErrorsA({
                  errors,
                  id: "total_budget_summary--total_amount",
                })}
                value={totals?.total_amount}
                bordered
                schema={fieldSchemas.totalAmount}
                hideLabel
                ariaLabel={`${title(fieldSchemas.totalAmount, "Total budgeted amount")}, total row`}
              />
            </td>
          </tr>
        </tbody>
      </Table>
    </div>
  );
}

export default Budget424aSectionA;
