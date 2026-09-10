import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { z } from "zod";

test("saved phone review: navigation, evidence, exact differences and keyboard without mutations", async ({
  page,
}) => {
  const evidence = z
    .object({ first: z.object({ id: z.string() }) })
    .parse(JSON.parse(readFileSync("../artifacts/increment6-image-browser-evidence.json", "utf8")));
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Continue as synthetic owner" }).click();
  await page.goto(`/?workspace=${evidence.first.id}`);
  await expect(page.getByRole("button", { name: "Refresh workspace", exact: true })).toBeVisible();
  const mutations: string[] = [];
  const errors: string[] = [];
  page.on("request", (r) => {
    if (r.method() !== "GET") mutations.push(r.url());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  for (const width of [320, 390, 430]) {
    await page.setViewportSize({ width, height: 844 });
    await expect(page.getByText("DFS / REVIEW ONLY")).toBeVisible();
    for (const section of ["Briefing", "Players", "Lineup", "Previews"]) {
      await page.getByRole("button", { name: section, exact: true }).click();
      await expect(page.locator("h2")).toBeVisible();
      await expect(
        page.getByRole("button", {
          name: /Apply|Undo|Reconcile|Record as entered|Save|Complete lineup/,
        }),
      ).toHaveCount(0);
      if (section === "Players") {
        await page.getByLabel("Search players").fill("Alpha");
        await page.getByText("Player evidence", { exact: true }).first().click();
      }
      if (section === "Previews") {
        const summaries = page.locator(".candidate > summary");
        if (await summaries.count()) await summaries.first().click();
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await page.screenshot({
        path: `../artifacts/increment6-mobile-${width}-${section.toLowerCase()}.png`,
        fullPage: true,
      });
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
    }
    await page.getByRole("button", { name: "Briefing", exact: true }).focus();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Players", exact: true })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { name: "Player research" })).toBeVisible();
  }
  expect(mutations).toEqual([]);
  expect(errors).toEqual([]);
});
