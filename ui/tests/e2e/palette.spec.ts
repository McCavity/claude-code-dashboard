import { expect, test } from "@playwright/test";

test("Command palette opens with ⌘K and navigates", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Meta+k");
  const palette = page.getByRole("dialog", { name: /Command palette/i });
  await expect(palette).toBeVisible();

  await palette.getByPlaceholder(/Search pages/i).fill("activ");
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(/\/activity$/);
});

test("Esc closes palette without navigating", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Meta+k");
  const palette = page.getByRole("dialog", { name: /Command palette/i });
  await expect(palette).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(palette).toBeHidden();
  expect(page.url()).toMatch(/\/$/);
});
