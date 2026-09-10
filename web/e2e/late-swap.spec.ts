import { test, expect as baseExpect } from "@playwright/test";
const expect = baseExpect.configure({ timeout: 40000 });
import { z } from "zod";
import { readFileSync, writeFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { workspaceSchema } from "../src/api";

test("per-game swaps, stale capture, entered authority, reconciliation and second-tab conflict", async ({
  page,
  context,
}) => {
  test.setTimeout(180000);
  expect.configure({ timeout: 15000 });
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && !m.text().includes("401") && !m.text().includes("409"))
      errors.push(m.text());
  });
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Continue as synthetic owner" }).click();
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
  async function create() {
    const fixture = z
      .object({
        setup: z.record(z.string(), z.unknown()),
        yahoo: z.string(),
        projections: z.record(z.string(), z.string()),
      })
      .parse(JSON.parse(readFileSync("../artifacts/local/decision-fixture.json", "utf8")));
    fixture.setup.yahoo_id = `late-browser-${Date.now()}`;
    fixture.setup.name = "Late swap browser verification";
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

    return { base, id: created.workspace_id };
  }
  const first = await create();
  const get = async (base = first.base) =>
    workspaceSchema.parse(await (await page.request.get(base)).json());
  const tighten = (w: Awaited<ReturnType<typeof get>>, index = 0) =>
    execFileSync(
      process.env.DFS_TEST_PYTHON ??
        (process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python"),
      [
        "-m",
        "tools.late_swap_clock_test",
        w.id,
        w.games[index].id,
        ...(process.env.RELEASE_DRILL ? ["--release-drill"] : []),
      ],
      { cwd: "..", encoding: "utf8" },
    );
  await page.goto(`/?workspace=${first.id}`);
  await page.getByRole("button", { name: "Complete lineup", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Apply exact preview", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Apply exact preview", exact: true }).click();
  await page.getByText("Review draft for entered recording", { exact: true }).click();
  await page.getByLabel("Recording / replacement reason").fill("Manually verified synthetic Yahoo");
  await page.getByRole("button", { name: "Record as entered in Yahoo", exact: true }).click();
  await expect(page.getByTestId("entered-status")).toHaveText("Draft matches recorded lineup");
  let w = await get();
  const entered = w.entered;
  await page.getByRole("button", { name: "Find alternatives", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Review exact completion", exact: true }),
  ).toBeVisible({ timeout: 40000 });
  await expect(page.getByText("Leading candidate", { exact: false }).first()).toBeVisible();
  await page
    .locator("details.candidate")
    .first()
    .evaluate((el) => el.setAttribute("open", ""));
  await expect(
    page.getByRole("button", { name: "Apply exact preview", exact: true }),
  ).toBeEnabled();
  tighten(w, 1);
  await page.getByRole("button", { name: "Apply exact preview", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Another game locked" })).toBeVisible();
  expect((await get()).draft_id).toBe(w.draft_id);
  await page.getByRole("button", { name: "Refresh workspace", exact: true }).click();
  await expect(page.getByText("Late swaps available", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Fixed · entered at kickoff", { exact: false }).first(),
  ).toBeVisible();
  await page.locator("aside.lineup").evaluate((el) => {
    el.scrollTop = 0;
  });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: `../artifacts/${process.env.RELEASE_DRILL ? "increment6-image" : "increment5"}-fixed.png`,
    fullPage: false,
  });
  // Explicit re-review/activation retains publication times and original evidence.
  const analysis = await (await page.request.get(`${first.base}/analysis`)).json();
  const reviewed = await command(
    `${first.base}/projections/${analysis.analysis.batch_id}/review`,
    {},
  );
  await command(`${first.base}/analysis/activate`, {
    expected_revision: reviewed.expected_revision,
    candidate_id: reviewed.candidate_id,
  });
  await page.getByRole("button", { name: "Refresh workspace", exact: true }).click();
  const remainderFixed = (await get()).late_swap.fixed;
  const remainderStarted = Date.now();
  await page.getByRole("button", { name: "Find alternatives", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Review exact completion", exact: true }),
  ).toBeVisible({ timeout: 40000 });
  await expect(page.getByText("Preview stale", { exact: false })).toHaveCount(0);
  await expect(page.locator("details.candidate")).not.toHaveCount(0);
  const remainderSeconds = (Date.now() - remainderStarted) / 1000;
  await page
    .locator("details.candidate")
    .last()
    .evaluate((el) => el.setAttribute("open", ""));
  await page.locator("details.candidate").last().getByRole("button", { name: /Apply/ }).click();
  await expect(page.getByTestId("entered-status")).toHaveText("Draft differs from recorded lineup");
  w = await get();
  expect(w.entered).toEqual(entered);
  expect(w.entered_status).toBe("differs");
  await page.screenshot({
    path: `../artifacts/${process.env.RELEASE_DRILL ? "increment6-image" : "increment5"}-remainder.png`,
    fullPage: true,
  });
  await page
    .getByLabel("Recording / replacement reason")
    .fill("Manually submitted synthetic late swap");
  await page.getByRole("button", { name: "Record as entered in Yahoo", exact: true }).click();
  await expect(page.getByTestId("entered-status")).toHaveText("Draft matches recorded lineup");
  await page.reload();
  await expect(page.getByTestId("entered-status")).toHaveText("Draft matches recorded lineup");
  w = await get();
  const secondTab = await context.newPage();
  await secondTab.goto(`/?workspace=${first.id}`);
  const editable = Object.keys(w.assignments).find((s) => !w.late_swap.fixed[s])!;
  await page.getByRole("button", { name: `Remove ${editable}`, exact: true }).click();
  await secondTab.getByRole("button", { name: `Remove ${editable}`, exact: true }).click();
  await secondTab.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(secondTab.getByRole("status")).toHaveText("Draft saved.");
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "Information changed" })).toBeVisible();
  await expect(page.getByText("1 unsaved edit", { exact: true })).toBeVisible();
  await page.screenshot({
    path: `../artifacts/${process.env.RELEASE_DRILL ? "increment6-image" : "increment5"}-conflict.png`,
    fullPage: true,
  });
  await secondTab.close();
  const missing = await create();
  await page.goto(`/?workspace=${missing.id}`);
  await page.getByRole("button", { name: "Complete lineup", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Apply exact preview", exact: true }),
  ).toBeEnabled();
  await page.getByRole("button", { name: "Apply exact preview", exact: true }).click();
  await expect.poll(async () => Object.keys((await get(missing.base)).assignments).length).toBe(9);
  let m = await get(missing.base);
  tighten(m);
  await page.getByRole("button", { name: "Refresh workspace", exact: true }).click();
  await expect(page.getByText("Reconciliation required", { exact: true })).toBeVisible();
  await page.getByText("Reconcile actual Yahoo lineup", { exact: true }).click();
  await page
    .getByRole("button", { name: "Start from unconfirmed saved draft assignments" })
    .click();
  await page
    .getByLabel("Historical correction reason")
    .fill("Forgot pregame recording; verified actual Yahoo slots");
  await page.getByLabel("Yahoo evidence reference").fill("Synthetic Yahoo screenshot reference");
  await page.getByRole("button", { name: "Preview reconciliation", exact: true }).click();
  await expect(page.getByText("Review exact historical correction", { exact: true })).toBeVisible();
  await page.screenshot({
    path: `../artifacts/${process.env.RELEASE_DRILL ? "increment6-image" : "increment5"}-reconcile.png`,
    fullPage: true,
  });
  await page
    .getByRole("button", {
      name: "Correct historical Yahoo facts; this does not authorize a late selection",
      exact: true,
    })
    .click();
  await expect(page.getByTestId("entered-status")).toHaveText("Draft matches recorded lineup");
  await page.reload();
  await expect(page.getByText("Late swaps available", { exact: true })).toBeVisible();
  m = await get(missing.base);
  expect(errors).toEqual([]);
  writeFileSync(
    `../artifacts/${process.env.RELEASE_DRILL ? "increment6-image" : "increment5"}-browser-evidence.json`,
    JSON.stringify(
      {
        first: await get(),
        reconciled: m,
        remainder: { seconds: remainderSeconds, fixed: remainderFixed },
        errors,
      },
      null,
      2,
    ),
  );
});
