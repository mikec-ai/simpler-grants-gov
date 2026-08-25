import { expect, type Locator, type Page } from "@playwright/test";
import { FORM_DEFAULTS } from "tests/e2e/utils/forms/form-defaults";

const PORTABLE_INTERACTION_TIMEOUT = 10_000;

/**
 * Activate a checkbox or radio through its visible label when one exists.
 *
 * USWDS-style controls can keep the native input offscreen while exposing a
 * visible, associated label. Clicking that label matches the user interaction
 * and avoids allowing Playwright's default actionability retry to consume the
 * catalog's full per-form timeout.
 */
export async function activateBinaryControl(control: Locator): Promise<void> {
  const id = await control.getAttribute("id");
  const label = id
    ? control.page().locator(`label[for=${JSON.stringify(id)}]`)
    : null;

  if (label && (await label.count()) > 0 && (await label.isVisible())) {
    await label.click({ timeout: PORTABLE_INTERACTION_TIMEOUT });
  } else {
    await control.check({ timeout: PORTABLE_INTERACTION_TIMEOUT });
  }
  await expect(control).toBeChecked({ timeout: PORTABLE_INTERACTION_TIMEOUT });
}

export async function clickPortableSaveButton(page: Page): Promise<void> {
  const saveButton = page
    .getByTestId(FORM_DEFAULTS.saveButtonTestId)
    .or(page.getByRole("button", { name: /save/i }).first());
  await expect(saveButton).toBeVisible({
    timeout: PORTABLE_INTERACTION_TIMEOUT,
  });
  await saveButton.click({ timeout: PORTABLE_INTERACTION_TIMEOUT });
}

/**
 * Save a form for a persistence probe without asserting whole-form validity.
 *
 * Attachments can be durably saved while unrelated required fields still
 * produce validation errors. The caller must verify the specific persisted
 * field after reload; this helper only proves the save request was accepted.
 */
export async function saveForPersistenceProbe(page: Page): Promise<void> {
  await clickPortableSaveButton(page);
  await expect(
    page.getByText(FORM_DEFAULTS.formSavedHeading, { exact: false }),
  ).toBeVisible({ timeout: PORTABLE_INTERACTION_TIMEOUT });
}
