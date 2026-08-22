"use client";

import React from "react";
import { Label } from "@trussworks/react-uswds";

export type DynamicLabelType = "default" | "hide-helper-text";

type DynamicFieldLabelProps = {
  idFor: string;
  title: string | undefined;
  required?: boolean;
  description?: string;
  descriptionId?: string;
  visuallyHidden?: boolean;
  labelType?: DynamicLabelType;
};

export const DynamicFieldLabel = ({
  idFor,
  title,
  required = false,
  description,
  descriptionId,
  visuallyHidden = false,
  labelType = "default",
}: DynamicFieldLabelProps) => {
  if (!title) return null;

  const labelContent = (
    <>
      {title}
      {required && (
        <span className="usa-hint usa-hint--required text-no-underline">*</span>
      )}
    </>
  );

  switch (labelType) {
    case "hide-helper-text":
      return (
        <Label
          htmlFor={idFor}
          id={`label-for-${idFor}`}
          className={visuallyHidden ? "usa-sr-only" : undefined}
        >
          {labelContent}
        </Label>
      );

    /* 
    TODO: get design / product approval
    waiting on design approval

    case "with-tooltip":
      return (
        <div className="display-flex flex-align-center">
           <Label htmlFor={idFor} id={`label-for-${idFor}`}>
             {labelContent}
           </Label>
           {description && (
             <Tooltip label="More info" className="margin-left-1">
               {description}
             </Tooltip>
           )}
         </div>
       );
    */

    case "default":
    default:
      return (
        <>
          <Label
            htmlFor={idFor}
            id={`label-for-${idFor}`}
            className={visuallyHidden ? "usa-sr-only" : undefined}
          >
            {labelContent}
          </Label>
          {description && (
            <p
              id={descriptionId}
              className={
                visuallyHidden ? "usa-sr-only" : "text-base-dark margin-top-0"
              }
            >
              {description}
            </p>
          )}
        </>
      );
  }
};
