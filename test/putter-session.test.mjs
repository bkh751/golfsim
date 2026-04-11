import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".css": "text/css; charset=utf-8",
};

async function createServer() {
  const server = http.createServer(async (req, res) => {
    const urlPath = req.url === "/" ? "/putter-session.html" : req.url;
    const safePath = path.normalize(urlPath).replace(/^(\.\.[/\\])+/, "");
    const filePath = path.join(ROOT, safePath);

    try {
      const data = await fs.readFile(filePath);
      res.writeHead(200, {
        "Content-Type": MIME[path.extname(filePath)] || "text/plain; charset=utf-8",
      });
      res.end(data);
    } catch {
      res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
      res.end("not found");
    }
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.once("listening", resolve);
    server.listen(0, "127.0.0.1");
  });

  const address = server.address();
  return {
    server,
    port: typeof address === "object" && address ? address.port : 0,
  };
}

async function withPage(run) {
  const { server, port } = await createServer();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 900, height: 1200 } });

  try {
    await page.goto(`http://127.0.0.1:${port}/putter-session.html`, { waitUntil: "domcontentloaded" });
    return await run(page);
  } finally {
    await browser.close();
    await new Promise((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())));
  }
}

async function readPayload(page) {
  return page.evaluate(() => JSON.parse(window.render_putter_session_to_text()));
}

test("manual fallback putt produces a deterministic result", async () => {
  const payload = await withPage(async (page) => {
    await page.locator("#manual-power").evaluate((input, value) => {
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }, "64");
    await page.click("#manual-putt");
    await page.evaluate(async () => {
      await window.advance_putter_time(2200);
    });
    return readPayload(page);
  });

  assert.equal(payload.strokeCount, 1);
  assert.equal(payload.lastResult.analysis.source, "manual");
  assert.ok(Math.abs(payload.lastResult.simulation.stopDistanceM) > 0.2);
});

test("synthetic sensor stroke path produces a sensor-sourced putt", async () => {
  const payload = await withPage(async (page) => {
    await page.evaluate(() => {
      window.putterDebug.forceSensorReady();
      window.putterDebug.armStrokeCapture();
      const samples = [
        { timestamp: 0, forward: 0.08, lateral: 0.01, twist: 0.1, magnitude: 0.08 },
        { timestamp: 16, forward: 0.26, lateral: 0.02, twist: 0.16, magnitude: 0.26 },
        { timestamp: 32, forward: 0.72, lateral: 0.04, twist: 0.28, magnitude: 0.73 },
        { timestamp: 48, forward: 1.22, lateral: 0.06, twist: 0.42, magnitude: 1.23 },
        { timestamp: 64, forward: 0.86, lateral: 0.04, twist: 0.35, magnitude: 0.87 },
        { timestamp: 80, forward: 0.36, lateral: 0.01, twist: 0.14, magnitude: 0.36 },
        { timestamp: 96, forward: 0.09, lateral: 0.01, twist: 0.08, magnitude: 0.1 },
        { timestamp: 224, forward: 0.04, lateral: 0.0, twist: 0.04, magnitude: 0.04 },
        { timestamp: 416, forward: 0.03, lateral: 0.0, twist: 0.02, magnitude: 0.03 },
      ];
      samples.forEach((sample) => window.feed_putter_motion(sample));
    });
    await page.evaluate(async () => {
      await window.advance_putter_time(2200);
    });
    return readPayload(page);
  });

  assert.equal(payload.strokeCount, 1);
  assert.equal(payload.lastResult.analysis.source, "sensor");
  assert.equal(payload.sensor.lastStroke.valid, true);
  assert.ok(payload.lastResult.analysis.ballSpeedMps > 0.3);
});
