import { expect, type Locator, type Page } from "@playwright/test";
import { schemaDefinitionToControlId } from "tests/e2e/portable-catalog/matrix-contract";
import { FORM_DEFAULTS } from "tests/e2e/utils/forms/form-defaults";

export const PORTABLE_INTERACTION_TIMEOUT = 10_000;
export const PORTABLE_SAVE_ACK_TIMEOUT = 30_000;

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

export type EligibleAttachmentControl = {
  definition: string;
  controlId: string;
  visibleInput: Locator;
};

/** Select the first declared attachment input that a user can currently use. */
export async function selectEligibleAttachmentControl(
  page: Page,
  definitions: string[],
): Promise<EligibleAttachmentControl> {
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
      return { definition, controlId, visibleInput };
    }
  }
  throw new Error(
    "no declared attachment widget is currently visible and enabled",
  );
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
  ).toBeVisible({ timeout: PORTABLE_SAVE_ACK_TIMEOUT });
}
