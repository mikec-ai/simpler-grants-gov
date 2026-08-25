import fs from "fs";
import path from "path";
import AxeBuilder from "@axe-core/playwright";
import {
  expect,
  test,
  type Locator,
  type Page,
  type Response,
} from "@playwright/test";
import playwrightEnv from "tests/e2e/playwright-env";
import {
  addressableAttachmentDefinitions,
  assertPortableMatrixEnvironment,
  boundaryError,
  classifyBoundary,
  completeBlockedProbes,
  firstAddressableAttachmentDefinition,
  isolateProbeLedger,
  loadBrowserPlan,
  observedBoundary,
  RECEIPT_CONTRACT,
  recoverBrowserPlanCandidates,
  requiresPageIsolationAfterProbe,
  responsePathToControlId,
  responsePathToRepeaterContainerIds,
  schemaDefinitionToControlId,
  schemaDefinitionToResponsePath,
  summarizeReceipts,
  writeReceipt,
  type Boundary,
  type BrowserPlan,
  type BrowserPlanForm,
  type FormReceipt,
  type ProbeReceipt,
  type RecoveredPlanCandidate,
  type SchemaImplicationDeclaration,
} from "tests/e2e/portable-catalog/matrix-contract";
import {
  activateBinaryControl,
  clickPortableSaveButton,
  saveForPersistenceProbe,
} from "tests/e2e/portable-catalog/portable-interactions";
import { createApplication } from "tests/e2e/utils/application/create-application-utils";
import { authenticateE2eUser } from "tests/e2e/utils/auth/authenticate-e2e-user-utils";
import { FORM_DEFAULTS } from "tests/e2e/utils/forms/form-defaults";
import {
  clickSaveButton,
  saveForm,
} from "tests/e2e/utils/forms/save-form-utils";
import { buildPrintUrl } from "tests/e2e/utils/submission/print-view-utils";

const planPath =
  process.env.PORTABLE_BROWSER_PLAN ??
  path.resolve(process.cwd(), "../api/test-results/portable-browser-plan.json");
const receiptsDirectory = path.resolve(
  process.cwd(),
  "test-results/portable-catalog",
);
const matrixEnabled = process.env.RUN_PORTABLE_BROWSER_MATRIX === "true";
const attachmentFixture = path.resolve(
  process.cwd(),
  "tests/e2e/test-upload-files/sample-upload-kb.pdf",
);
const plannedFormProbes = [
  "preview_registration",
  "adapter_api_preflight",
  "apply_render",
  "static_content",
  "attachment_upload_reload",
  "initial_save_reload",
  "schema_implication",
  "accessibility",
  "print_render",
] as const;

type StaticContentDeclaration = {
  sectionName: string;
  label: string;
  paragraphs: string[];
  sha256: string;
};

test.use({ trace: "off" });

function failureProbe(
  name: string,
  error: unknown,
  fallbackBoundary: Boundary,
): ProbeReceipt {
  const boundary = observedBoundary(error, fallbackBoundary);
  const ownership = classifyBoundary(boundary);
  return {
    probe: name,
    status: ownership === "harness_inconclusive" ? "inconclusive" : "failed",
    boundary,
    ownership,
    durationMs: 0,
    evidence: {
      message: error instanceof Error ? error.message : String(error),
    },
  };
}

async function probe(
  name: string,
  boundary: Boundary,
  operation: () => Promise<Record<string, unknown> | void>,
): Promise<ProbeReceipt> {
  const started = Date.now();
  try {
    return {
      probe: name,
      status: "passed",
      durationMs: Date.now() - started,
      evidence: (await operation()) ?? undefined,
    };
  } catch (error) {
    return {
      ...failureProbe(name, error, boundary),
      durationMs: Date.now() - started,
    };
  }
}

function receiptFor(
  form: RecoveredPlanCandidate,
  browser: string,
  manifestSha256 = "unavailable",
): FormReceipt {
  return {
    contract: RECEIPT_CONTRACT,
    consumerCommit: process.env.GITHUB_SHA ?? "local",
    manifestSha256,
    browser,
    portableFormId: form.portableFormId,
    previewFormId: form.previewFormId,
    artifactDigests: form.artifactDigests,
    probes: [],
  };
}

async function openSelectedForm(
  page: Page,
  applicationUrl: string,
  displayName: string,
) {
  await page.goto(applicationUrl, { waitUntil: "domcontentloaded" });
  const rows = page.locator(".simpler-application-forms-table tbody tr");
  await expect(rows.first()).toBeVisible({ timeout: 30_000 });
  const row = rows.filter({
    has: page.getByText(displayName, { exact: true }),
  });
  await expect(row).toHaveCount(1);
  await row.getByTestId("application-form-link").click();
  await page.waitForURL(
    /\/workspace\/applications\/[a-f0-9-]+\/form\/[a-f0-9-]+/,
  );
  await expect(
    page.getByRole("heading", { level: 1, name: displayName }),
  ).toBeVisible();
}

async function captureFormState(page: Page) {
  return page
    .locator(
      "main input:not([type=file]):not([type=hidden]):not([type=submit]):not([type=button]):not([disabled]):not([readonly]), " +
        "main select:not([disabled]), main textarea:not([disabled]):not([readonly])",
    )
    .evaluateAll((nodes) =>
      nodes.map((node) => {
        const field = node as
          HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
        return {
          key: field.name || field.id,
          value: field.value,
          checked: field instanceof HTMLInputElement ? field.checked : null,
        };
      }),
    );
}

const editableControlSelector =
  "main input:visible:not([type=file]):not([type=hidden]):not([disabled]):not([readonly]), " +
  "main textarea:visible:not([disabled]):not([readonly]), " +
  "main select:visible:not([disabled])";

async function makeDeterministicEdit(
  page: Page,
  definition?: string,
): Promise<string> {
  const declaredControl = definition
    ? page.locator(
        `main [id=${JSON.stringify(schemaDefinitionToControlId(definition))}]`,
      )
    : null;
  const control =
    declaredControl && (await declaredControl.count()) > 0
      ? declaredControl
      : page.locator(editableControlSelector).first();
  await expect(control).toBeVisible({ timeout: 10_000 });
  const identity =
    (await control.getAttribute("id")) ??
    (await control.getAttribute("name")) ??
    "first-editable-control";
  const kind = await control.evaluate((node) => ({
    tag: node.tagName.toLowerCase(),
    type: node instanceof HTMLInputElement ? node.type : "",
  }));
  if (kind.tag === "select") {
    const value = await control
      .locator("option:not([value=''])")
      .first()
      .getAttribute("value");
    if (!value) throw new Error("editable select has no non-empty option");
    await control.selectOption(value, { timeout: 10_000 });
  } else if (kind.type === "checkbox" || kind.type === "radio") {
    await activateBinaryControl(control);
  } else if (kind.type === "date") {
    await control.fill("2026-01-01", { timeout: 10_000 });
  } else if (kind.type === "email") {
    await control.fill("browser-canary@example.com", { timeout: 10_000 });
  } else if (kind.type === "number") {
    await control.fill("1", { timeout: 10_000 });
  } else {
    await control.fill("Browser canary", { timeout: 10_000 });
  }
  return identity;
}

async function reachDeclaredEditableControl(
  page: Page,
  form: BrowserPlanForm,
): Promise<string> {
  expect(form.capabilities.editableScalar?.applicability).toBe("applicable");
  const visibleTargetIds = await page
    .locator(editableControlSelector)
    .evaluateAll((nodes) =>
      nodes
        .map((node) => node.id || node.getAttribute("name"))
        .filter((identity): identity is string => Boolean(identity)),
    );
  expect(visibleTargetIds.length).toBeGreaterThan(0);

  await page.evaluate(() =>
    (document.activeElement as HTMLElement | null)?.blur(),
  );
  const interactiveCount = await page
    .locator(
      "a[href]:visible, button:visible:not([disabled]), input:visible:not([disabled]), select:visible:not([disabled]), textarea:visible:not([disabled]), [tabindex]:visible:not([tabindex='-1'])",
    )
    .count();
  for (let index = 0; index < interactiveCount + 5; index += 1) {
    await page.keyboard.press("Tab");
    const focusedTarget = await page.evaluate((ids) => {
      const active = document.activeElement as HTMLElement | null;
      if (!active?.closest("main")) return null;
      const identity = active.id || active.getAttribute("name");
      return identity && ids.includes(identity) ? identity : null;
    }, visibleTargetIds);
    if (focusedTarget) return focusedTarget;
  }
  throw new Error(
    "keyboard traversal did not reach a declared editable form control",
  );
}

async function exerciseStaticContent(
  page: Page,
  form: BrowserPlanForm,
): Promise<Record<string, unknown>> {
  const capability = form.capabilities.staticContent;
  if (capability?.applicability !== "applicable") {
    throw new Error("no section-level static content is declared");
  }
  const declarations = capability.declarations as StaticContentDeclaration[];
  for (const declaration of declarations) {
    const section = page.locator(
      `main [id=${JSON.stringify(`form-section-${declaration.sectionName}`)}]`,
    );
    await expect(section).toBeVisible();
    await expect(
      section.getByRole("heading", { name: declaration.label, exact: true }),
    ).toBeVisible();
    for (const paragraph of declaration.paragraphs) {
      await expect(section.getByText(paragraph, { exact: true })).toBeVisible();
    }
  }
  return {
    sections: declarations.map(({ sectionName, sha256 }) => ({
      sectionName,
      sha256,
    })),
  };
}

async function exerciseAttachmentUpload(
  page: Page,
  form: BrowserPlanForm,
): Promise<Record<string, unknown>> {
  const definitions = addressableAttachmentDefinitions(form);
  if (definitions.length === 0) {
    throw new Error(
      "no mechanically addressable attachment widget is declared",
    );
  }
  let selected:
    | { definition: string; controlId: string; visibleInput: Locator }
    | undefined;
  for (const definition of definitions) {
    const controlId = schemaDefinitionToControlId(definition);
    const visibleInput = page.locator(
      `main input[type=file][id=${JSON.stringify(`${controlId}-visible`)}]`,
    );
    if (
      (await visibleInput.count()) > 0 &&
      (await visibleInput.isVisible()) &&
      (await visibleInput.isEnabled())
    ) {
      selected = { definition, controlId, visibleInput };
      break;
    }
  }
  if (!selected) {
    throw new Error(
      "no declared attachment widget is currently visible and enabled",
    );
  }
  const { definition, controlId, visibleInput } = selected;

  const fileName = path.basename(attachmentFixture);
  const existingFile = page
    .getByTestId("file-input-existing-files")
    .filter({ hasText: fileName });
  const uploadResponsePromise = page.waitForResponse(
    (response) =>
      /\/api\/applications\/[^/]+\/attachments\/create$/.test(response.url()),
    { timeout: 30_000 },
  );
  await visibleInput.setInputFiles(attachmentFixture);
  const uploadResponse = await uploadResponsePromise;
  if (!uploadResponse.ok()) {
    const body = await uploadResponse
      .text()
      .catch(() => "response unavailable");
    const scanUnavailable =
      uploadResponse.status() === 422 && /pending|scan/i.test(body);
    throw boundaryError(
      scanUnavailable ? "environment" : "api_round_trip",
      `attachment upload failed with ${uploadResponse.status()}: ${uploadResponse.url()}; ${body}`,
    );
  }
  await expect(existingFile).toHaveCount(1, { timeout: 30_000 });
  const hiddenInput = page.locator(
    `main input[type=hidden][id=${JSON.stringify(controlId)}]`,
  );
  await expect(hiddenInput).not.toHaveValue("", { timeout: 30_000 });

  await saveForPersistenceProbe(page);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(
    page.getByRole("heading", { level: 1, name: form.displayName }),
  ).toBeVisible();
  const persistedFile = page
    .getByTestId("file-input-existing-files")
    .filter({ hasText: fileName });
  await expect(persistedFile).toHaveCount(1, { timeout: 30_000 });
  await expect(
    persistedFile.getByRole("button", { name: /delete/i }),
  ).toBeVisible();
  await expect(hiddenInput).not.toHaveValue("", { timeout: 30_000 });

  return {
    definition,
    controlId,
    fileName,
    persistedAfterReload: true,
  };
}

function implicationWitnesses(pattern: string): {
  triggering: string;
  nonTriggering: string;
} {
  const expression = new RegExp(pattern);
  const candidates = ["0", "0.00", "0.01", "1", "1.00", "test"];
  const triggering = candidates.find((candidate) => expression.test(candidate));
  const nonTriggering = candidates.find(
    (candidate) => !expression.test(candidate),
  );
  if (triggering === undefined || nonTriggering === undefined) {
    throw new Error(`pattern has no bounded browser witnesses: ${pattern}`);
  }
  return { triggering, nonTriggering };
}

function firstBrowserSchemaImplication(
  form: BrowserPlanForm,
): SchemaImplicationDeclaration | undefined {
  const capability = form.capabilities.schemaImplication;
  if (capability?.applicability !== "applicable") return undefined;
  return (capability.declarations as SchemaImplicationDeclaration[]).find(
    ({ trigger, consequence }) =>
      typeof trigger.constraint?.pattern === "string" &&
      consequence.required &&
      consequence.constraint === null,
  );
}

async function materializeRepresentativeRepeaters(
  page: Page,
  responsePath: string,
): Promise<string[]> {
  const containerIds = responsePathToRepeaterContainerIds(responsePath);
  for (const containerId of containerIds) {
    const container = page.locator(`main [id=${JSON.stringify(containerId)}]`);
    await expect(container).toBeVisible();
    const directEntries = container.locator(
      ":scope > .field-list-widget__entry",
    );
    if ((await directEntries.count()) === 0) {
      const addButton = container.locator(
        ":scope > .field-list-widget__controls button",
      );
      await expect(addButton).toBeEnabled();
      await addButton.click();
      await expect(directEntries).toHaveCount(1);
    }
  }
  return containerIds;
}

async function exerciseSchemaImplication(
  page: Page,
  form: BrowserPlanForm,
): Promise<Record<string, unknown>> {
  const declaration = firstBrowserSchemaImplication(form);
  if (!declaration) {
    throw new Error(
      "no mechanically addressable patterned schema implication is declared",
    );
  }
  const pattern = declaration.trigger.constraint?.pattern;
  if (typeof pattern !== "string") {
    throw new Error("schema implication trigger does not declare a pattern");
  }
  const repeaterContainers = await materializeRepresentativeRepeaters(
    page,
    declaration.trigger.responsePath,
  );
  const triggerId = responsePathToControlId(declaration.trigger.responsePath);
  const consequenceId = responsePathToControlId(
    declaration.consequence.responsePath,
  );
  const triggerControl = page.locator(`main [id=${JSON.stringify(triggerId)}]`);
  await expect(triggerControl).toBeVisible();
  const { triggering, nonTriggering } = implicationWitnesses(pattern);

  await triggerControl.fill(triggering);
  await saveForm(page, true);
  const consequenceLink = page
    .getByTestId("alert")
    .locator(`a[href=${JSON.stringify(`#${consequenceId}`)}]`);
  await expect(consequenceLink).toHaveCount(1);
  await consequenceLink.click();
  const visibleConsequence = page.locator(
    `[id=${JSON.stringify(`${consequenceId}-visible`)}]`,
  );
  const consequenceControl =
    (await visibleConsequence.count()) > 0
      ? visibleConsequence
      : page.locator(`[id=${JSON.stringify(consequenceId)}]`);
  await expect(consequenceControl).toBeFocused();

  await triggerControl.fill(nonTriggering);
  await clickSaveButton(page);
  await expect(consequenceLink).toHaveCount(0, { timeout: 30_000 });
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(
    page.locator(`main [id=${JSON.stringify(triggerId)}]`),
  ).toHaveValue(nonTriggering);

  return {
    triggerResponsePath: declaration.trigger.responsePath,
    consequenceResponsePath: declaration.consequence.responsePath,
    pattern,
    triggering,
    nonTriggering,
    errorFocus:
      consequenceControl === visibleConsequence ? "visible_upload" : "control",
    persistedNonTriggeringValue: true,
    repeaterContainers,
  };
}

type ApplicationFormApiRecord = {
  application_form_id: string;
  form_id: string;
  form?: { form_json_schema?: unknown; form_ui_schema?: unknown };
};

async function fetchApiJson<T>(url: string, token: string): Promise<T> {
  const response = await fetch(url, { headers: { "X-SGG-Token": token } });
  if (!response.ok)
    throw new Error(`API preflight failed with ${response.status}: ${url}`);
  return (await response.json()) as T;
}

test.describe("portable catalog browser conformance", () => {
  // Each attempt emits per-probe receipts with exact failure ownership. Repeating
  // the full catalog does not add evidence and can multiply bounded gate runs by
  // four when an environment capability is unavailable.
  test.describe.configure({ retries: 0 });
  test.skip(
    !matrixEnabled,
    "portable catalog matrix requires explicit lower-environment opt-in",
  );
  test(
    "runs Stage A for every manifest-selected preview form",
    { tag: "@portable-catalog" },
    async ({ page, context }, testInfo) => {
      test.setTimeout(30 * 60_000);
      let plan: BrowserPlan | undefined;
      const receipts: FormReceipt[] = [];
      let receiptByForm = new Map<string, FormReceipt>();
      const browserSlug = testInfo.project.name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-");
      const tracePath = path.join(
        receiptsDirectory,
        `catalog-${browserSlug}-trace.zip`,
      );
      fs.mkdirSync(receiptsDirectory, { recursive: true });
      let tracingStarted = false;
      let setupBoundary: Boundary = "environment";
      let fatalError: Error | undefined;
      let catalogFailure: ProbeReceipt | undefined;
      let summary: ReturnType<typeof summarizeReceipts> | undefined;

      try {
        await context.tracing.start({
          screenshots: true,
          snapshots: true,
          sources: true,
        });
        tracingStarted = true;
        assertPortableMatrixEnvironment();

        setupBoundary = "plan";
        const loadedPlan = loadBrowserPlan(planPath);
        plan = loadedPlan;
        receipts.push(
          ...loadedPlan.forms.map((form) =>
            receiptFor(form, testInfo.project.name, loadedPlan.manifestSha256),
          ),
        );
        receiptByForm = new Map(
          receipts.map((receipt) => [receipt.portableFormId, receipt]),
        );

        setupBoundary = "authentication";
        const token = await authenticateE2eUser(
          page,
          context,
          testInfo.project.name.match(/[Mm]obile/) !== null,
        );
        setupBoundary = "seed";
        await createApplication(
          page,
          `/opportunity/${plan.consumerSeed.opportunityId}`,
          undefined,
        );
        const applicationUrl = page.url();
        const applicationId = applicationUrl.match(
          /\/applications\/([a-f0-9-]+)/,
        )?.[1];
        if (!applicationId)
          throw new Error(
            `seed did not produce an application URL: ${applicationUrl}`,
          );

        setupBoundary = "preview_registration";
        const application = await fetchApiJson<{
          data: { application_forms: ApplicationFormApiRecord[] };
        }>(
          `${playwrightEnv.apiUrl}/alpha/applications/${applicationId}`,
          token,
        );
        const applicationForms = application.data.application_forms;
        const selectedFormIds = new Set(
          plan.forms.map(({ previewFormId }) => previewFormId),
        );
        expect(new Set(applicationForms.map(({ form_id }) => form_id))).toEqual(
          selectedFormIds,
        );
        const applicationFormByFormId = new Map(
          applicationForms.map((record) => [record.form_id, record]),
        );
        for (const receipt of receipts) {
          receipt.probes.push({
            probe: "preview_registration",
            status: "passed",
            durationMs: 0,
            evidence: {
              applicationId,
              applicationFormId: applicationFormByFormId.get(
                receipt.previewFormId,
              )?.application_form_id,
            },
          });
        }

        // A competition can place selected forms in either the required or
        // conditionally-required table. Count rows across both tables so the
        // harness validates the application, not one presentation bucket.
        const formRows = page.locator(
          ".simpler-application-forms-table tbody tr",
        );
        await expect(formRows).toHaveCount(plan.forms.length);

        for (const form of plan.forms) {
          const receipt = receiptByForm.get(form.portableFormId);
          if (!receipt)
            throw new Error(`missing receipt for ${form.portableFormId}`);
          const applicationForm = applicationFormByFormId.get(
            form.previewFormId,
          );
          receipt.probes.push(
            await probe("adapter_api_preflight", "api_round_trip", async () => {
              if (!applicationForm)
                throw new Error("preview form missing from application API");
              const detail = await fetchApiJson<{
                data: ApplicationFormApiRecord;
              }>(
                `${playwrightEnv.apiUrl}/alpha/applications/${applicationId}/application_form/${applicationForm.application_form_id}`,
                token,
              );
              expect(detail.data.form_id).toBe(form.previewFormId);
              expect(detail.data.form?.form_json_schema).toBeDefined();
              expect(detail.data.form?.form_ui_schema).toBeDefined();
              return { applicationFormId: applicationForm.application_form_id };
            }),
          );
          if (receipt.probes.at(-1)?.status !== "passed") {
            completeBlockedProbes(receipt, plannedFormProbes);
            continue;
          }

          const pageErrors: string[] = [];
          const failedFormRequests: string[] = [];
          const onPageError = (error: Error) => pageErrors.push(error.message);
          const onResponse = (response: Response) => {
            if (
              !response.ok() &&
              /\/api\/applications\//.test(response.url())
            ) {
              failedFormRequests.push(response.url());
            }
          };
          page.on("pageerror", onPageError);
          page.on("response", onResponse);
          try {
            let uploadedAttachmentFileName: string | undefined;
            receipt.probes.push(
              await probe("apply_render", "apply_render", async () => {
                await openSelectedForm(page, applicationUrl, form.displayName);
                await expect(
                  page.getByText("Error rendering form"),
                ).toHaveCount(0);
                expect(pageErrors).toEqual([]);
                expect(failedFormRequests).toEqual([]);
                if (
                  form.capabilities.editableScalar?.applicability ===
                  "applicable"
                ) {
                  const editableDefinition =
                    form.capabilities.editableScalar.declarations[0]
                      ?.definition;
                  if (typeof editableDefinition === "string") {
                    await materializeRepresentativeRepeaters(
                      page,
                      schemaDefinitionToResponsePath(editableDefinition),
                    );
                  }
                  const editableControls = page.locator(
                    editableControlSelector,
                  );
                  expect(await editableControls.count()).toBeGreaterThan(0);
                }
                return { route: page.url() };
              }),
            );
            if (receipt.probes.at(-1)?.status !== "passed") {
              completeBlockedProbes(receipt, plannedFormProbes);
              continue;
            }

            if (
              form.capabilities.staticContent?.applicability === "applicable"
            ) {
              receipt.probes.push(
                await probe("static_content", "apply_render", async () =>
                  exerciseStaticContent(page, form),
                ),
              );
            } else {
              receipt.probes.push({
                probe: "static_content",
                status: "not_applicable",
                durationMs: 0,
                evidence: {
                  reason: "no section-level static content is declared",
                },
              });
            }

            let applyUrl = page.url();
            const attachmentDefinition =
              firstAddressableAttachmentDefinition(form);
            const attachmentFailedRequestStart = failedFormRequests.length;
            const attachmentPageErrorStart = pageErrors.length;
            let attachmentProbe: ProbeReceipt;
            if (attachmentDefinition && fs.existsSync(attachmentFixture)) {
              attachmentProbe = await probe(
                "attachment_upload_reload",
                "api_round_trip",
                async () => {
                  const evidence = await exerciseAttachmentUpload(page, form);
                  uploadedAttachmentFileName = evidence.fileName as string;
                  return evidence;
                },
              );
            } else if (
              form.capabilities.attachment?.applicability === "applicable"
            ) {
              attachmentProbe = {
                probe: "attachment_upload_reload",
                status: "inconclusive",
                boundary: "missing_vector",
                ownership: "harness_inconclusive",
                durationMs: 0,
                evidence: {
                  reason: attachmentDefinition
                    ? `deterministic attachment fixture is unavailable: ${attachmentFixture}`
                    : "attachment rules exist but no mechanically addressable attachment widget is declared",
                },
              };
            } else {
              attachmentProbe = {
                probe: "attachment_upload_reload",
                status: "not_applicable",
                durationMs: 0,
                evidence: {
                  reason: "no attachment widget or rule is declared",
                },
              };
            }
            receipt.probes.push(attachmentProbe);

            if (requiresPageIsolationAfterProbe(attachmentProbe)) {
              // Attribute only errors observed during this stateful probe.
              // Earlier failures remain in their owning probe's ledger and
              // continue to fail later independent receipts.
              const attachmentFailedRequests = isolateProbeLedger(
                failedFormRequests,
                attachmentFailedRequestStart,
              );
              const attachmentPageErrors = isolateProbeLedger(
                pageErrors,
                attachmentPageErrorStart,
              );
              attachmentProbe.evidence = {
                ...attachmentProbe.evidence,
                failedFormRequests: attachmentFailedRequests,
                pageErrors: attachmentPageErrors,
              };
            }

            receipt.probes.push(
              await probe("initial_save_reload", "api_round_trip", async () => {
                if (requiresPageIsolationAfterProbe(attachmentProbe)) {
                  // A stateful probe can fail after changing unsaved page data.
                  // Re-enter the form so independent save evidence starts from
                  // the persisted application state, while retaining the
                  // original attachment receipt unchanged.
                  await page.goto(applyUrl, { waitUntil: "domcontentloaded" });
                  await expect(
                    page.getByRole("heading", {
                      level: 1,
                      name: form.displayName,
                    }),
                  ).toBeVisible();
                }
                const editableDefinition =
                  form.capabilities.editableScalar?.declarations[0]?.definition;
                if (typeof editableDefinition === "string") {
                  await materializeRepresentativeRepeaters(
                    page,
                    schemaDefinitionToResponsePath(editableDefinition),
                  );
                }
                const editedControl =
                  form.capabilities.editableScalar?.applicability ===
                  "applicable"
                    ? await makeDeterministicEdit(
                        page,
                        typeof editableDefinition === "string"
                          ? editableDefinition
                          : undefined,
                      )
                    : "not_applicable";
                // Saving is a Next server action, so its API PUT is server-side and
                // invisible to Playwright's browser response stream. Assert the shared
                // save confirmation without predicting whether a generic bounded edit
                // is valid; validation-warning count is recorded separately below.
                // Capture after the save so generic calculated fields have reached
                // their canonical values before we compare them with the reload.
                await clickPortableSaveButton(page);
                await expect(
                  page.getByText(FORM_DEFAULTS.formSavedHeading, {
                    exact: false,
                  }),
                ).toBeVisible({ timeout: 30_000 });
                const beforeReload = await captureFormState(page);
                applyUrl = page.url();
                await page.reload({ waitUntil: "domcontentloaded" });
                await expect(
                  page.getByRole("heading", {
                    level: 1,
                    name: form.displayName,
                  }),
                ).toBeVisible();
                await expect(
                  page.getByText("Error rendering form"),
                ).toHaveCount(0);
                const afterReload = await captureFormState(page);
                expect(afterReload).toEqual(beforeReload);
                expect(pageErrors).toEqual([]);
                expect(failedFormRequests).toEqual([]);
                const validationWarningCount = await page
                  .getByTestId("alert")
                  .locator("li")
                  .count();
                return {
                  route: applyUrl,
                  status: "ui_confirmed",
                  validationWarningCount,
                  persistedControls: afterReload.length,
                  editedControl,
                };
              }),
            );

            if (firstBrowserSchemaImplication(form)) {
              receipt.probes.push(
                await probe("schema_implication", "apply_render", async () =>
                  exerciseSchemaImplication(page, form),
                ),
              );
            } else {
              receipt.probes.push({
                probe: "schema_implication",
                status: "not_applicable",
                durationMs: 0,
                evidence: {
                  reason:
                    form.capabilities.schemaImplication?.applicability ===
                    "applicable"
                      ? "no mechanically addressable patterned implication is declared"
                      : "no simple schema implication is declared",
                },
              });
            }

            receipt.probes.push(
              await probe("accessibility", "apply_render", async () => {
                const results = await new AxeBuilder({ page })
                  .include("main")
                  .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
                  .analyze();
                expect(results.violations).toEqual([]);
                if (
                  form.capabilities.editableScalar?.applicability ===
                  "applicable"
                ) {
                  return {
                    violations: 0,
                    focusedControl: await reachDeclaredEditableControl(
                      page,
                      form,
                    ),
                  };
                }
                return { violations: 0, focus: "not_applicable" };
              }),
            );

            receipt.probes.push(
              await probe("print_render", "print_render", async () => {
                const printUrl = buildPrintUrl(applyUrl);
                await page.goto(printUrl, { waitUntil: "domcontentloaded" });
                await expect(
                  page.getByRole("heading", {
                    level: 1,
                    name: form.displayName,
                  }),
                ).toBeVisible();
                const preview = page.locator(".apply-form-print-preview");
                await expect(preview).toBeVisible();
                await expect(
                  page.getByText("Error rendering form"),
                ).toHaveCount(0);
                if (uploadedAttachmentFileName) {
                  await expect(preview).toContainText(
                    uploadedAttachmentFileName,
                  );
                }
                const interactiveControls = preview.locator(
                  "input:visible:not([type=hidden]):not([disabled]):not([readonly]), " +
                    "textarea:visible:not([disabled]):not([readonly]), " +
                    "select:visible:not([disabled]), button:visible:not([disabled]), " +
                    "[contenteditable='true']:visible",
                );
                await expect(interactiveControls).toHaveCount(0);
                expect(pageErrors).toEqual([]);
                expect(failedFormRequests).toEqual([]);
                return {
                  route: printUrl,
                  interactiveControls: 0,
                  attachmentFileName:
                    uploadedAttachmentFileName ?? "not_applicable",
                };
              }),
            );
          } finally {
            page.off("pageerror", onPageError);
            page.off("response", onResponse);
            completeBlockedProbes(receipt, plannedFormProbes);
          }
        }
      } catch (error) {
        fatalError =
          error instanceof Error
            ? error
            : new Error("catalog setup failed with a non-Error value");
        catalogFailure = failureProbe("catalog_setup", error, setupBoundary);
        if (!plan && receipts.length === 0) {
          receipts.push(
            ...recoverBrowserPlanCandidates(planPath).map((candidate) =>
              receiptFor(candidate, testInfo.project.name),
            ),
          );
        }
        for (const receipt of receipts) {
          if (
            !receipt.probes.some(
              ({ status }) => status === "failed" || status === "inconclusive",
            )
          ) {
            receipt.probes.push(catalogFailure);
          }
          completeBlockedProbes(receipt, plannedFormProbes);
        }
      } finally {
        let traceError: unknown;
        if (tracingStarted) {
          try {
            await context.tracing.stop({ path: tracePath });
          } catch (error) {
            traceError = error;
          }
        } else {
          traceError = new Error("browser tracing did not start");
        }
        if (traceError) {
          for (const receipt of receipts) {
            receipt.probes.push(
              failureProbe("trace_capture", traceError, "environment"),
            );
          }
        }

        for (const receipt of receipts) {
          completeBlockedProbes(receipt, plannedFormProbes);
          const receiptPath = writeReceipt(receiptsDirectory, receipt);
          await testInfo.attach(`${receipt.portableFormId}-receipt`, {
            path: receiptPath,
            contentType: "application/json",
          });
          if (receipt.probes.some(({ status }) => status === "failed")) {
            const screenshotPath = path.join(
              receiptsDirectory,
              `${receipt.portableFormId}-${browserSlug}-failure.png`,
            );
            await page
              .screenshot({ path: screenshotPath, fullPage: true })
              .catch(() => undefined);
            if (fs.existsSync(screenshotPath)) {
              await testInfo.attach(`${receipt.portableFormId}-failure`, {
                path: screenshotPath,
                contentType: "image/png",
              });
            }
          }
        }

        summary = summarizeReceipts(receipts, catalogFailure);
        const summaryPath = path.join(
          receiptsDirectory,
          `catalog-summary-${browserSlug}.json`,
        );
        fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
        await testInfo.attach("portable-catalog-summary", {
          path: summaryPath,
          contentType: "application/json",
        });
        if (tracingStarted && !traceError && fs.existsSync(tracePath)) {
          await testInfo.attach("portable-catalog-trace", {
            path: tracePath,
            contentType: "application/zip",
          });
        }
        if (catalogFailure?.boundary === "plan" || traceError) {
          const traceStatusPath = path.join(
            receiptsDirectory,
            `catalog-${browserSlug}-trace-status.json`,
          );
          fs.writeFileSync(
            traceStatusPath,
            `${JSON.stringify(
              {
                status:
                  tracingStarted && !traceError && fs.existsSync(tracePath)
                    ? "captured"
                    : "inconclusive",
                boundary:
                  catalogFailure?.boundary ??
                  observedBoundary(traceError, "environment"),
                ownership:
                  catalogFailure?.ownership ??
                  classifyBoundary(observedBoundary(traceError, "environment")),
                message:
                  catalogFailure?.evidence?.message ??
                  (traceError instanceof Error
                    ? traceError.message
                    : "browser trace unavailable"),
              },
              null,
              2,
            )}\n`,
          );
          await testInfo.attach("portable-catalog-trace-status", {
            path: traceStatusPath,
            contentType: "application/json",
          });
        }
      }

      if (fatalError) throw fatalError;
      expect(summary?.forms).toBe(plan?.forms.length);
      expect(summary?.releaseGate).toBe(true);
    },
  );
});
