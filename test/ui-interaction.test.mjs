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

async function settleShot(page) {
  await page.evaluate(async () => {
    await window.advanceTime(5000);
  });
  return readPayload(page);
}

test('regression: launch button press-and-release fires one shot and enters the continuous loop state', async () => {
  const payload = await withPage(async (page) => {
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
    return settleShot(page);
  });

  assert.equal(payload.totalShots, 1);
  assert.equal(payload.charging, false);
  assert.ok(['auto_reset_pending', 'session_ready'].includes(payload.mode));
  assert.ok(payload.metrics.carry > 0);
  assert.ok(payload.lastShot);
  assert.ok(payload.lastShot.ballSpeed > 0);
  assert.match(payload.message, /이어집니다|다음 샷을 준비하세요/);
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
    return settleShot(page);
  });

  const keyboardPayload = await withPage(async (page) => {
    await page.keyboard.down('Space');
    await page.evaluate(async () => {
      await window.advanceTime(300);
    });
    await page.keyboard.up('Space');
    return settleShot(page);
  });

  assert.equal(launchPayload.totalShots, 1);
  assert.equal(keyboardPayload.totalShots, 1);
  assert.ok(Math.abs(launchPayload.lastShot.carry - keyboardPayload.lastShot.carry) < 1);
  assert.ok(Math.abs(launchPayload.lastShot.ballSpeed - keyboardPayload.lastShot.ballSpeed) < 0.01);
  assert.ok(Math.abs(launchPayload.lastShot.offline - keyboardPayload.lastShot.offline) < 0.1);
});
