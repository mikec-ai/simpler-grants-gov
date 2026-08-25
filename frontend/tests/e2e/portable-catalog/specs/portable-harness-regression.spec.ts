import { expect, test } from "@playwright/test";
import {
  activateBinaryControl,
  saveForPersistenceProbe,
} from "tests/e2e/portable-catalog/portable-interactions";

test.describe("portable catalog harness regressions", () => {
  test("activates a styled offscreen radio through its accessible label", async ({
    page,
  }) => {
    await page.route("http://portable-harness.test/radio", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: `
          <main>
            <input id="agency-value-0" name="agency" type="radio" value="NIH"
              style="position:absolute;left:-10000px" />
            <label for="agency-value-0">National Institutes of Health</label>
            <script>
              const control = document.querySelector("#agency-value-0");
              control.checked = localStorage.getItem("agency") === "NIH";
              control.addEventListener("change", () =>
                localStorage.setItem("agency", control.value));
            </script>
          </main>
        `,
      }),
    );
    await page.goto("http://portable-harness.test/radio");

    const control = page.locator("#agency-value-0");
    await activateBinaryControl(control);

    await expect(control).toBeChecked();
    await page.reload();
    await expect(page.locator("#agency-value-0")).toBeChecked();
  });

  test("accepts a durable save acknowledgement despite unrelated validation errors", async ({
    page,
  }) => {
    await page.route("http://portable-harness.test/attachment", (route) =>
      route.fulfill({
        contentType: "text/html",
        body: `
          <main>
            <button data-testid="apply-form-save">Save</button>
            <input id="attachment" type="hidden" value="attachment-123" />
            <div data-testid="file-input-existing-files">sample-upload-kb.pdf <button>Delete</button></div>
            <div id="result"></div>
            <script>
              if (localStorage.getItem("attachmentSaved") === "true") {
                document.querySelector("#attachment").dataset.persisted = "true";
              }
              document.querySelector("button").addEventListener("click", () => {
                localStorage.setItem("attachmentSaved", "true");
                document.querySelector("#result").textContent =
                  "Form was saved. Please correct the following errors before submitting.";
              });
            </script>
          </main>
        `,
      }),
    );
    await page.goto("http://portable-harness.test/attachment");

    await saveForPersistenceProbe(page);

    await expect(
      page.getByText("Form was saved", { exact: false }),
    ).toBeVisible();
    await expect(page.getByText("No errors were detected.")).toHaveCount(0);
    await page.reload();
    await expect(page.locator("#attachment")).toHaveValue("attachment-123");
    await expect(page.locator("#attachment")).toHaveAttribute(
      "data-persisted",
      "true",
    );
    await expect(page.getByTestId("file-input-existing-files")).toContainText(
      "sample-upload-kb.pdf",
    );
    await expect(page.getByRole("button", { name: "Delete" })).toBeVisible();
  });
});
