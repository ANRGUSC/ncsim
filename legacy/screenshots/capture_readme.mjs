/**
 * Capture screenshots of ncsim-viz for README documentation.
 * Uses the parallel-spread experiment for richer visuals.
 *
 * Prerequisites:
 *   1. Backend running: cd viz/server && python run.py
 *   2. Frontend running: cd viz && node node_modules/vite/bin/vite.js
 *   3. parallel-spread results in viz/public/sample-runs/
 *
 * Run from viz dir:
 *   node ../docs/screenshots/capture_readme.mjs
 */

import { createRequire } from "module";
import { fileURLToPath } from "url";
import { dirname, resolve } from "path";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const vizDir = resolve(__dirname, "../../viz");
const require = createRequire(resolve(vizDir, "package.json"));
const { chromium } = require("playwright");

const BASE_URL = "http://localhost:5173";
const VIEWPORT = { width: 1440, height: 900 };
const SHOT_DIR = __dirname;

async function shot(page, filename, description) {
  const path = `${SHOT_DIR}/${filename}`;
  await page.screenshot({ path });
  console.log(`  OK ${filename} - ${description}`);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: VIEWPORT });
  const page = await context.newPage();

  // 1. Home page
  await page.goto(BASE_URL);
  await page.waitForSelector("text=ncsim-viz", { timeout: 10000 });
  await shot(page, "readme-01-home.png", "Home page");

  // 2. Click "Visualize Existing" to see experiment browser
  await page.click("text=Visualize Existing");
  await page.waitForTimeout(1000);
  await shot(page, "readme-02-browse.png", "Experiment browser");

  // 3. Click the parallel-spread experiment card
  await page.click("text=parallel-spread");
  await page.waitForTimeout(2000);
  // Should land on Overview tab
  await shot(page, "readme-03-overview.png", "Overview dashboard");

  // 4. Network tab
  await page.click("text=Network");
  await page.waitForTimeout(1500);
  await shot(page, "readme-04-network.png", "Network topology");

  // 5. DAG tab
  await page.click("text=DAG");
  await page.waitForTimeout(1500);
  await shot(page, "readme-05-dag.png", "DAG task graph");

  // 6. Schedule tab (Gantt)
  await page.click("text=Schedule");
  await page.waitForTimeout(1500);
  await shot(page, "readme-06-schedule.png", "Gantt schedule");

  // 7. Simulation tab
  await page.click("text=Simulation");
  await page.waitForTimeout(1500);
  // Advance playback a bit for more interesting state
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(300);
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(500);
  await shot(page, "readme-07-simulation.png", "Simulation replay mid-execution");

  // 8. Go back to home and show Configure & Run
  await page.goto(BASE_URL);
  await page.waitForSelector("text=ncsim-viz");
  await page.click("text=Configure & Run");
  await page.waitForTimeout(1500);

  // Select Star topology preset for more interesting screenshot
  const topologyPreset = page.locator("select").first();
  // Find the topology preset select - look for one with "Star" option
  const selects = page.locator("select");
  const count = await selects.count();
  for (let i = 0; i < count; i++) {
    const options = await selects.nth(i).locator("option").allTextContents();
    if (options.some(o => o.includes("Star"))) {
      await selects.nth(i).selectOption({ label: options.find(o => o.includes("Star")) });
      break;
    }
  }
  await page.waitForTimeout(500);

  // Select Fork-Join DAG preset
  for (let i = 0; i < count; i++) {
    const options = await selects.nth(i).locator("option").allTextContents();
    if (options.some(o => o.includes("Fork"))) {
      await selects.nth(i).selectOption({ label: options.find(o => o.includes("Fork")) });
      break;
    }
  }
  await page.waitForTimeout(500);
  await shot(page, "readme-08-configure.png", "Configure & Run form");

  await browser.close();
  console.log("\nDone! Screenshots saved to docs/screenshots/");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
