import { expect, test } from "@playwright/test";

test("Activity page renders heatmap, firehose, sessions table", async ({ page }) => {
  await page.goto("/activity");
  await expect(page.getByText(/30-day intensity/i)).toBeVisible();
  await expect(page.getByText(/OTEL firehose/i)).toBeVisible();
  await expect(page.getByText(/All sessions/i)).toBeVisible();
});

test("Skills page shows MCP drill-down kicker", async ({ page }) => {
  await page.goto("/skills");
  await expect(page.getByText(/MCP servers/i)).toBeVisible();
  await expect(page.getByText(/Skills registry/i)).toBeVisible();
});
