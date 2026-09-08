import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Transfer } from "../lib/types";

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
const front = readEnv(".env.local"), back = readEnv("../backend/.env");
const reviewerHeaders = { Authorization: `Bearer ${back.REVIEWER_TOKEN}` };

async function propose(request: APIRequestContext): Promise<Transfer> {
  const response = await request.post("http://127.0.0.1:8000/mcp", {
    headers: {
      Authorization: `Bearer ${back.MCP_TOKEN}`,
      Accept: "application/json, text/event-stream",
    },
    data: {
      jsonrpc: "2.0", id: 1, method: "tools/call",
      params: {
        name: "propose_transfer",
        arguments: {
          recipient: "Taylor Demo", destination: "DEMO-9234", amount_cents: 4890,
          concept: "Prueba E2E", idempotency_key: crypto.randomUUID(),
        },
      },
    },
  });
  expect(response.ok()).toBeTruthy();
  const result = await response.json();
  expect(result.error).toBeUndefined();
  expect(result.result.isError).toBeFalsy();
  return result.result.structuredContent ?? JSON.parse(result.result.content[0].text);
}

async function readAction(request: APIRequestContext, id: string): Promise<Transfer> {
  const response = await request.get(`http://127.0.0.1:8000/actions/${id}`, { headers: reviewerHeaders });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function review(page: Page, id: string) {
  await page.goto(`/?action=${id}`);
  await expect(page.getByLabel("Detalle de acci\u00f3n")).toHaveCount(0);
  await page.getByLabel("Contrase\u00f1a").fill(front.REVIEW_PASSWORD);
  await page.getByRole("button", { name: "Entrar al espacio" }).click();
  await expect(page.getByRole("heading", { name: "Centro de control." })).toBeVisible();
  await expect(page.getByLabel("Detalle de acci\u00f3n").getByText(id.slice(0, 8), { exact: true })).toBeVisible();
}

async function decideViaApi(request: APIRequestContext, proposal: Transfer, decision: "confirm" | "reject") {
  return request.post(`http://127.0.0.1:8000/actions/${proposal.id}/decision`, {
    headers: reviewerHeaders, data: { fingerprint: proposal.fingerprint, decision },
  });
}

test("MCP proposal requires explicit review; execution audit is idempotent and mobile fits", async ({
  page, request,
}, testInfo) => {
  const created = await propose(request);
  const proposal = process.env.REVIEW_ACTION_ID
    ? await readAction(request, process.env.REVIEW_ACTION_ID) : created;
  await review(page, proposal.id);
  const pending = await readAction(request, proposal.id);
  expect(pending.status).toBe("pending");
  expect(pending.audit?.map((event) => event.event)).toEqual(["proposed"]);
  const confirm = page.getByRole("button", { name: "Confirmar simulaci\u00f3n" });
  await expect(confirm).toBeDisabled();
  await page.getByRole("checkbox").check();
  await expect(confirm).toBeEnabled();
  await confirm.click();
  await expect(page.getByText("Simulaci\u00f3n completada")).toBeVisible();
  const executed = await readAction(request, proposal.id);
  expect(executed.status).toBe("executed");
  expect(executed.simulated).toBe(true);
  expect(executed.audit?.map(({ event, actor }) => [event, actor])).toEqual([
    ["proposed", "agent"], ["confirmed", "human"], ["executed", "simulator"],
  ]);
  expect((await decideViaApi(request, proposal, "confirm")).status()).toBe(200);
  expect((await decideViaApi(request, proposal, "reject")).status()).toBe(409);
  expect((await readAction(request, proposal.id)).audit).toEqual(executed.audit);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("dashboard-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "Centro de control." })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("dashboard-mobile.png"), fullPage: true });
});

test("rejecting needs no confirmation checkbox and can never execute", async ({ page, request }) => {
  const proposal = await propose(request);
  await review(page, proposal.id);
  await expect(page.getByRole("checkbox")).not.toBeChecked();
  await page.getByRole("button", { name: "Rechazar propuesta" }).click();
  await expect(page.getByText("Acci\u00f3n rechazada")).toBeVisible();
  const rejected = await readAction(request, proposal.id);
  expect(rejected.status).toBe("rejected");
  expect(rejected.audit?.map(({ event, actor }) => [event, actor])).toEqual([
    ["proposed", "agent"], ["rejected", "human"],
  ]);
  expect((await decideViaApi(request, proposal, "reject")).status()).toBe(200);
  expect((await decideViaApi(request, proposal, "confirm")).status()).toBe(409);
  expect((await readAction(request, proposal.id)).audit).toEqual(rejected.audit);
});
