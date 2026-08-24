import fs from "fs";
import path from "path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Response } from "@playwright/test";
import {
  classifyBoundary,
  loadBrowserPlan,
  RECEIPT_CONTRACT,
  summarizeReceipts,
  writeReceipt,
  type Boundary,
  type FormReceipt,
  type ProbeReceipt,
} from "tests/e2e/portable-catalog/matrix-contract";
import { createApplication } from "tests/e2e/utils/application/create-application-utils";
import { authenticateE2eUser } from "tests/e2e/utils/auth/authenticate-e2e-user-utils";
import { buildPrintUrl } from "tests/e2e/utils/submission/print-view-utils";

const planPath =
  process.env.PORTABLE_BROWSER_PLAN ??
  path.resolve(process.cwd(), "../api/test-results/portable-browser-plan.json");
const receiptsDirectory = path.resolve(
  process.cwd(),
  "test-results/portable-catalog",
);
const matrixEnabled = process.env.RUN_PORTABLE_BROWSER_MATRIX === "true";

test.use({ trace: "off" });

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
      probe: name,
      status:
        classifyBoundary(boundary) === "harness_inconclusive"
          ? "inconclusive"
          : "failed",
      boundary,
      ownership: classifyBoundary(boundary),
      durationMs: Date.now() - started,
      evidence: {
        message: error instanceof Error ? error.message : String(error),
      },
    };
  }
}

async function openSelectedForm(
  page: Page,
  applicationUrl: string,
  displayName: string,
) {
  await page.goto(applicationUrl, { waitUntil: "domcontentloaded" });
  const table = page.locator(".simpler-application-forms-table").first();
  await expect(table).toBeVisible({ timeout: 30_000 });
  const row = table.locator("tbody tr").filter({ hasText: displayName });
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
      "main input:not([type=file]):not([type=submit]):not([type=button]), main select, main textarea",
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
      const plan = loadBrowserPlan(planPath);
      const receipts: FormReceipt[] = [];
      fs.mkdirSync(receiptsDirectory, { recursive: true });
      await context.tracing.start({
        screenshots: true,
        snapshots: true,
        sources: true,
      });

      await authenticateE2eUser(
        page,
        context,
        testInfo.project.name.match(/[Mm]obile/) !== null,
      );
      await createApplication(
        page,
        `/opportunity/${plan.consumerSeed.opportunityId}`,
        undefined,
      );
      const applicationUrl = page.url();

      const formRows = page
        .locator(".simpler-application-forms-table")
        .first()
        .locator("tbody tr");
      await expect(formRows).toHaveCount(plan.forms.length);

      for (const form of plan.forms) {
        const receipt: FormReceipt = {
          contract: RECEIPT_CONTRACT,
          consumerCommit: process.env.GITHUB_SHA ?? "local",
          manifestSha256: plan.manifestSha256,
          browser: testInfo.project.name,
          portableFormId: form.portableFormId,
          previewFormId: form.previewFormId,
          artifactDigests: form.artifactDigests,
          probes: [],
        };
        const pageErrors: string[] = [];
        const failedFormRequests: string[] = [];
        const onPageError = (error: Error) => pageErrors.push(error.message);
        const onResponse = (response: Response) => {
          if (!response.ok() && /\/api\/applications\//.test(response.url())) {
            failedFormRequests.push(response.url());
          }
        };
        page.on("pageerror", onPageError);
        page.on("response", onResponse);

        receipt.probes.push(
          await probe("apply_render", "apply_render", async () => {
            await openSelectedForm(page, applicationUrl, form.displayName);
            await expect(page.getByText("Error rendering form")).toHaveCount(0);
            expect(pageErrors).toEqual([]);
            expect(failedFormRequests).toEqual([]);
            return { route: page.url() };
          }),
        );

        let applyUrl = page.url();
        if (receipt.probes.at(-1)?.status === "passed") {
          receipt.probes.push(
            await probe("initial_save_reload", "api_round_trip", async () => {
              const beforeSave = await captureFormState(page);
              const save = page.getByTestId("apply-form-save");
              await expect(save).toBeVisible();
              await expect(save).not.toHaveAttribute("aria-disabled", "true");
              const saveResponse = page.waitForResponse(
                (response) =>
                  response.request().method() === "PUT" &&
                  /\/api\/applications\//.test(response.url()),
                { timeout: 60_000 },
              );
              await save.click();
              const response = await saveResponse;
              expect(response.ok()).toBe(true);
              applyUrl = page.url();
              await page.reload({ waitUntil: "domcontentloaded" });
              await expect(
                page.getByRole("heading", { level: 1, name: form.displayName }),
              ).toBeVisible();
              await expect(page.getByText("Error rendering form")).toHaveCount(
                0,
              );
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
                status: response.status(),
                validationWarningCount,
                persistedControls: afterReload.length,
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
                form.capabilities.editableScalar?.applicability === "applicable"
              ) {
                await page.locator("body").press("Tab");
                const focusedTag = await page.evaluate(
                  () => document.activeElement?.tagName ?? null,
                );
                expect(focusedTag).not.toBe("BODY");
                return { violations: 0, focusedTag };
              }
              return { violations: 0, focus: "not_applicable" };
            }),
          );

          receipt.probes.push(
            await probe("print_render", "print_render", async () => {
              const printUrl = buildPrintUrl(applyUrl);
              await page.goto(printUrl, { waitUntil: "domcontentloaded" });
              await expect(
                page.getByRole("heading", { level: 1, name: form.displayName }),
              ).toBeVisible();
              await expect(
                page.locator(".apply-form-print-preview"),
              ).toBeVisible();
              await expect(page.getByText("Error rendering form")).toHaveCount(
                0,
              );
              await expect(
                page.locator(
                  ".apply-form-print-preview input:visible:not([disabled]):not([readonly]), " +
                    ".apply-form-print-preview textarea:visible:not([disabled]):not([readonly])",
                ),
              ).toHaveCount(0);
              expect(pageErrors).toEqual([]);
              expect(failedFormRequests).toEqual([]);
              return { route: printUrl };
            }),
          );
        } else {
          for (const blockedProbe of [
            "initial_save_reload",
            "accessibility",
            "print_render",
          ]) {
            receipt.probes.push({
              probe: blockedProbe,
              status: "inconclusive",
              boundary: "apply_render",
              ownership: "shared_runtime",
              durationMs: 0,
              evidence: { blockedBy: "apply_render" },
            });
          }
        }

        page.off("pageerror", onPageError);
        page.off("response", onResponse);
        receipts.push(receipt);
        const receiptPath = writeReceipt(receiptsDirectory, receipt);
        await testInfo.attach(`${form.portableFormId}-receipt`, {
          path: receiptPath,
          contentType: "application/json",
        });
        if (receipt.probes.some(({ status }) => status === "failed")) {
          const screenshotPath = path.join(
            receiptsDirectory,
            `${form.portableFormId}-${testInfo.project.name}-failure.png`,
          );
          await page.screenshot({
            path: screenshotPath,
            fullPage: true,
          });
          await testInfo.attach(`${form.portableFormId}-failure`, {
            path: screenshotPath,
            contentType: "image/png",
          });
        }
      }

      const summary = summarizeReceipts(receipts);
      const browserSlug = testInfo.project.name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-");
      const summaryPath = path.join(
        receiptsDirectory,
        `catalog-summary-${browserSlug}.json`,
      );
      fs.writeFileSync(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
      await testInfo.attach("portable-catalog-summary", {
        path: summaryPath,
        contentType: "application/json",
      });
      const tracePath = path.join(
        receiptsDirectory,
        `catalog-${browserSlug}-trace.zip`,
      );
      await context.tracing.stop({ path: tracePath });
      await testInfo.attach("portable-catalog-trace", {
        path: tracePath,
        contentType: "application/zip",
      });
      expect(summary.forms).toBe(plan.forms.length);
      expect(summary.releaseGate).toBe(true);
    },
  );
});
