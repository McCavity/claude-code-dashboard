import { expect, test } from "@playwright/test";

test.describe("Command page", () => {
  test("shell renders with KPIs and observability section", async ({ page }) => {
    await page.goto("/");

    // App shell.
    await expect(page.getByRole("link", { name: /Command Centre/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Command$/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /^Activity$/ })).toBeVisible();
    await expect(page.getByRole("link", { name: /Skills & MCP/ })).toBeVisible();

    // KPIs row — at least one tile labeled "Sessions today".
    await expect(page.getByText(/Sessions today/i)).toBeVisible();

    // CollapsibleSection — Observability.
    await expect(page.getByText(/Observability/i)).toBeVisible();
  });
});
