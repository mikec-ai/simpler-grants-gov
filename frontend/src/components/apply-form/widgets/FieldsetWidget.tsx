import { JSX } from "react";
import { Fieldset, FormGroup } from "@trussworks/react-uswds";

export const FieldsetWidget = ({
  label,
  fieldName,
  children,
  description,
}: {
  label: string;
  fieldName: string;
  children: JSX.Element | undefined;
  description?: string;
}) => {
  const headingId = `form-section-${fieldName}-heading`;
  const descriptionGraphs = description
    ?.split("\n")
    .filter(Boolean)
    .map((paragraph, i) => (
      <p key={`${label}-section-description-paragraph-${i}`}>{paragraph}</p>
    ));
  return (
    <Fieldset
      key={`${fieldName}-row`}
      id={`form-section-${fieldName}`}
      tabIndex={-1}
      aria-labelledby={headingId}
    >
      <FormGroup key={`${fieldName}-group`} className="simpler-formgroup">
        <h4
          id={headingId}
          key={`${fieldName}-legend`}
          className="usa-legend font-sans-lg margin-bottom-05 margin-top-5"
        >
          {label}
        </h4>
        {descriptionGraphs}
        {children}
      </FormGroup>
    </Fieldset>
  );
};
