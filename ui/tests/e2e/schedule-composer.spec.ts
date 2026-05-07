import { expect, test } from "@playwright/test";

test("Schedule composer creates and deletes a recurring task", async ({ page }) => {
  await page.goto("/");

  // Open Mission Control section, then the schedule composer.
  await page.getByRole("button", { name: /^Mission Control$/i }).click();
  await page.getByRole("button", { name: /New schedule/ }).click();

  const sheet = page.getByRole("dialog", { name: /New schedule/i });
  await expect(sheet).toBeVisible();

  // Fill required fields.
  const name = `e2e-${Date.now()}`;
  await sheet.getByPlaceholder(/Morning summary/i).fill(name);
  await sheet.getByPlaceholder(/each time/i).fill(`Test schedule task ${name}`);
  await sheet.getByRole("button", { name: /^Create$/ }).click();

  // Schedule should appear in the list.
  await expect(page.getByText(name)).toBeVisible();

  // Tear down via the trash icon on this row.
  const row = page.locator("li", { hasText: name });
  await row.locator("button").filter({ hasText: /Disable|Enable/ }).first().click();
  // Now click the trash icon by its aria-label fallback (last button in row).
  await row.locator("button").last().click();
  await expect(page.getByText(name)).toBeHidden();
});
