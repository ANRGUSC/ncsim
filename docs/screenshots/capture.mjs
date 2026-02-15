/**
 * Playwright screenshot capture for ncsim documentation.
 *
 * Captures ~16 screenshots of the viz UI for use in userguide.html.
 *
 * Prerequisites:
 *   1. Backend running:  cd viz/server && python run.py
 *   2. Frontend running: cd viz && npm run dev
 *   3. Playwright installed: npx playwright install chromium
 *
 * Run:
 *   cd viz && node ../docs/screenshots/capture.mjs
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
const SHOT_DIR = __dirname; // saves into docs/screenshots/

// Helper: wait for server to be ready
async function waitForServer(url, retries = 30, delayMs = 1000) {
  for (let i = 0; i < retries; i++) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch { /* not ready */ }
    console.log(`  Waiting for ${url}... (${i + 1}/${retries})`);
    await new Promise((r) => setTimeout(r, delayMs));
  }
  throw new Error(`Server at ${url} not ready after ${retries} retries`);
}

// Helper: find a <select> by scanning for an option matching a regex
async function findSelectByOption(page, regex) {
  const selects = page.locator("select");
  const count = await selects.count();
  for (let i = 0; i < count; i++) {
    const options = await selects.nth(i).locator("option").allTextContents();
    const match = options.find((o) => regex.test(o));
    if (match) return { select: selects.nth(i), label: match };
  }
  return null;
}

// Helper: screenshot with logging
async function shot(page, filename, description) {
  const path = `${SHOT_DIR}/${filename}`;
  await page.screenshot({ path });
  console.log(`  ✓ ${filename} — ${description}`);
}

async function run() {
  console.log("Waiting for servers...");
  await waitForServer(BASE_URL);
  console.log("Servers ready.\n");

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: VIEWPORT });

  // ── 01: Home page ──
  console.log("01. Home page");
  await page.goto(BASE_URL, { waitUntil: "networkidle" });
  await shot(page, "01-home.png", "Home page with two cards");

  // ── 02: Configure form (basic config) ──
  console.log("02. Configure form");
  await page.getByText("Configure & Run").click();
  await page.waitForTimeout(500);
  await shot(page, "02-configure-form.png", "Top of configure form");

  // ── 03: Topology — Star preset ──
  console.log("03. Topology — Star");
  try {
    const topoResult = await findSelectByOption(page, /^Star$/);
    if (topoResult) {
      await topoResult.select.selectOption({ label: topoResult.label });
      await page.waitForTimeout(300);
    }
    // Set node count to 5 via range slider or number input
    const nodeCountInputs = page.locator('input[type="range"]');
    const rangeCount = await nodeCountInputs.count();
    if (rangeCount > 0) {
      await nodeCountInputs.first().fill("5");
      await page.waitForTimeout(200);
    }
    // Scroll topology section into view
    const topoHeading = page.getByText("Network Topology");
    if (await topoHeading.isVisible()) {
      await topoHeading.scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
    }
    await shot(page, "03-topology-star.png", "Star topology with 5 nodes");
  } catch (e) {
    console.warn(`  ⚠ Step 03 failed: ${e.message}`);
  }

  // ── 04: DAG — Fork-Join preset ──
  console.log("04. DAG — Fork-Join");
  try {
    const dagResult = await findSelectByOption(page, /fork.join/i);
    if (dagResult) {
      await dagResult.select.selectOption({ label: dagResult.label });
      await page.waitForTimeout(300);
    }
    const dagHeading = page.getByText("DAG Structure");
    if (await dagHeading.isVisible()) {
      await dagHeading.scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
    }
    await shot(page, "04-dag-forkjoin.png", "Fork-Join DAG preset");
  } catch (e) {
    console.warn(`  ⚠ Step 04 failed: ${e.message}`);
  }

  // ── 05: Interference — CSMA/CA Bianchi ──
  console.log("05. Interference — CSMA/CA Bianchi");
  try {
    const intResult = await findSelectByOption(page, /bianchi/i);
    if (intResult) {
      await intResult.select.selectOption({ label: intResult.label });
      await page.waitForTimeout(400);
    }
    const intHeading = page.getByText("Interference Model");
    if (await intHeading.isVisible()) {
      await intHeading.scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
    }
    await shot(page, "05-interference.png", "CSMA/CA Bianchi with WiFi RF panel");
  } catch (e) {
    console.warn(`  ⚠ Step 05 failed: ${e.message}`);
  }

  // ── 06: YAML Preview ──
  console.log("06. YAML Preview");
  try {
    const yamlHeading = page.getByText("Scenario YAML Preview");
    if (await yamlHeading.isVisible()) {
      await yamlHeading.scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
    }
    await shot(page, "06-yaml-preview.png", "Generated YAML preview");
  } catch (e) {
    console.warn(`  ⚠ Step 06 failed: ${e.message}`);
  }

  // ── 07: Running state ──
  // Reset to a simple, fast config first
  console.log("07. Running experiment (simple config)");
  try {
    // Reset topology to Line with 3 nodes
    const topoLine = await findSelectByOption(page, /^Line$/);
    if (topoLine) {
      await topoLine.select.selectOption({ label: topoLine.label });
      await page.waitForTimeout(200);
    }
    const rangeInputs = page.locator('input[type="range"]');
    const rc = await rangeInputs.count();
    if (rc > 0) await rangeInputs.first().fill("3");

    // Reset DAG to Chain with 3 tasks
    const dagChain = await findSelectByOption(page, /^Chain$/);
    if (dagChain) {
      await dagChain.select.selectOption({ label: dagChain.label });
      await page.waitForTimeout(200);
    }
    if (rc > 1) await rangeInputs.nth(1).fill("3");

    // Reset interference to None
    const intNone = await findSelectByOption(page, /^None$/);
    if (intNone) {
      await intNone.select.selectOption({ label: intNone.label });
      await page.waitForTimeout(200);
    }

    // Scroll to top and click Run
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(200);

    const runBtn = page.getByRole("button", { name: /run experiment/i });
    await runBtn.scrollIntoViewIfNeeded();
    await runBtn.click();
    // Capture the running spinner immediately
    await page.waitForTimeout(300);
    await shot(page, "07-running.png", "Running spinner state");
  } catch (e) {
    console.warn(`  ⚠ Step 07 failed: ${e.message}`);
  }

  // ── Wait for results ──
  console.log("   Waiting for results...");
  try {
    await page.waitForFunction(
      () => /makespan/i.test(document.body.textContent || ""),
      { timeout: 30000 }
    );
    console.log("   Results loaded.");
  } catch {
    console.warn("   Timed out waiting for results; continuing...");
    await page.waitForTimeout(3000);
  }

  // ── 08: Overview tab ──
  console.log("08. Overview tab");
  try {
    const overviewBtn = page.getByRole("button", { name: /overview/i }).first();
    if (await overviewBtn.isVisible().catch(() => false)) {
      await overviewBtn.click();
      await page.waitForTimeout(500);
    }
    await shot(page, "08-overview.png", "Overview tab with metrics");
  } catch (e) {
    console.warn(`  ⚠ Step 08 failed: ${e.message}`);
  }

  // ── 09: Network tab ──
  console.log("09. Network tab");
  try {
    const networkBtn = page.getByRole("button", { name: /network/i }).first();
    await networkBtn.click();
    await page.waitForTimeout(1500); // D3 render time
    await shot(page, "09-network.png", "Network topology view");
  } catch (e) {
    console.warn(`  ⚠ Step 09 failed: ${e.message}`);
  }

  // ── 10: DAG tab ──
  console.log("10. DAG tab");
  try {
    const dagBtn = page.getByRole("button", { name: /^dag$/i }).first();
    await dagBtn.click();
    await page.waitForTimeout(500);
    await shot(page, "10-dag.png", "DAG layout view");
  } catch (e) {
    console.warn(`  ⚠ Step 10 failed: ${e.message}`);
  }

  // ── 11: Schedule tab ──
  console.log("11. Schedule tab");
  try {
    const schedBtn = page.getByRole("button", { name: /schedule/i }).first();
    await schedBtn.click();
    await page.waitForTimeout(500);
    await shot(page, "11-schedule.png", "Gantt chart");
  } catch (e) {
    console.warn(`  ⚠ Step 11 failed: ${e.message}`);
  }

  // ── 12: Simulation tab ──
  console.log("12. Simulation tab");
  try {
    const simBtn = page.getByRole("button", { name: /simulation/i }).first();
    await simBtn.click();
    await page.waitForTimeout(1000);
    await shot(page, "12-simulation.png", "Simulation view");
  } catch (e) {
    console.warn(`  ⚠ Step 12 failed: ${e.message}`);
  }

  // ── 13: Parameters tab ──
  console.log("13. Parameters tab");
  try {
    // Use keyboard shortcut '6' to switch to Parameters tab
    await page.keyboard.press("6");
    await page.waitForTimeout(500);
    await shot(page, "13-parameters.png", "Parameters panel");
  } catch (e) {
    console.warn(`  ⚠ Step 13 failed: ${e.message}`);
  }

  // ── 14: Browse saved experiments ──
  console.log("14. Browse experiments");
  try {
    // Go back home
    const backBtn = page.getByRole("button", { name: /back/i }).first();
    if (await backBtn.isVisible().catch(() => false)) {
      await backBtn.click();
      await page.waitForTimeout(300);
    } else {
      await page.goto(BASE_URL, { waitUntil: "networkidle" });
    }
    // Click "Visualize Existing"
    await page.getByText("Visualize Existing").click();
    await page.waitForTimeout(500);
    await shot(page, "14-browse.png", "Experiment browser");
  } catch (e) {
    console.warn(`  ⚠ Step 14 failed: ${e.message}`);
  }

  // ── 15: Load a saved experiment and show simulation controls ──
  console.log("15. Simulation controls (loaded experiment)");
  try {
    // Click the first experiment card (demo-simple or similar)
    const cards = page.locator("button, [role='button'], a").filter({ hasText: /simple|demo/i });
    const cardCount = await cards.count();
    if (cardCount > 0) {
      await cards.first().click();
      await page.waitForTimeout(1500);
    }
    // Go to simulation tab
    const simBtn = page.getByRole("button", { name: /simulation/i }).first();
    if (await simBtn.isVisible().catch(() => false)) {
      await simBtn.click();
      await page.waitForTimeout(1000);
    }
    // Try to hit play briefly
    const playBtn = page.locator('button').filter({ hasText: /play|▶/i }).first();
    if (await playBtn.isVisible().catch(() => false)) {
      await playBtn.click();
      await page.waitForTimeout(800);
    }
    await shot(page, "15-simulation-controls.png", "Simulation playback controls");
  } catch (e) {
    console.warn(`  ⚠ Step 15 failed: ${e.message}`);
  }

  // ── 16: Overview of loaded experiment ──
  console.log("16. Loaded experiment overview");
  try {
    const overviewBtn = page.getByRole("button", { name: /overview/i }).first();
    if (await overviewBtn.isVisible().catch(() => false)) {
      await overviewBtn.click();
      await page.waitForTimeout(500);
    }
    await shot(page, "16-loaded-overview.png", "Overview of loaded saved experiment");
  } catch (e) {
    console.warn(`  ⚠ Step 16 failed: ${e.message}`);
  }

  await browser.close();
  console.log("\nDone! Screenshots saved to docs/screenshots/");
}

run().catch((err) => {
  console.error("Screenshot capture FAILED:", err.message);
  process.exit(1);
});
