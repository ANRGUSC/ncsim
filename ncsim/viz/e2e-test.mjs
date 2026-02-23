/**
 * Playwright E2E test for ncsim-viz.
 *
 * Prerequisites:
 *   1. Backend running:  cd viz/server && python run.py
 *   2. Frontend running: cd viz && npm run dev
 *
 * Run:
 *   cd viz && node e2e-test.mjs
 */

import { chromium } from "playwright";

const BASE_URL = "http://localhost:5173";

async function run() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  console.log("1. Opening home page...");
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await page.screenshot({ path: "e2e-screenshots/01-home.png" });

  console.log("2. Clicking 'Configure & Run'...");
  await page.getByRole("button", { name: /configure/i }).click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: "e2e-screenshots/02-configure.png" });

  console.log("3. Selecting Random (radio-range) topology with 5 nodes...");
  // Find the topology preset select by scanning all <select> elements
  const selects = page.locator("select");
  const selectCount = await selects.count();
  let topoFound = false;
  for (let i = 0; i < selectCount; i++) {
    const options = await selects.nth(i).locator("option").allTextContents();
    const randomOpt = options.find((o) => /random.*radio/i.test(o));
    if (randomOpt) {
      await selects.nth(i).selectOption({ label: randomOpt });
      topoFound = true;
      console.log(`   Found topology select (index ${i}), selected: "${randomOpt}"`);
      break;
    }
  }
  if (!topoFound) {
    console.warn("   WARNING: Could not find Random (radio-range) topology preset.");
  }
  await page.waitForTimeout(300);

  // Set node count to 5 if there's a number input for it
  const numberInputs = page.locator('input[type="number"]');
  const numCount = await numberInputs.count();
  if (numCount > 0) {
    await numberInputs.first().fill("5");
    await numberInputs.first().press("Tab");
    console.log("   Set node count to 5.");
  }
  await page.waitForTimeout(300);
  await page.screenshot({ path: "e2e-screenshots/03-topology-selected.png" });

  console.log("4. Clicking 'Run Experiment'...");
  const runButton = page.getByRole("button", { name: /run experiment/i });
  await runButton.click();

  console.log("5. Waiting for results (up to 30s)...");
  // Wait for results to load — look for makespan text appearing on the page
  try {
    await page.waitForFunction(
      () => /makespan/i.test(document.body.textContent || ""),
      { timeout: 30000 }
    );
    console.log("   Results loaded (makespan detected).");
  } catch {
    console.warn("   Timed out waiting for makespan; continuing...");
    await page.waitForTimeout(3000);
  }

  await page.screenshot({ path: "e2e-screenshots/04-results.png" });

  console.log("6. Checking Overview tab for metrics...");
  // Click Overview tab if visible
  const overviewTab = page.getByRole("button", { name: /overview/i }).first();
  if (await overviewTab.isVisible().catch(() => false)) {
    await overviewTab.click();
    await page.waitForTimeout(500);
  }

  await page.screenshot({ path: "e2e-screenshots/05-overview.png" });

  // Verify key metrics are present
  const pageText = await page.textContent("body");
  const hasMakespan = /makespan/i.test(pageText);
  const hasNodes = /node/i.test(pageText);
  const hasTasks = /task/i.test(pageText);

  console.log(`   Makespan: ${hasMakespan ? "YES" : "no"}, Nodes: ${hasNodes ? "YES" : "no"}, Tasks: ${hasTasks ? "YES" : "no"}`);

  if (!hasMakespan) {
    console.error("FAIL: Makespan metric not found on page.");
    await page.screenshot({ path: "e2e-screenshots/06-fail.png", fullPage: true });
    await browser.close();
    process.exit(1);
  }

  console.log("7. Taking final screenshot...");
  await page.screenshot({ path: "e2e-screenshots/06-final.png", fullPage: true });

  await browser.close();
  console.log("\nE2E test PASSED. Screenshots saved to e2e-screenshots/");
}

run().catch((err) => {
  console.error("E2E test FAILED:", err.message);
  process.exit(1);
});
