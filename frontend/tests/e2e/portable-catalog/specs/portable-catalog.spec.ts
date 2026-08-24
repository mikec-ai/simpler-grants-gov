import fs from "fs";
import path from "path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Response } from "@playwright/test";
import playwrightEnv from "tests/e2e/playwright-env";
import {
  assertPortableMatrixEnvironment,
  classifyBoundary,
  completeBlockedProbes,
  loadBrowserPlan,
  observedBoundary,
  RECEIPT_CONTRACT,
  recoverBrowserPlanCandidates,
  schemaDefinitionToControlId,
  summarizeReceipts,
  writeReceipt,
  type Boundary,
  type BrowserPlan,
  type BrowserPlanForm,
  type FormReceipt,
  type ProbeReceipt,
  type RecoveredPlanCandidate,
} from "tests/e2e/portable-catalog/matrix-contract";
import { createApplication } from "tests/e2e/utils/application/create-application-utils";
import { authenticateE2eUser } from "tests/e2e/utils/auth/authenticate-e2e-user-utils";
import { saveForm } from "tests/e2e/utils/forms/save-form-utils";
import { buildPrintUrl } from "tests/e2e/utils/submission/print-view-utils";

const planPath =
  process.env.PORTABLE_BROWSER_PLAN ??
  path.resolve(process.cwd(), "../api/test-results/portable-browser-plan.json");
const receiptsDirectory = path.resolve(
  process.cwd(),
  "test-results/portable-catalog",
);
const matrixEnabled = process.env.RUN_PORTABLE_BROWSER_MATRIX === "true";
const plannedFormProbes = [
  "preview_registration",
  "adapter_api_preflight",
  "apply_render",
  "initial_save_reload",
  "accessibility",
  "print_render",
] as const;

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
  const row = rows.filter({ hasText: displayName });
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
      "main input:not([type=file]):not([type=hidden]):not([type=submit]):not([type=button]), main select, main textarea",
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
  "main input:visible:not([type=hidden]):not([disabled]):not([readonly]), " +
  "main textarea:visible:not([disabled]):not([readonly]), " +
  "main select:visible:not([disabled])";

async function makeDeterministicEdit(
  page: Page,
  definition?: string,
): Promise<string> {
  const control = definition
    ? page.locator(
        `main [id=${JSON.stringify(schemaDefinitionToControlId(definition))}]`,
      )
    : page.locator(editableControlSelector).first();
  await expect(control).toBeVisible();
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
    await control.selectOption(value);
  } else if (kind.type === "checkbox" || kind.type === "radio") {
    await control.check();
  } else if (kind.type === "date") {
    await control.fill("2026-01-01");
  } else if (kind.type === "email") {
    await control.fill("browser-canary@example.com");
  } else if (kind.type === "number") {
    await control.fill("1");
  } else {
    await control.fill("Browser canary");
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

            let applyUrl = page.url();
            receipt.probes.push(
              await probe("initial_save_reload", "api_round_trip", async () => {
                const editableDefinition =
                  form.capabilities.editableScalar?.declarations[0]?.definition;
                const editedControl = await makeDeterministicEdit(
                  page,
                  typeof editableDefinition === "string"
                    ? editableDefinition
                    : undefined,
                );
                const beforeSave = await captureFormState(page);
                // Saving is a Next server action, so its API PUT is server-side and
                // invisible to Playwright's browser response stream. Assert the user
                // confirmation instead; this incomplete canary payload should report
                // validation issues while still persisting the deterministic edit.
                await saveForm(page, true);
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
                expect(afterReload).toEqual(beforeSave);
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

            receipt.probes.push(
              await probe("accessibility", "apply_render", async () => {
                const results = await new AxeBuilder({ page })
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
                await expect(
                  preview.locator(
                    "input:visible:not([type=hidden]):not([disabled]):not([readonly]), " +
                      "textarea:visible:not([disabled]):not([readonly]), " +
                      "select:visible:not([disabled]), button:visible:not([disabled]), " +
                      "[contenteditable='true']:visible",
                  ),
                ).toHaveCount(0);
                expect(pageErrors).toEqual([]);
                expect(failedFormRequests).toEqual([]);
                return { route: printUrl };
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
