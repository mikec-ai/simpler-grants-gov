import { execFileSync } from "child_process";
import fs from "fs";
import path from "path";
import { expect, test, type Page } from "@playwright/test";
import playwrightEnv from "tests/e2e/playwright-env";
import { loadBrowserPlan } from "tests/e2e/portable-catalog/matrix-contract";
import { createApplication } from "tests/e2e/utils/application/create-application-utils";
import { authenticateE2eUser } from "tests/e2e/utils/auth/authenticate-e2e-user-utils";
import { saveForm } from "tests/e2e/utils/forms/save-form-utils";
import { buildPrintUrl } from "tests/e2e/utils/submission/print-view-utils";

const enabled = process.env.RUN_PORTABLE_COMPARISON_DEMO === "true";
const planPath =
  process.env.PORTABLE_BROWSER_PLAN ??
  path.resolve(process.cwd(), "../api/test-results/portable-browser-plan.json");
const artifactDirectory = path.resolve(
  process.cwd(),
  "test-results/portable-comparison",
);
const existingSf424OpportunityId = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";
const existingDisplayName = "Application for Federal Assistance (SF-424)";
const videoSize = { width: 960, height: 1080 };

test.use({ trace: "off", video: "off" });

async function openSelectedForm(
  page: Page,
  applicationUrl: string,
  displayName: string,
) {
  await page.goto(applicationUrl, { waitUntil: "domcontentloaded" });
  const row = page
    .locator(".simpler-application-forms-table tbody tr")
    .filter({ hasText: displayName });
  await expect(row).toHaveCount(1);
  await row.getByTestId("application-form-link").click();
  await page.waitForURL(
    /\/workspace\/applications\/[a-f0-9-]+\/form\/[a-f0-9-]+/,
  );
  await expect(
    page.getByRole("heading", { level: 1, name: displayName }),
  ).toBeVisible();
}

async function createFormRoute(
  page: Page,
  opportunityId: string,
  displayName: string,
) {
  await createApplication(page, `/opportunity/${opportunityId}`, undefined);
  const applicationUrl = page.url();
  await openSelectedForm(page, applicationUrl, displayName);
  return page.url();
}

async function setRecordingOverlay(page: Page, label: string, caption: string) {
  await page.evaluate(
    ({ columnLabel, currentCaption }) => {
      const rootId = "portable-comparison-recording-overlay";
      let root = document.getElementById(rootId);
      if (!root) {
        root = document.createElement("div");
        root.id = rootId;
        root.style.cssText = [
          "position:fixed",
          "inset:0",
          "pointer-events:none",
          "z-index:2147483647",
          "font-family:system-ui,sans-serif",
        ].join(";");
        root.innerHTML =
          "<div data-column-label></div><div data-caption></div>";
        document.body.appendChild(root);
      }
      const labelNode = root.querySelector<HTMLElement>("[data-column-label]");
      const captionNode = root.querySelector<HTMLElement>("[data-caption]");
      if (!labelNode || !captionNode) return;
      labelNode.textContent = columnLabel;
      labelNode.style.cssText = [
        "position:absolute",
        "top:16px",
        "left:16px",
        "padding:8px 12px",
        "border-radius:4px",
        "background:#16395f",
        "color:white",
        "font-size:18px",
        "font-weight:700",
        "box-shadow:0 2px 8px rgba(0,0,0,.25)",
      ].join(";");
      captionNode.textContent = currentCaption;
      captionNode.style.cssText = [
        "position:absolute",
        "left:16px",
        "right:16px",
        "bottom:16px",
        "padding:12px 16px",
        "border-radius:4px",
        "background:rgba(0,0,0,.82)",
        "color:white",
        "font-size:17px",
        "line-height:1.35",
        "box-shadow:0 2px 8px rgba(0,0,0,.25)",
      ].join(";");
    },
    { columnLabel: label, currentCaption: caption },
  );
}

async function pauseBoth(existing: Page, portable: Page, milliseconds: number) {
  await Promise.all([
    existing.waitForTimeout(milliseconds),
    portable.waitForTimeout(milliseconds),
  ]);
}

async function selectOption(page: Page, value: string) {
  const select = page
    .locator("main select")
    .filter({ has: page.locator(`option[value="${value}"]`) })
    .first();
  await expect(select).toBeVisible();
  await select.selectOption(value);
  await expect(select).toHaveValue(value);
}

function currentCommit() {
  return (
    process.env.GITHUB_SHA ??
    execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: path.resolve(process.cwd(), ".."),
      encoding: "utf8",
    }).trim()
  );
}

function combineVideos(
  existingPath: string,
  portablePath: string,
  output: string,
) {
  try {
    execFileSync(
      "ffmpeg",
      [
        "-y",
        "-i",
        existingPath,
        "-i",
        portablePath,
        "-filter_complex",
        "[0:v]setpts=PTS-STARTPTS[left];[1:v]setpts=PTS-STARTPTS[right];[left][right]hstack=inputs=2[v]",
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-pix_fmt",
        "yuv420p",
        "-shortest",
        output,
      ],
      { stdio: "pipe" },
    );
  } catch (error) {
    const detail =
      error instanceof Error && "stderr" in error
        ? String((error as Error & { stderr?: Buffer }).stderr ?? error.message)
        : String(error);
    throw new Error(
      `Unable to assemble the comparison video. Install ffmpeg and retry. ${detail}`,
    );
  }
}

test.describe("portable form comparison recording", () => {
  test.skip(
    !enabled,
    "comparison recording requires explicit lower-environment opt-in",
  );

  test(
    "records existing and portable SF-424 through the real Simpler frontend",
    { tag: "@portable-comparison-demo" },
    async ({ browser, context, page }, testInfo) => {
      test.setTimeout(10 * 60_000);
      const plan = loadBrowserPlan(planPath);
      expect(plan.forms.map(({ portableFormId }) => portableFormId)).toEqual([
        "sf424",
      ]);
      const portableForm = plan.forms[0];

      await authenticateE2eUser(page, context, false);
      const existingRoute = await createFormRoute(
        page,
        existingSf424OpportunityId,
        existingDisplayName,
      );
      const portableRoute = await createFormRoute(
        page,
        plan.consumerSeed.opportunityId,
        portableForm.displayName,
      );
      const storageState = await context.storageState();

      fs.mkdirSync(artifactDirectory, { recursive: true });
      const rawDirectory = path.join(artifactDirectory, "raw");
      fs.mkdirSync(rawDirectory, { recursive: true });
      const contextOptions = {
        baseURL: playwrightEnv.baseUrl,
        storageState,
        viewport: videoSize,
        recordVideo: { dir: rawDirectory, size: videoSize },
      };
      const [existingContext, portableContext] = await Promise.all([
        browser.newContext(contextOptions),
        browser.newContext(contextOptions),
      ]);
      const [existingPage, portablePage] = await Promise.all([
        existingContext.newPage(),
        portableContext.newPage(),
      ]);
      const existingVideo = existingPage.video();
      const portableVideo = portablePage.video();
      if (!existingVideo || !portableVideo) {
        throw new Error("Playwright did not initialize both comparison videos");
      }

      try {
        await Promise.all([
          existingPage.goto(existingRoute, { waitUntil: "domcontentloaded" }),
          portablePage.goto(portableRoute, { waitUntil: "domcontentloaded" }),
        ]);
        await Promise.all([
          expect(
            existingPage.getByRole("heading", {
              level: 1,
              name: existingDisplayName,
            }),
          ).toBeVisible(),
          expect(
            portablePage.getByRole("heading", {
              level: 1,
              name: portableForm.displayName,
            }),
          ).toBeVisible(),
        ]);

        await Promise.all([
          setRecordingOverlay(
            existingPage,
            "Existing SGG implementation",
            "The same SF-424 is running in two isolated browser contexts.",
          ),
          setRecordingOverlay(
            portablePage,
            "Portable specification",
            "The same SF-424 is running in two isolated browser contexts.",
          ),
        ]);
        await pauseBoth(existingPage, portablePage, 2_500);

        await Promise.all([
          setRecordingOverlay(
            existingPage,
            "Existing SGG implementation",
            'Set "Type of Submission" to Application.',
          ),
          setRecordingOverlay(
            portablePage,
            "Portable specification",
            'Set "Type of Submission" to Application.',
          ),
          selectOption(existingPage, "Application"),
          selectOption(portablePage, "Application"),
        ]);
        await pauseBoth(existingPage, portablePage, 1_800);

        await Promise.all([
          setRecordingOverlay(
            existingPage,
            "Existing SGG implementation",
            'Set "Type of Application" to Revision and expose its conditional questions.',
          ),
          setRecordingOverlay(
            portablePage,
            "Portable specification",
            'Set "Type of Application" to Revision and expose its conditional questions.',
          ),
          selectOption(existingPage, "Revision"),
          selectOption(portablePage, "Revision"),
        ]);
        await pauseBoth(existingPage, portablePage, 2_500);

        await Promise.all([
          setRecordingOverlay(
            existingPage,
            "Existing SGG implementation",
            "Save the same incomplete payload. Validation messages are expected.",
          ),
          setRecordingOverlay(
            portablePage,
            "Portable specification",
            "Save the same incomplete payload. Validation messages are expected.",
          ),
        ]);
        await Promise.all([
          saveForm(existingPage, true),
          saveForm(portablePage, true),
        ]);
        await pauseBoth(existingPage, portablePage, 2_000);

        await Promise.all([
          existingPage.reload({ waitUntil: "domcontentloaded" }),
          portablePage.reload({ waitUntil: "domcontentloaded" }),
        ]);
        await Promise.all([
          expect(existingPage.locator("main select").first()).toHaveValue(
            "Application",
          ),
          expect(portablePage.locator("main select").first()).toHaveValue(
            "Application",
          ),
        ]);
        await Promise.all([
          setRecordingOverlay(
            existingPage,
            "Existing SGG implementation",
            "Reload complete. The edited values persisted in both implementations.",
          ),
          setRecordingOverlay(
            portablePage,
            "Portable specification",
            "Reload complete. The edited values persisted in both implementations.",
          ),
        ]);
        await pauseBoth(existingPage, portablePage, 2_500);

        await Promise.all([
          existingPage.goto(buildPrintUrl(existingPage.url()), {
            waitUntil: "domcontentloaded",
          }),
          portablePage.goto(buildPrintUrl(portablePage.url()), {
            waitUntil: "domcontentloaded",
          }),
        ]);
        await Promise.all([
          expect(
            existingPage.locator(".apply-form-print-preview"),
          ).toBeVisible(),
          expect(
            portablePage.locator(".apply-form-print-preview"),
          ).toBeVisible(),
          setRecordingOverlay(
            existingPage,
            "Existing SGG implementation",
            "Both forms reached the ordinary Simpler print view.",
          ),
          setRecordingOverlay(
            portablePage,
            "Portable specification",
            "Both forms reached the ordinary Simpler print view.",
          ),
        ]);
        await pauseBoth(existingPage, portablePage, 3_000);

        await Promise.all([
          setRecordingOverlay(
            existingPage,
            "Existing SGG implementation",
            "Recorded evidence: render, conditional interaction, save/reload, and print.",
          ),
          setRecordingOverlay(
            portablePage,
            "Portable specification",
            "Recorded evidence: render, conditional interaction, save/reload, and print.",
          ),
        ]);
        await pauseBoth(existingPage, portablePage, 3_000);
      } finally {
        await Promise.all([existingContext.close(), portableContext.close()]);
      }

      const existingVideoPath = path.join(
        artifactDirectory,
        "sf424-existing.webm",
      );
      const portableVideoPath = path.join(
        artifactDirectory,
        "sf424-portable.webm",
      );
      await Promise.all([
        existingVideo.saveAs(existingVideoPath),
        portableVideo.saveAs(portableVideoPath),
      ]);
      const comparisonVideoPath = path.join(
        artifactDirectory,
        "sf424-side-by-side.mp4",
      );
      combineVideos(existingVideoPath, portableVideoPath, comparisonVideoPath);

      const receiptPath = path.join(
        artifactDirectory,
        "sf424-side-by-side-receipt.json",
      );
      fs.writeFileSync(
        receiptPath,
        `${JSON.stringify(
          {
            contract: "sgg-portable-comparison-recording/v1",
            form: "sf424",
            producer: plan.source,
            consumerCommit: currentCommit(),
            manifestSha256: plan.manifestSha256,
            artifactDigests: portableForm.artifactDigests,
            comparison: {
              existingFormId: "1623b310-85be-496a-b84b-34bdee22a68a",
              portablePreviewFormId: portableForm.previewFormId,
              checkpoints: [
                "render",
                "conditional_interaction",
                "save_reload",
                "print",
              ],
            },
            limitation:
              "This recording is compatibility evidence, not semantic acceptance, accessibility approval, policy approval, or production registration.",
          },
          null,
          2,
        )}\n`,
      );

      await testInfo.attach("sf424-side-by-side-video", {
        path: comparisonVideoPath,
        contentType: "video/mp4",
      });
      await testInfo.attach("sf424-side-by-side-receipt", {
        path: receiptPath,
        contentType: "application/json",
      });
    },
  );
});
