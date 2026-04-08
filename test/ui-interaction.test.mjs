import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
};

async function createServer() {
  const server = http.createServer(async (req, res) => {
    const urlPath = req.url === '/' ? '/index.html' : req.url;
    const safePath = path.normalize(urlPath).replace(/^(\.\.[/\\])+/, '');
    const filePath = path.join(ROOT, safePath);

    try {
      const data = await fs.readFile(filePath);
      res.writeHead(200, {
        'Content-Type': MIME[path.extname(filePath)] || 'text/plain; charset=utf-8',
      });
      res.end(data);
    } catch {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('not found');
    }
  });

  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.once('listening', resolve);
    server.listen(0);
  });

  const address = server.address();
  return {
    server,
    port: typeof address === 'object' && address ? address.port : 0,
  };
}

async function withPage(run) {
  const { server, port } = await createServer();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

  try {
    await page.addInitScript(() => {
      const values = new Array(32).fill(0.5);
      Math.random = () => values.shift() ?? 0.5;
    });
    await page.goto(`http://127.0.0.1:${port}/index.html`, { waitUntil: 'domcontentloaded' });
    return await run(page);
  } finally {
    await browser.close();
    await new Promise((resolve, reject) => server.close((err) => (err ? reject(err) : resolve())));
  }
}

async function readPayload(page) {
  return page.evaluate(() => JSON.parse(window.render_game_to_text()));
}

async function settleShot(page, ms = 5000) {
  await page.evaluate(async (duration) => {
    await window.advanceTime(duration);
  }, ms);
  return readPayload(page);
}

async function waitForMode(page, expectedMode, timeoutMs = 2500, stepMs = 100) {
  let elapsed = 0;
  while (elapsed <= timeoutMs) {
    const payload = await readPayload(page);
    if (payload.mode === expectedMode) return payload;
    await page.evaluate(async (duration) => {
      await window.advanceTime(duration);
    }, stepMs);
    elapsed += stepMs;
  }
  return readPayload(page);
}

test('regression: launch button press-and-release fires one shot, shows result hold, then auto readies', async () => {
  const { resultPayload, readyPayload } = await withPage(async (page) => {
    await page.evaluate(async () => {
      const launch = document.getElementById('start-btn');
      launch.dispatchEvent(new PointerEvent('pointerdown', {
        bubbles: true,
        button: 0,
        buttons: 1,
        pointerId: 1,
        pointerType: 'mouse',
      }));
      await window.advanceTime(350);
      launch.dispatchEvent(new PointerEvent('pointerup', {
        bubbles: true,
        button: 0,
        buttons: 0,
        pointerId: 1,
        pointerType: 'mouse',
      }));
    });
    const resultPayload = await waitForMode(page, 'result', 7000, 250);
    const readyPayload = await waitForMode(page, 'ready', 6000, 250);
    return { resultPayload, readyPayload };
  });

  assert.equal(resultPayload.totalShots, 1);
  assert.equal(resultPayload.charging, false);
  assert.equal(resultPayload.mode, 'result');
  assert.ok(resultPayload.metrics.carry > 0);
  assert.ok(resultPayload.lastShotMetrics);
  assert.match(resultPayload.message, /결과를 확인하는 중입니다|다음 샷을 준비하세요/);

  assert.equal(readyPayload.mode, 'ready');
  assert.equal(readyPayload.charging, false);
  assert.ok(readyPayload.lastShotMetrics);
  assert.match(readyPayload.message, /다음 샷을 바로 이어서 실험할 수 있습니다|샷을 준비하세요/);
});

test('regression: launch button and space key produce equivalent shot metrics for the same hold duration', async () => {
  const launchPayload = await withPage(async (page) => {
    await page.evaluate(async () => {
      const launch = document.getElementById('start-btn');
      launch.dispatchEvent(new PointerEvent('pointerdown', {
        bubbles: true,
        button: 0,
        buttons: 1,
        pointerId: 1,
        pointerType: 'mouse',
      }));
      await window.advanceTime(300);
      launch.dispatchEvent(new PointerEvent('pointerup', {
        bubbles: true,
        button: 0,
        buttons: 0,
        pointerId: 1,
        pointerType: 'mouse',
      }));
    });
    await waitForMode(page, 'result', 7000, 250);
    return waitForMode(page, 'ready', 6000, 250);
  });

  const keyboardPayload = await withPage(async (page) => {
    await page.keyboard.down('Space');
    await page.evaluate(async () => {
      await window.advanceTime(300);
    });
    await page.keyboard.up('Space');
    await waitForMode(page, 'result', 7000, 250);
    return waitForMode(page, 'ready', 6000, 250);
  });

  assert.equal(launchPayload.totalShots, 1);
  assert.equal(keyboardPayload.totalShots, 1);
  assert.ok(launchPayload.lastShotMetrics);
  assert.ok(keyboardPayload.lastShotMetrics);
  assert.ok(Math.abs(launchPayload.lastShotMetrics.carry - keyboardPayload.lastShotMetrics.carry) < 1.0);
  assert.ok(Math.abs(launchPayload.lastShotMetrics.ballSpeedMph - keyboardPayload.lastShotMetrics.ballSpeedMph) < 0.01);
  assert.ok(Math.abs(launchPayload.lastShotMetrics.offline - keyboardPayload.lastShotMetrics.offline) < 0.2);
});
