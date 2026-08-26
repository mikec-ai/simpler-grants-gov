"use client";

import { RJSFSchema } from "@rjsf/utils";
import { isEmpty } from "lodash";
import { handleFormAction } from "src/app/[locale]/(base)/workspace/applications/[applicationId]/form/[appFormId]/actions";
import { AttachmentsProvider } from "src/hooks/ApplicationAttachments";
import {
  AttachmentsUploadingCounter,
  FormattedFormValidationWarning,
  FormValidationWarning,
  UiSchema,
} from "src/types/applyForm/types";
import { Attachment } from "src/types/attachmentTypes";
import {
  buildWarningTree,
  getFieldsForNav,
  shapeFormData,
} from "src/utils/applyForm/applyFormUtils";
import {
  ConditionalRequiredRule,
  evaluateConditionalRequiredRules,
} from "src/utils/applyForm/conditionalRequiredRules";
import {
  filterVisibleUiSchema,
  hasConditionalUi,
} from "src/utils/applyForm/evaluateConditionalUi";
import { rebaseFieldListWarningsAfterDelete } from "src/utils/applyForm/rebaseFieldListWarningsAfterDelete";
import {
  formatTimestamp,
  getModifiedTimeDisplay,
} from "src/utils/generalUtils";

import { useTranslations } from "next-intl";
import { useNavigationGuard } from "next-navigation-guard";
import {
  ReactNode,
  useActionState,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Alert, FormGroup } from "@trussworks/react-uswds";

import { FormFields } from "src/components/apply-form/FormFields";
import LeftHandFormNav from "src/components/core/forms/LeftHandFormNav";
import ApplyFormActionButtons from "./ApplyFormActionButtons";
import { ApplyFormMessage } from "./ApplyFormMessage";

type Translator = ((
  key: string,
  values?: Record<string, unknown>,
) => string) & {
  rich: (
    key: string,
    values: Record<string, (chunks: ReactNode) => ReactNode>,
  ) => ReactNode;
};

interface WidgetSupport {
  validationWarnings:
    FormattedFormValidationWarning[] | FormValidationWarning[];
  deletedEntryIndexesByFieldListPath: Record<string, number[]>;
  onFieldListEntryDelete: (
    fieldListPath: string,
    deletedEntryIndex: number,
  ) => void;
  markFormDirty?: () => void;
  syncFormData?: () => void;
  attachmentsUploadingCounter?: AttachmentsUploadingCounter;
}

interface ApplyFormFormContext {
  rootSchema: RJSFSchema;
  rootFormData: unknown;
  activeConditionalRequiredPaths?: string[];
  widgetSupport: WidgetSupport;
}

const ApplyForm = ({
  applicationId,
  formId,
  formSchema,
  conditionalRequiredRules = [],
  savedFormData,
  validationWarnings,
  uiSchema,
  attachments,
  isBudgetForm = false,
  applicationStatus,
  createdAt,
  updatedAt,
}: {
  applicationId: string;
  formId: string;
  formSchema: RJSFSchema;
  conditionalRequiredRules?: ConditionalRequiredRule[];
  savedFormData: object;
  uiSchema: UiSchema;
  validationWarnings:
    FormattedFormValidationWarning[] | FormValidationWarning[] | null;
  attachments: Attachment[];
  isBudgetForm?: boolean;
  applicationStatus?: string;
  createdAt?: string;
  updatedAt?: string;
}) => {
  const t = useTranslations("Application.applyForm");
  const translate = t as unknown as Translator;
  const isFormLocked = applicationStatus !== "in_progress";

  const lastUpdatedAt = updatedAt || createdAt;

  const isCreated =
    !updatedAt ||
    getModifiedTimeDisplay(updatedAt, createdAt || updatedAt, "created") ===
      "created";
  const formStatus = isCreated ? "created" : "updated";
  const isFormSaved = Boolean(lastUpdatedAt);

  const required = translate.rich("required", {
    abr: (content) => (
      <abbr
        title="required"
        className="usa-hint usa-hint--required text-no-underline"
      >
        {content}
      </abbr>
    ),
  });

  const [formState, formAction] = useActionState(handleFormAction, {
    applicationId,
    error: false,
    formId,
    formData: new FormData(),
    saved: false,
  });

  const [formChanged, setFormChanged] = useState<boolean>(false);
  const [attachmentsChanged, setAttachmentsChanged] = useState<boolean>(false);
  const [
    deletedEntryIndexesByFieldListPath,
    setDeletedEntryIndexesByFieldListPath,
  ] = useState<Record<string, number[]>>({});
  const [attachmentsUploading, setAttachmentsUploading] = useState<number>(0);
  const formRef = useRef<HTMLFormElement>(null);
  const recalculationFrameRef = useRef<number | null>(null);
  const [liveFormData, setLiveFormData] = useState<object>(savedFormData || {});
  const [lastSavedFormData, setLastSavedFormData] =
    useState<object>(savedFormData);
  const hasConditionalBehavior = useMemo(
    () => hasConditionalUi(uiSchema),
    [uiSchema],
  );
  const hasConditionalRequiredness = conditionalRequiredRules.length > 0;

  if (lastSavedFormData !== savedFormData) {
    setLastSavedFormData(savedFormData);
    setLiveFormData(savedFormData || {});
  }

  const recalculateFromForm = useCallback(
    (formElement: HTMLFormElement): void => {
      setLiveFormData(
        shapeFormData<object>(new FormData(formElement), formSchema),
      );
    },
    [formSchema],
  );

  const scheduleRecalculation = useCallback(
    (formElement: HTMLFormElement): void => {
      if (
        (!hasConditionalBehavior && !hasConditionalRequiredness) ||
        recalculationFrameRef.current !== null
      ) {
        return;
      }
      recalculationFrameRef.current = requestAnimationFrame(() => {
        recalculationFrameRef.current = null;
        recalculateFromForm(formElement);
      });
    },
    [hasConditionalBehavior, hasConditionalRequiredness, recalculateFromForm],
  );

  useEffect(
    () => () => {
      if (recalculationFrameRef.current !== null) {
        cancelAnimationFrame(recalculationFrameRef.current);
      }
    },
    [],
  );

  useNavigationGuard({
    enabled: formChanged || attachmentsChanged,
    confirm: () => window.confirm(translate("unsavedChangesWarning")),
  });

  const { error, saved } = formState;

  /**
   * Marks the form as changed.
   *
   * Used by FieldList and other widgets to signal that local form state
   * has been modified, enabling unsaved-change indicators and navigation guards.
   */
  const handleFormEdited = (): void => {
    setFormChanged(true);
  };

  const syncFormData = useCallback((): void => {
    if (formRef.current) {
      recalculateFromForm(formRef.current);
    }
  }, [recalculateFromForm]);

  const handleFieldListEntryDelete = (
    fieldListPath: string,
    deletedEntryIndex: number,
  ): void => {
    setDeletedEntryIndexesByFieldListPath((previousValue) => ({
      ...previousValue,
      [fieldListPath]: [
        ...(previousValue[fieldListPath] ?? []),
        deletedEntryIndex,
      ],
    }));
  };

  const formObject = liveFormData;

  const conditionalRequiredEvaluation = useMemo(
    () =>
      evaluateConditionalRequiredRules(conditionalRequiredRules, liveFormData),
    [conditionalRequiredRules, liveFormData],
  );

  const navFields = useMemo(
    () => getFieldsForNav(filterVisibleUiSchema(uiSchema, liveFormData)),
    [liveFormData, uiSchema],
  );

  const displayValidationWarnings = useMemo(() => {
    if (!validationWarnings && !formChanged) return null;

    const rebased = Object.entries(deletedEntryIndexesByFieldListPath).reduce<
      FormattedFormValidationWarning[] | FormValidationWarning[] | null
    >((currentWarnings, [fieldListPath, deletedEntryIndexes]) => {
      return deletedEntryIndexes.reduce<
        FormattedFormValidationWarning[] | FormValidationWarning[] | null
      >((rebasedWarnings, deletedEntryIndex) => {
        return rebaseFieldListWarningsAfterDelete({
          rawErrors: rebasedWarnings,
          fieldListPath,
          deletedEntryIndex,
        });
      }, currentWarnings);
    }, validationWarnings ?? []);
    if (!formChanged) return rebased;

    const retained = (rebased ?? []).filter(
      (warning) =>
        warning.type !== "required" ||
        !conditionalRequiredEvaluation.managedPaths.includes(warning.field),
    );
    return [
      ...retained,
      ...buildWarningTree(
        uiSchema,
        null,
        conditionalRequiredEvaluation.warnings,
        formSchema,
      ),
    ];
  }, [
    conditionalRequiredEvaluation,
    deletedEntryIndexesByFieldListPath,
    formChanged,
    formSchema,
    uiSchema,
    validationWarnings,
  ]);

  const attachmentsUploadingCounter: AttachmentsUploadingCounter = useMemo(
    () => ({
      incrementAttachmentsProcessing: () =>
        setAttachmentsUploading((prevState) => prevState + 1),
      decrementAttachmentsProcessing: () =>
        setAttachmentsUploading((prevState) =>
          prevState === 0 ? prevState : prevState - 1,
        ),
    }),
    [],
  );

  const formContextValue = useMemo<ApplyFormFormContext>(
    () => ({
      rootSchema: formSchema,
      rootFormData: formObject,
      activeConditionalRequiredPaths:
        conditionalRequiredEvaluation.activeRequiredPaths,
      widgetSupport: {
        validationWarnings: displayValidationWarnings ?? [],
        deletedEntryIndexesByFieldListPath,
        onFieldListEntryDelete: handleFieldListEntryDelete,
        markFormDirty: handleFormEdited,
        syncFormData,
        attachmentsUploadingCounter,
      },
    }),
    [
      deletedEntryIndexesByFieldListPath,
      displayValidationWarnings,
      formObject,
      formSchema,
      attachmentsUploadingCounter,
      conditionalRequiredEvaluation.activeRequiredPaths,
      syncFormData,
    ],
  );

  useEffect(() => {
    // TODO #9633
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDeletedEntryIndexesByFieldListPath({});
  }, [savedFormData, validationWarnings]);

  if (!formSchema || !formSchema.properties || isEmpty(formSchema.properties)) {
    return (
      <Alert data-testid="alert" type="error" heading="Error" headingLevel="h4">
        Error rendering form
      </Alert>
    );
  }

  return (
    <form
      ref={formRef}
      className="flex-1 margin-top-2 simpler-apply-form"
      action={formAction}
      onChange={(event) => {
        setFormChanged(true);
        scheduleRecalculation(event.currentTarget);
      }}
      noValidate
    >
      <div className="display-flex flex-align-center flex-justify margin-bottom-2">
        <div>
          {required}
          {isFormSaved && lastUpdatedAt && (
            <div className="margin-top-1">
              {formStatus === "updated"
                ? `${translate("lastUpdatedMessage")} ${formatTimestamp(lastUpdatedAt)}`
                : `${translate("createdMessage")} ${formatTimestamp(lastUpdatedAt)}`}
            </div>
          )}
        </div>
        {!isFormLocked && (
          <ApplyFormActionButtons
            applicationId={applicationId}
            onSaveClick={() => {
              setFormChanged(false);
              setAttachmentsChanged(false);
            }}
            returnToApplicationText={translate("returnToApplication")}
            savingText={translate("saving")}
            savingAndRefreshingText={translate("savingAndRefreshing")}
            disableSaveButton={attachmentsUploading !== 0}
            saveDisabledTooltipText={translate("saveDisabledTooltipMessage")}
          />
        )}
      </div>
      <div className="usa-in-page-nav-container">
        <FormGroup className="order-2 width-full">
          <ApplyFormMessage
            saved={saved}
            error={error}
            validationWarnings={displayValidationWarnings}
            isBudgetForm={isBudgetForm}
          />
          <AttachmentsProvider
            value={{ attachments: attachments ?? [], setAttachmentsChanged }}
          >
            <FormFields
              key={saved ? "after-save" : "before-save"}
              errors={saved || formChanged ? displayValidationWarnings : null}
              formData={formObject}
              schema={formSchema}
              uiSchema={uiSchema}
              formContext={formContextValue}
              isFormLocked={isFormLocked}
            />
          </AttachmentsProvider>
        </FormGroup>
        <LeftHandFormNav title={translate("navTitle")} fields={navFields} />
      </div>
    </form>
  );
};

export default ApplyForm;
