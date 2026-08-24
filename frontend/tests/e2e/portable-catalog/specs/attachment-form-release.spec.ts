/**
 * Bounded browser handoff evidence for the banked portable Attachment Form.
 *
 * This uses the ordinary lower-environment preview registry, application route,
 * upload widget, save action, reload route, and print route. It does not alter or
 * imply production registration and it is not a human accessibility review.
 */

import fs from "fs";
import path from "path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import {
  assertPortableMatrixEnvironment,
  loadBrowserPlan,
} from "tests/e2e/portable-catalog/matrix-contract";
import { createApplication } from "tests/e2e/utils/application/create-application-utils";
import { authenticateE2eUser } from "tests/e2e/utils/auth/authenticate-e2e-user-utils";
import { saveForm } from "tests/e2e/utils/forms/save-form-utils";
import {
  assertPrintViewIsReadOnly,
  buildPrintUrl,
} from "tests/e2e/utils/submission/print-view-utils";

const matrixEnabled = process.env.RUN_PORTABLE_BROWSER_MATRIX === "true";
const planPath =
  process.env.PORTABLE_BROWSER_PLAN ??
  path.resolve(process.cwd(), "../api/test-results/portable-browser-plan.json");
const sourcePdf = path.resolve(
  process.cwd(),
  "tests/e2e/test-upload-files/sample-upload-kb.pdf",
);

test.use({ trace: "retain-on-failure" });

async function openAttachmentForm(page: Page, applicationUrl: string) {
  await page.goto(applicationUrl, { waitUntil: "domcontentloaded" });
  const row = page
    .locator(".simpler-application-forms-table tbody tr")
    .filter({ hasText: "[Portable preview] Attachment Form" });
  await expect(row).toHaveCount(1);
  await row.getByTestId("application-form-link").click();
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: "[Portable preview] Attachment Form",
    }),
  ).toBeVisible();
}

async function upload(page: Page, slot: number, filePath: string) {
  const section = page.locator(`#form-section-attachment${slot}`);
  await section
    .locator(`input[name="att${slot}-visible"]`)
    .setInputFiles(filePath);
  await expect(section.getByTestId("file-input-existing-files")).toContainText(
    path.basename(filePath),
    { timeout: 30_000 },
  );
}

async function remove(page: Page, slot: number) {
  const section = page.locator(`#form-section-attachment${slot}`);
  await section.getByRole("button", { name: /delete/i }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: /delete/i }).click();
  await expect(section.getByTestId("file-input-existing-files")).toHaveCount(0);
}

test.describe("portable Attachment Form release evidence", () => {
  test.skip(
    !matrixEnabled,
    "portable Attachment Form evidence requires explicit lower-environment opt-in",
  );

  test(
    "uploads in source order, persists, replaces/removes, and prints read-only",
    { tag: "@portable-catalog" },
    async ({ page, context }, testInfo) => {
      test.setTimeout(10 * 60_000);
      assertPortableMatrixEnvironment();
      const plan = loadBrowserPlan(planPath);
      test.skip(
        !plan.forms.some(
          ({ portableFormId }) => portableFormId === "attachment-form",
        ),
        "the current bounded browser selection does not include attachment-form",
      );

      const slot1 = testInfo.outputPath("slot-1.pdf");
      const slot5 = testInfo.outputPath("slot-5.pdf");
      const replacement = testInfo.outputPath("slot-1-replacement.pdf");
      fs.copyFileSync(sourcePdf, slot1);
      fs.copyFileSync(sourcePdf, slot5);
      fs.copyFileSync(sourcePdf, replacement);

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
      await openAttachmentForm(page, applicationUrl);
      const applyUrl = page.url();

      await expect(
        page.getByText(/attach your files in the proper sequence/i),
      ).toBeVisible();
      await expect(page.locator('main input[type="file"]')).toHaveCount(15);
      const accessibility = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(accessibility.violations).toEqual([]);

      await page.evaluate(() =>
        (document.activeElement as HTMLElement | null)?.blur(),
      );
      let reachedAttachment = false;
      for (let index = 0; index < 40; index += 1) {
        await page.keyboard.press("Tab");
        reachedAttachment = await page.evaluate(
          () => document.activeElement?.getAttribute("name") === "att1-visible",
        );
        if (reachedAttachment) break;
      }
      expect(reachedAttachment).toBe(true);

      await upload(page, 5, slot5);
      await upload(page, 1, slot1);
      await saveForm(page);
      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page.locator("#form-section-attachment1")).toContainText(
        "slot-1.pdf",
      );
      await expect(page.locator("#form-section-attachment5")).toContainText(
        "slot-5.pdf",
      );

      await remove(page, 1);
      await upload(page, 1, replacement);
      await remove(page, 5);
      await saveForm(page);
      await page.reload({ waitUntil: "domcontentloaded" });
      await expect(page.locator("#form-section-attachment1")).toContainText(
        "slot-1-replacement.pdf",
      );
      await expect(page.locator("#form-section-attachment5")).not.toContainText(
        "slot-5.pdf",
      );

      await page.goto(buildPrintUrl(applyUrl), {
        waitUntil: "domcontentloaded",
      });
      await assertPrintViewIsReadOnly(page);
      await expect(page.locator("#form-section-attachment1")).toContainText(
        "slot-1-replacement.pdf",
      );
      await expect(page.locator("#form-section-attachment5")).not.toContainText(
        "slot-5.pdf",
      );
      const orderedSections = await page
        .locator('main [id^="form-section-attachment"]')
        .evaluateAll((sections) => sections.map(({ id }) => id));
      expect(orderedSections).toEqual(
        Array.from(
          { length: 15 },
          (_, index) => `form-section-attachment${index + 1}`,
        ),
      );
    },
  );
});
