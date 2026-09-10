import { z } from "zod";
import { workspaceSchema } from "../src/api";
import { test, expect } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";

test("decision workspace: context, alternatives, Apply, Undo, attestation and conflict", async ({
  page,
}) => {
  test.setTimeout(120000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Continue as synthetic owner" }).click();
  await expect(page.getByText("Synthetic test identity", { exact: true })).toBeVisible();
  const csrf = (await (await page.request.get("/api/session")).json()).csrf;
  async function command(url: string, body: unknown) {
    const r = await page.request.post(url, {
      data: body,
      headers: {
        origin: "http://127.0.0.1:8765",
        "x-csrf-token": csrf,
        "idempotency-key": crypto.randomUUID(),
      },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    return r.json();
  }
  const fixture = z
    .object({
      setup: z.record(z.string(), z.unknown()),
      yahoo: z.string(),
      projections: z.record(z.string(), z.string()),
    })
    .parse(JSON.parse(readFileSync("../artifacts/local/decision-fixture.json", "utf8")));
  fixture.setup.yahoo_id = `decision-browser-${Date.now()}`;
  fixture.setup.name = "Decision browser verification";
  const created = await command("/api/workspaces", fixture.setup),
    base = `/api/workspaces/${created.workspace_id}`;
  const headers = { origin: "http://127.0.0.1:8765", "x-csrf-token": csrf };
  const upload = await page.request.post(`${base}/imports`, {
    headers,
    multipart: {
      file: { name: "synthetic.csv", mimeType: "text/csv", buffer: Buffer.from(fixture.yahoo) },
    },
  });
  const bid = (await upload.json()).batch_id;
  await command(`${base}/activate`, { expected_revision: 0, batch_revision: 1, batch_id: bid });
  const form = new FormData();
  const positions = Object.keys(fixture.projections);
  positions.forEach((p) =>
    form.append("files", new File([fixture.projections[p]], `${p}.csv`, { type: "text/csv" })),
  );
  form.append("positions", JSON.stringify(positions));
  form.append(
    "declaration",
    JSON.stringify({
      season: fixture.setup.season,
      period: fixture.setup.round,
      scoring: "half-ppr-baseline",
      evidence: "Synthetic main settings match baseline",
      source_context: "Synthetic future fixture; not live forecasts",
      material_settings_match: true,
    }),
  );
  const batch = await page.request.post(`${base}/projections`, { headers, multipart: form });
  expect(batch.ok(), await batch.text()).toBeTruthy();
  const review = await command(`${base}/projections/${(await batch.json()).batch_id}/review`, {});
  await command(`${base}/analysis/activate`, {
    expected_revision: review.expected_revision,
    candidate_id: review.candidate_id,
  });
  await page.goto(`/?workspace=${created.workspace_id}`);
  await expect(page.getByRole("heading", { name: "Decision browser verification" })).toBeVisible();
  await page.getByText("Add or revise game evidence", { exact: true }).click();
  await page.getByLabel("Source / bookmaker").fill("Synthetic bookmaker");
  await page
    .getByLabel("Source reference", { exact: true })
    .fill("Manual synthetic full-game paired quote");
  await page
    .getByLabel("Observed timestamp with timezone")
    .fill(new Date(Date.now() - 60000).toISOString());
  await page.getByLabel("Game total", { exact: true }).fill("47.5");
  await page.getByLabel("Home team spread", { exact: false }).fill("-3.5");
  await page
    .getByLabel("Reason / observation context")
    .fill("Synthetic evidence for browser verification");
  await page.getByRole("button", { name: "Save game evidence" }).click();
  await expect(page.getByText(/Implied:.*25.5/)).toBeVisible();
  await page.getByText("Add or revise game evidence", { exact: true }).click();
  await page.getByLabel("Search players").fill("Alternative");
  await page.getByLabel("Position filter").selectOption("RB");
  await page.getByLabel("Sort players").selectOption("value");
  const player = page.locator(".player").filter({ hasText: "Synthetic AlternativeRB" });
  await expect(player).toBeVisible();
  await player.getByText("Player evidence", { exact: true }).click();
  await expect(player).toContainText("Yahoo eligibility RB");
  await page.screenshot({
    path: `../artifacts/${process.env.RELEASE_DRILL ? "increment6-decisions" : "increment4"}-research.png`,
    fullPage: true,
  });
  await page.getByLabel("Search players").fill("");
  await page.getByLabel("Position filter").selectOption("");
  await page.getByText("Keep / Avoid and availability", { exact: true }).click();
  await page
    .getByLabel("Preference subject")
    .selectOption({ label: "Synthetic Charlie · RB · CHI" });
  await page.getByRole("button", { name: "Keep player", exact: true }).click();
  await expect(page.getByText("Synthetic Charlie: keep", { exact: false })).toBeVisible();
  await page.getByLabel("Preference subject").selectOption({ label: "Synthetic Bravo · QB · BUF" });
  await page.getByRole("button", { name: "Avoid player", exact: true }).click();
  await expect(page.getByText("Synthetic Bravo: avoid", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Complete lineup", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review exact completion" })).toBeVisible({
    timeout: 45000,
  });
  await page.getByRole("button", { name: "Apply exact preview", exact: true }).click();
  await expect(page.locator("aside").getByText("Open slot", { exact: true })).toHaveCount(0);
  const before = workspaceSchema.parse(await (await page.request.get(base)).json());
  await page.locator("aside").getByText("Temporary request controls", { exact: true }).click();
  await page.getByLabel("Temporary include").selectOption({ label: "Synthetic Alpha" });
  await page.getByLabel("Temporary exclude").selectOption({ label: "Synthetic Bravo" });
  await page.getByRole("button", { name: "Find alternatives", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review exact completion" })).toBeVisible({
    timeout: 45000,
  });
  await page
    .locator("summary")
    .filter({ hasText: /^Alternative 1/ })
    .click();
  await expect(
    page.getByText("Optimal under added exclusion", { exact: false }).first(),
  ).toBeVisible();
  await page
    .locator(".candidate")
    .nth(1)
    .evaluate((el) => {
      const panel = el.closest("aside");
      if (panel)
        panel.scrollTop += el.getBoundingClientRect().top - panel.getBoundingClientRect().top - 12;
    });
  await page.screenshot({
    path: `../artifacts/${process.env.RELEASE_DRILL ? "increment6-decisions" : "increment4"}-candidates.png`,
  });
  await page.getByRole("button", { name: "Apply alternative 1", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Preview stale — information changed" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Undo latest lineup action" }).click();
  await expect
    .poll(async () =>
      Object.entries(workspaceSchema.parse(await (await page.request.get(base)).json()).assignments)
        .map(([s, p]) => [s, p.entry_id])
        .sort(),
    )
    .toEqual(
      Object.entries(before.assignments)
        .map(([s, p]) => [s, p.entry_id])
        .sort(),
    );
  await page.getByText("Review draft for entered recording", { exact: true }).click();
  await page
    .getByLabel("Recording / replacement reason")
    .fill("I manually entered this synthetic lineup in test Yahoo context");
  await page.getByRole("button", { name: "Record as entered in Yahoo", exact: true }).click();
  await expect(page.getByTestId("entered-status")).toHaveText("Draft matches recorded lineup");
  const recorded = (await (await page.request.get(base)).json()).entered;
  await page.getByRole("button", { name: "Remove WR1", exact: true }).click();
  await expect(page.getByTestId("entered-status")).toHaveText("Draft differs from recorded lineup");
  await page.getByRole("button", { name: "Refresh workspace", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Unsaved edits retained");
  await expect(page.locator("aside")).toContainText("1 unsaved edit");
  await page
    .getByRole("button", { name: "Discard attempted edits and reload saved draft" })
    .click();
  await page.getByRole("button", { name: "Remove WR1", exact: true }).click();
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByTestId("entered-status")).toHaveText("Draft differs from recorded lineup");
  await page.reload();
  await expect(page.getByTestId("entered-status")).toHaveText("Draft differs from recorded lineup");
  expect((await (await page.request.get(base)).json()).entered).toEqual(recorded);
  const history = await page.request.get(`${base}/decision-history`);
  expect(history.ok()).toBeTruthy();
  expect((await history.json()).entered[0].id).toBe(recorded.id);
  await page.screenshot({
    path: `../artifacts/${process.env.RELEASE_DRILL ? "increment6-decisions" : "increment4"}-entered.png`,
    fullPage: true,
  });
  // A second tab edits after the first tab captures a saved recommendation.
  await page.getByRole("button", { name: "Complete lineup", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Review exact completion" })).toBeVisible({
    timeout: 45000,
  });
  const second = await page.context().newPage();
  await second.goto(page.url());
  await second.getByRole("button", { name: "Remove WR2", exact: true }).click();
  await second.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(second.locator("aside").getByText("Open slot", { exact: true })).toHaveCount(2);
  // Expected rejection generates a console HTTP 409; collect page exceptions separately below.
  const rejected = page.waitForResponse((r) => r.url().endsWith("/apply"));
  await page.getByRole("button", { name: "Apply exact preview", exact: true }).click();
  expect((await rejected).status()).toBe(409);
  await expect(page.getByRole("alert")).toContainText("Information changed");
  await page.screenshot({
    path: `../artifacts/${process.env.RELEASE_DRILL ? "increment6-decisions" : "increment4"}-conflict.png`,
    fullPage: true,
  });
  await second.close();
  const unexpected = errors.filter((e) => !e.includes("409") && !e.includes("401"));
  expect(unexpected).toEqual([]);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  writeFileSync(
    `../artifacts/${process.env.RELEASE_DRILL ? "increment6-decisions" : "increment4"}-browser-evidence.json`,
    JSON.stringify(
      { workspace: created.workspace_id, errors, unexpected, entered_id: recorded.id },
      null,
      2,
    ),
  );
});
