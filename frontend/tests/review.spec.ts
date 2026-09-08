import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
const readEnv = (path: string) =>
  Object.fromEntries(
    readFileSync(resolve(path), "utf8")
      .split("\n")
      .filter((line) => line.includes("="))
      .map((line) => {
        const i = line.indexOf("=");
        return [line.slice(0, i), line.slice(i + 1)];
      }),
  );
const front = readEnv(".env.local"),
  back = readEnv("../backend/.env");
test("MCP proposal → human review → simulated execution; mobile has no overflow", async ({
  page,
  request,
}, testInfo) => {
  const response = await request.post("http://127.0.0.1:8000/mcp", {
    headers: {
      Authorization: `Bearer ${back.MCP_TOKEN}`,
      Accept: "application/json, text/event-stream",
    },
    data: {
      jsonrpc: "2.0",
      id: 1,
      method: "tools/call",
      params: {
        name: "propose_transfer",
        arguments: {
          recipient: "Taylor Demo",
          destination: "DEMO-9234",
          amount_cents: 4890,
          concept: "Prueba E2E",
          idempotency_key: crypto.randomUUID(),
        },
      },
    },
  });
  expect(response.ok()).toBeTruthy();
  const result = await response.json();
  expect(result.result.isError).toBeFalsy();
  const proposal =
    result.result.structuredContent ??
    JSON.parse(result.result.content[0].text);
  const actionId = process.env.REVIEW_ACTION_ID ?? proposal.id;
  await page.goto(`/?action=${actionId}`);
  await expect(page.getByLabel("Detalle de acción")).toHaveCount(0);
  await page.getByLabel("Contraseña").fill(front.REVIEW_PASSWORD);
  await page.getByRole("button", { name: "Entrar al espacio" }).click();
  await expect(
    page.getByRole("heading", { name: "Centro de control." }),
  ).toBeVisible();
  await expect(
    page
      .getByLabel("Detalle de acción")
      .getByText(actionId.slice(0, 8), { exact: true }),
  ).toBeVisible();
  const confirm = page.getByRole("button", { name: "Confirmar simulación" });
  await expect(confirm).toBeDisabled();
  await page.getByRole("checkbox").check();
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByText("Simulación completada")).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: testInfo.outputPath("dashboard-desktop.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("heading", { name: "Centro de control." }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: testInfo.outputPath("dashboard-mobile.png"),
    fullPage: true,
  });
});
