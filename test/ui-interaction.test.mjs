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
    server.listen(0, '127.0.0.1');
  });

  const address = server.address();
  return {
    server,
    port: typeof address === 'object' && address ? address.port : 0,
  };
}

async function withPage(run, options = {}) {
  const { server, port } = await createServer();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: options.viewport ?? { width: 1280, height: 800 } });

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

async function getCanvasCenter(page) {
  const box = await page.locator('#game').boundingBox();
  assert.ok(box);
  return {
    x: box.x + box.width / 2,
    y: box.y + box.height / 2,
  };
}

async function readPayload(page) {
  return page.evaluate(() => JSON.parse(window.render_game_to_text()));
}

async function waitForMode(page, mode, maxMs = 15000) {
  let elapsed = 0;
  while (elapsed <= maxMs) {
    const payload = await readPayload(page);
    if (payload.mode === mode) return payload;
    await page.evaluate(async () => {
      await window.advanceTime(100);
    });
    elapsed += 100;
  }
  throw new Error(`timed out waiting for mode ${mode}`);
}

async function settleShot(page) {
  let elapsed = 0;
  while (elapsed <= 15000) {
    const payload = await readPayload(page);
    if (
      payload.currentShot &&
      !['launching', 'in_flight', 'rollout'].includes(payload.mode)
    ) {
      return payload;
    }
    await page.evaluate(async () => {
      await window.advanceTime(250);
    });
    elapsed += 250;
  }
  throw new Error('timed out waiting for settled shot');
}

async function triggerSpaceLaunch(page, repeat = false) {
  await dispatchKeyboard(page, { key: ' ', code: 'Space', repeat, type: 'keydown' });
}

async function dispatchKeyboard(page, {
  key,
  code,
  repeat = false,
  shiftKey = false,
  type = 'keydown',
}) {
  await page.evaluate((payload) => {
    window.dispatchEvent(new KeyboardEvent(payload.type, {
      key: payload.key,
      code: payload.code,
      bubbles: true,
      repeat: payload.repeat,
      shiftKey: payload.shiftKey,
    }));
  }, { key, code, repeat, shiftKey, type });
}

async function holdKeyboardCode(page, {
  key,
  code,
  durationMs,
}) {
  await dispatchKeyboard(page, { key, code, type: 'keydown' });
  await page.evaluate(async ({ duration }) => {
    await window.advanceTime(duration);
  }, { duration: durationMs });
  await dispatchKeyboard(page, { key, code, type: 'keyup' });
}

test('regression: launch button click fires one shot and enters the continuous loop state', async () => {
  const payload = await withPage(async (page) => {
    await page.click('#start-btn');
    return settleShot(page);
  });

  assert.equal(payload.totalShots, 1);
  assert.equal(payload.charging, false);
  assert.ok(['auto_reset_pending', 'session_ready'].includes(payload.mode));
  assert.equal(payload.cameraMode, 'follow');
  assert.ok(payload.metrics.carry > 0);
  assert.ok(payload.currentShot);
  assert.equal(payload.previousShot, null);
  assert.equal(payload.change, null);
  assert.ok(payload.currentShot.ballSpeed > 0);
  assert.match(payload.message, /현재 샷 품질과 변화를 확인하세요\. 2초 뒤 다음 샷을 준비합니다\.|다음 샷 준비 완료\. 지금 바로 다시 칠 수 있습니다\./);
});

test('regression: space keydown launches immediately without waiting for keyup', async () => {
  const payload = await withPage(async (page) => {
    await triggerSpaceLaunch(page);
    return readPayload(page);
  });

  assert.equal(payload.totalShots, 1);
  assert.equal(payload.mode, 'launching');
  assert.equal(payload.charging, false);
});

test('regression: repeated space keydown does not trigger duplicate launches', async () => {
  const payload = await withPage(async (page) => {
    await triggerSpaceLaunch(page, false);
    await triggerSpaceLaunch(page, true);
    await triggerSpaceLaunch(page, true);
    return settleShot(page);
  });

  assert.equal(payload.totalShots, 1);
  assert.ok(payload.currentShot);
});

test('regression: launch button click and space keydown produce equivalent shot metrics', async () => {
  const launchPayload = await withPage(async (page) => {
    await page.click('#start-btn');
    return settleShot(page);
  });

  const keyboardPayload = await withPage(async (page) => {
    await triggerSpaceLaunch(page);
    return settleShot(page);
  });

  assert.equal(launchPayload.totalShots, 1);
  assert.equal(keyboardPayload.totalShots, 1);
  assert.ok(Math.abs(launchPayload.currentShot.carry - keyboardPayload.currentShot.carry) < 1);
  assert.ok(Math.abs(launchPayload.currentShot.ballSpeed - keyboardPayload.currentShot.ballSpeed) < 0.01);
  assert.ok(Math.abs(launchPayload.currentShot.offline - keyboardPayload.currentShot.offline) < 0.5);
});

test('regression: camera hotkey cycles through all presets and shift+c reverses the order', async () => {
  const payload = await withPage(async (page) => {
    const initial = await readPayload(page);
    await dispatchKeyboard(page, { key: 'ㅊ', code: 'KeyC', type: 'keydown' });
    const fixedTee = await readPayload(page);
    const fixedNote = await page.textContent('#camera-mode-note');
    await dispatchKeyboard(page, { key: 'ㅊ', code: 'KeyC', type: 'keydown' });
    const follow = await readPayload(page);
    await dispatchKeyboard(page, { key: 'ㅊ', code: 'KeyC', type: 'keydown', shiftKey: true });
    const reverse = await readPayload(page);
    return { initial, fixedTee, fixedNote, follow, reverse };
  });

  assert.equal(payload.initial.cameraMode, 'follow');
  assert.equal(payload.fixedTee.cameraMode, 'fixed-tee');
  assert.equal(payload.follow.cameraMode, 'follow');
  assert.equal(payload.reverse.cameraMode, 'fixed-tee');
  assert.ok(Math.abs(payload.fixedTee.camera.position.x - payload.initial.camera.position.x) < 0.02);
  assert.ok(Math.abs(payload.fixedTee.camera.position.y - payload.initial.camera.position.y) < 0.02);
  assert.ok(Math.abs(payload.fixedTee.camera.position.z - payload.initial.camera.position.z) < 0.02);
  assert.ok(Math.abs(payload.fixedTee.camera.target.x - payload.initial.camera.target.x) < 0.02);
  assert.ok(Math.abs(payload.fixedTee.camera.target.y - payload.initial.camera.target.y) < 0.02);
  assert.match(payload.fixedNote, /티박스 고정 · 좌드래그 이동 · 우드래그 회전 · 휠 줌 · Esc/);
});

test('regression: each fixed camera preset stays anchored during ball flight', async () => {
  const presets = [
    {
      value: 'fixed-tee',
      position: { x: -16.9, y: 4.8, z: 0 },
      target: { x: 10, y: 1.25, z: 0 },
    },
  ];

  for (const preset of presets) {
    const payload = await withPage(async (page) => {
      await page.selectOption('#camera-mode', preset.value);
      const before = await readPayload(page);
      await page.click('#start-btn');
      const inFlight = await waitForMode(page, 'in_flight');
      await page.evaluate(async () => {
        await window.advanceTime(800);
      });
      const later = await readPayload(page);
      return { before, inFlight, later };
    });

    assert.equal(payload.before.cameraMode, preset.value);
    assert.equal(payload.inFlight.cameraMode, preset.value);
    assert.equal(payload.later.cameraMode, preset.value);
    assert.ok(Math.abs(payload.before.camera.position.x - preset.position.x) < 0.02);
    assert.ok(Math.abs(payload.before.camera.position.y - preset.position.y) < 0.02);
    assert.ok(Math.abs(payload.before.camera.position.z - preset.position.z) < 0.02);
    assert.ok(Math.abs(payload.before.camera.target.x - preset.target.x) < 0.02);
    assert.ok(Math.abs(payload.before.camera.target.y - preset.target.y) < 0.02);
    assert.ok(Math.abs(payload.before.camera.target.z - preset.target.z) < 0.02);
    assert.ok(Math.abs(payload.inFlight.camera.position.x - payload.before.camera.position.x) < 0.02);
    assert.ok(Math.abs(payload.inFlight.camera.position.y - payload.before.camera.position.y) < 0.02);
    assert.ok(Math.abs(payload.inFlight.camera.position.z - payload.before.camera.position.z) < 0.02);
    assert.ok(Math.abs(payload.later.camera.position.x - payload.before.camera.position.x) < 0.02);
    assert.ok(Math.abs(payload.later.camera.position.y - payload.before.camera.position.y) < 0.02);
    assert.ok(Math.abs(payload.later.camera.position.z - payload.before.camera.position.z) < 0.02);
  }
});

test('regression: selected camera preset persists after reload', async () => {
  const payload = await withPage(async (page) => {
    await page.selectOption('#camera-mode', 'fixed-tee');
    await page.reload({ waitUntil: 'domcontentloaded' });
    return {
      render: await readPayload(page),
      selected: await page.inputValue('#camera-mode'),
      note: await page.textContent('#camera-mode-note'),
    };
  });

  assert.equal(payload.render.cameraMode, 'fixed-tee');
  assert.equal(payload.selected, 'fixed-tee');
  assert.match(payload.note, /티박스 고정/);
});

test('regression: viewport stays within the current browser height without page scroll', async () => {
  const viewports = [
    { width: 1440, height: 900 },
    { width: 1280, height: 720 },
    { width: 1024, height: 768 },
  ];

  for (const viewport of viewports) {
    const metrics = await withPage(async (page) => {
      return page.evaluate(() => {
        const shell = document.getElementById('game-shell').getBoundingClientRect();
        const stage = document.getElementById('game-stage').getBoundingClientRect();
        return {
          bodyOverflow: getComputedStyle(document.body).overflowY,
          docClientHeight: document.documentElement.clientHeight,
          docScrollHeight: document.documentElement.scrollHeight,
          shellBottom: shell.bottom,
          stageBottom: stage.bottom,
          viewportHeight: window.innerHeight,
        };
      });
    }, { viewport });

    assert.equal(metrics.bodyOverflow, 'hidden');
    assert.ok(metrics.docScrollHeight <= metrics.docClientHeight + 1);
    assert.ok(metrics.shellBottom <= metrics.viewportHeight + 1);
    assert.ok(metrics.stageBottom <= metrics.viewportHeight + 1);
  }
});

test('regression: follow camera ignores mouse drag and wheel input', async () => {
  const payload = await withPage(async (page) => {
    const before = await readPayload(page);
    const center = await getCanvasCenter(page);
    await page.mouse.move(center.x, center.y);
    await page.mouse.down({ button: 'left' });
    await page.mouse.move(center.x + 140, center.y + 50);
    await page.mouse.up({ button: 'left' });
    await page.mouse.down({ button: 'right' });
    await page.mouse.move(center.x + 30, center.y - 80);
    await page.mouse.up({ button: 'right' });
    await page.mouse.wheel(0, 240);
    const after = await readPayload(page);
    return { before, after };
  });

  assert.equal(payload.before.camera.mode, 'follow');
  assert.equal(payload.after.camera.mode, 'follow');
  assert.equal(payload.after.camera.manualDirty, false);
  assert.ok(Math.abs(payload.after.camera.position.x - payload.before.camera.position.x) < 0.02);
  assert.ok(Math.abs(payload.after.camera.position.y - payload.before.camera.position.y) < 0.02);
  assert.ok(Math.abs(payload.after.camera.position.z - payload.before.camera.position.z) < 0.02);
  assert.ok(Math.abs(payload.after.camera.target.x - payload.before.camera.target.x) < 0.02);
  assert.ok(Math.abs(payload.after.camera.target.y - payload.before.camera.target.y) < 0.02);
  assert.ok(Math.abs(payload.after.camera.target.z - payload.before.camera.target.z) < 0.02);
});

test('regression: fixed tee camera supports pan orbit zoom and reset controls', async () => {
  const payload = await withPage(async (page) => {
    await page.selectOption('#camera-mode', 'fixed-tee');
    const center = await getCanvasCenter(page);
    const preset = await readPayload(page);

    await page.mouse.move(center.x, center.y);
    await page.mouse.down({ button: 'left' });
    await page.mouse.move(center.x + 120, center.y + 64);
    await page.mouse.up({ button: 'left' });
    const afterPan = await readPayload(page);

    await page.mouse.down({ button: 'right' });
    await page.mouse.move(center.x + 200, center.y - 26);
    await page.mouse.up({ button: 'right' });
    await page.mouse.wheel(0, -220);
    const afterOrbitZoom = await readPayload(page);
    const overlayVisible = await page.isVisible('#camera-overlay-controls');
    const overlayHint = await page.textContent('#camera-overlay-hint');

    await page.click('#camera-reset-overlay');
    const afterReset = await readPayload(page);
    return { preset, afterPan, afterOrbitZoom, afterReset, overlayVisible, overlayHint };
  });

  assert.equal(payload.preset.camera.mode, 'fixed-tee');
  assert.equal(payload.afterPan.camera.manualDirty, true);
  assert.notEqual(payload.afterPan.camera.position.x, payload.preset.camera.position.x);
  assert.notEqual(payload.afterPan.camera.target.z, payload.preset.camera.target.z);
  assert.notEqual(payload.afterOrbitZoom.camera.manual.distance, payload.afterPan.camera.manual.distance);
  assert.equal(payload.overlayVisible, true);
  assert.match(payload.overlayHint ?? '', /좌드래그 이동 · 우드래그 회전 · 휠 줌 · Esc 리셋/);
  assert.equal(payload.afterReset.camera.manualDirty, false);
  assert.ok(Math.abs(payload.afterReset.camera.position.x - payload.preset.camera.position.x) < 0.02);
  assert.ok(Math.abs(payload.afterReset.camera.position.y - payload.preset.camera.position.y) < 0.02);
  assert.ok(Math.abs(payload.afterReset.camera.position.z - payload.preset.camera.position.z) < 0.02);
});

test('regression: space still launches even when fixed tee camera has manual offsets', async () => {
  const payload = await withPage(async (page) => {
    await page.selectOption('#camera-mode', 'fixed-tee');
    const center = await getCanvasCenter(page);
    await page.mouse.move(center.x, center.y);
    await page.mouse.down({ button: 'left' });
    await page.mouse.move(center.x + 90, center.y + 40);
    await page.mouse.up({ button: 'left' });
    const beforeLaunch = await readPayload(page);
    await triggerSpaceLaunch(page);
    const launching = await readPayload(page);
    return { beforeLaunch, launching };
  });

  assert.equal(payload.beforeLaunch.camera.manualDirty, true);
  assert.equal(payload.launching.totalShots, 1);
  assert.equal(payload.launching.mode, 'launching');
  assert.equal(payload.launching.camera.mode, 'fixed-tee');
});

test('regression: camera hotkey returns fixed tee to its default preset when toggled back from follow', async () => {
  const payload = await withPage(async (page) => {
    await page.selectOption('#camera-mode', 'fixed-tee');
    const preset = await readPayload(page);
    const center = await getCanvasCenter(page);
    await page.mouse.move(center.x, center.y);
    await page.mouse.down({ button: 'left' });
    await page.mouse.move(center.x + 100, center.y + 30);
    await page.mouse.up({ button: 'left' });
    const dirty = await readPayload(page);
    await dispatchKeyboard(page, { key: 'ㅊ', code: 'KeyC', type: 'keydown' });
    const follow = await readPayload(page);
    await dispatchKeyboard(page, { key: 'ㅊ', code: 'KeyC', type: 'keydown' });
    const fixedAgain = await readPayload(page);
    return { preset, dirty, follow, fixedAgain };
  });

  assert.equal(payload.dirty.camera.manualDirty, true);
  assert.equal(payload.follow.camera.mode, 'follow');
  assert.equal(payload.fixedAgain.camera.mode, 'fixed-tee');
  assert.equal(payload.fixedAgain.camera.manualDirty, false);
  assert.ok(Math.abs(payload.fixedAgain.camera.position.x - payload.preset.camera.position.x) < 0.02);
  assert.ok(Math.abs(payload.fixedAgain.camera.position.y - payload.preset.camera.position.y) < 0.02);
  assert.ok(Math.abs(payload.fixedAgain.camera.position.z - payload.preset.camera.position.z) < 0.02);
});

test('regression: physical key hotkeys adjust camera, spin, ball speed, and yaw under non-latin key values', async () => {
  const payload = await withPage(async (page) => {
    await dispatchKeyboard(page, { key: 'ㅊ', code: 'KeyC', type: 'keydown' });
    const camera = await readPayload(page);

    await page.fill('#side-spin-rpm', '150');
    await dispatchKeyboard(page, { key: 'ㅂ', code: 'KeyQ', type: 'keydown' });
    const afterFirstLeftSpin = await page.inputValue('#side-spin-rpm');

    await dispatchKeyboard(page, { key: 'ㅂ', code: 'KeyQ', type: 'keydown' });
    const afterSecondLeftSpin = await page.inputValue('#side-spin-rpm');

    await dispatchKeyboard(page, { key: 'ㄷ', code: 'KeyE', type: 'keydown' });
    const afterRecoveringRightSpin = await page.inputValue('#side-spin-rpm');

    await dispatchKeyboard(page, { key: 'ㅈ', code: 'KeyW', type: 'keydown' });
    const faster = await page.inputValue('#ball-speed-mph');

    await dispatchKeyboard(page, { key: 'ㄴ', code: 'KeyS', type: 'keydown' });
    const slower = await page.inputValue('#ball-speed-mph');

    await page.fill('#back-spin-rpm', '2500');
    await dispatchKeyboard(page, { key: 'ㄱ', code: 'KeyR', type: 'keydown' });
    const moreBackspin = await page.inputValue('#back-spin-rpm');

    await dispatchKeyboard(page, { key: 'ㄹ', code: 'KeyF', type: 'keydown' });
    const lessBackspin = await page.inputValue('#back-spin-rpm');

    await holdKeyboardCode(page, { key: 'ㅁ', code: 'KeyA', durationMs: 400 });
    const afterLeftAim = await readPayload(page);

    await holdKeyboardCode(page, { key: 'ㅇ', code: 'KeyD', durationMs: 800 });
    const afterRightAim = await readPayload(page);

    return {
      camera,
      afterFirstLeftSpin,
      afterSecondLeftSpin,
      afterRecoveringRightSpin,
      faster,
      slower,
      moreBackspin,
      lessBackspin,
      afterLeftAim,
      afterRightAim,
    };
  });

  assert.equal(payload.camera.cameraMode, 'fixed-tee');
  assert.equal(payload.afterFirstLeftSpin, '100');
  assert.equal(payload.afterSecondLeftSpin, '50');
  assert.equal(payload.afterRecoveringRightSpin, '100');
  assert.equal(payload.faster, '151');
  assert.equal(payload.slower, '150');
  assert.equal(payload.moreBackspin, '2550');
  assert.equal(payload.lessBackspin, '2500');
  assert.ok(payload.afterLeftAim.yawDeg < 0);
  assert.ok(payload.afterRightAim.yawDeg > payload.afterLeftAim.yawDeg);
});

test('regression: current ball input card keeps a stable height across signed spin value changes', async () => {
  const payload = await withPage(async (page) => {
    const measure = async () => page.evaluate(() => {
      const summary = document.getElementById('session-last');
      const detail = document.getElementById('session-input-sidespin');
      return {
        height: summary.getBoundingClientRect().height,
        summaryText: summary.textContent,
        detailText: detail.textContent,
      };
    });

    await page.fill('#side-spin-rpm', '150');
    await page.waitForTimeout(80);
    const first = await measure();

    await page.fill('#side-spin-rpm', '200');
    await page.waitForTimeout(80);
    const second = await measure();

    await page.fill('#side-spin-rpm', '-50');
    await page.waitForTimeout(80);
    const third = await measure();

    await page.fill('#side-spin-rpm', '-100');
    await page.waitForTimeout(80);
    const fourth = await measure();

    return { first, second, third, fourth };
  });

  assert.equal(payload.first.height, payload.second.height);
  assert.equal(payload.second.height, payload.third.height);
  assert.equal(payload.third.height, payload.fourth.height);
  assert.match(payload.second.summaryText ?? '', /볼 150 mph · 세부값 보기/);
  assert.match(payload.second.detailText ?? '', /\+0200 rpm/);
  assert.match(payload.fourth.detailText ?? '', /-0100 rpm/);
});

test('regression: putter session transition exposes checklist guidance and advanced sensor link', async () => {
  const payload = await withPage(async (page) => {
    await page.selectOption('#session-mode', 'putter');
    await page.waitForTimeout(120);
    return page.evaluate(() => {
      const readDisplay = (id) => window.getComputedStyle(document.getElementById(id)).display;
      return {
        render: JSON.parse(window.render_game_to_text()),
        stageHeading: document.getElementById('game-stage-heading').textContent,
        hudHeading: document.getElementById('hud-panel-heading').textContent,
        controlHeading: document.getElementById('control-sidebar-heading').textContent,
        startLabel: document.getElementById('start-btn').textContent,
        modeNote: document.getElementById('session-mode-note').textContent,
        guideDisplay: readDisplay('putter-guide-card'),
        rangeInputDisplay: readDisplay('range-ball-input-card'),
        putterInputDisplay: readDisplay('putter-input-card'),
        putterMotionDisplay: readDisplay('putter-motion-card'),
        cameraRowDisplay: readDisplay('camera-mode-row'),
        advancedLinkDisplay: readDisplay('putter-advanced-link'),
        advancedLinkText: document.getElementById('putter-advanced-link').textContent,
        guideSummary: document.getElementById('putter-guide-summary').textContent,
        stepDistanceTitle: document.querySelector('#putter-step-distance .putter-step-title').textContent,
        stepInputTitle: document.querySelector('#putter-step-input .putter-step-title').textContent,
        stepResultTitle: document.querySelector('#putter-step-result .putter-step-title').textContent,
        inputKey: document.getElementById('session-input-ball-key').textContent,
        resultKey: document.getElementById('session-result-primary-key').textContent,
      };
    });
  });

  assert.equal(payload.render.sessionKind, 'putter');
  assert.equal(payload.stageHeading, '1. 퍼트 결과와 거리감 확인');
  assert.equal(payload.hudHeading, '2. 퍼트 결과');
  assert.equal(payload.controlHeading, '3. 퍼터 세팅과 가이드');
  assert.equal(payload.startLabel, '퍼트 실행');
  assert.match(payload.modeNote, /빠른 거리감 훈련이 기본/);
  assert.equal(payload.guideDisplay, 'block');
  assert.equal(payload.rangeInputDisplay, 'none');
  assert.equal(payload.putterInputDisplay, 'block');
  assert.equal(payload.putterMotionDisplay, 'block');
  assert.equal(payload.cameraRowDisplay, 'none');
  assert.match(payload.advancedLinkDisplay, /flex/);
  assert.equal(payload.advancedLinkText, '고급 센서 모드 열기');
  assert.match(payload.guideSummary, /거리감/);
  assert.equal(payload.stepDistanceTitle, '홀까지 거리 선택');
  assert.equal(payload.stepInputTitle, '수동 또는 모션 스트로크 준비');
  assert.equal(payload.stepResultTitle, '퍼트 실행과 결과 확인');
  assert.equal(payload.inputKey, '홀 거리');
  assert.equal(payload.resultKey, '남은 거리');
});

test('regression: last selected session kind is restored from localStorage on reload', async () => {
  const payload = await withPage(async (page) => {
    await page.selectOption('#session-mode', 'putter');
    await page.waitForTimeout(120);
    await page.reload({ waitUntil: 'domcontentloaded' });
    return {
      render: await readPayload(page),
      sessionModeValue: await page.inputValue('#session-mode'),
      startLabel: await page.textContent('#start-btn'),
    };
  });

  assert.equal(payload.render.sessionKind, 'putter');
  assert.equal(payload.sessionModeValue, 'putter');
  assert.equal(payload.startLabel, '퍼트 실행');
});

test('regression: left putter shortcut tab switches the main session into putter mode', async () => {
  const payload = await withPage(async (page) => {
    await page.click('#putter-shortcut-tab');
    await page.waitForTimeout(140);
    return page.evaluate(() => ({
      render: JSON.parse(window.render_game_to_text()),
      sessionModeValue: document.getElementById('session-mode').value,
      shortcutDisplay: window.getComputedStyle(document.getElementById('putter-shortcut-tab')).display,
      advancedLinkDisplay: window.getComputedStyle(document.getElementById('putter-advanced-link')).display,
      startLabel: document.getElementById('start-btn').textContent,
      controlHeading: document.getElementById('control-sidebar-heading').textContent,
    }));
  });

  assert.equal(payload.render.sessionKind, 'putter');
  assert.equal(payload.sessionModeValue, 'putter');
  assert.equal(payload.shortcutDisplay, 'none');
  assert.match(payload.advancedLinkDisplay, /flex/);
  assert.equal(payload.startLabel, '퍼트 실행');
  assert.equal(payload.controlHeading, '3. 퍼터 세팅과 가이드');
});

test('regression: render payload exposes canonical session contract for range and putter sessions', async () => {
  const rangePayload = await withPage(async (page) => readPayload(page));
  const putterPayload = await withPage(async (page) => {
    await page.selectOption('#session-mode', 'putter');
    await page.waitForTimeout(120);
    return readPayload(page);
  });

  assert.equal(rangePayload.sessionContract.version, 1);
  assert.equal(rangePayload.sessionContract.selection.currentKind, 'range');
  assert.equal(rangePayload.sessionContract.selection.storageKey, 'golfsim.sessionKind');
  assert.equal(rangePayload.sessionContract.input.kind, 'range');
  assert.equal(rangePayload.sessionContract.replay.recentShotCount, 0);

  assert.equal(putterPayload.sessionContract.selection.currentKind, 'putter');
  assert.equal(putterPayload.sessionContract.input.kind, 'putter');
  assert.equal(typeof putterPayload.sessionContract.input.holeDistanceM, 'number');
  assert.equal(putterPayload.sessionContract.transition.mode, putterPayload.mode);
});

test('regression: putter session prioritizes remaining distance in HUD and comparison copy', async () => {
  const payload = await withPage(async (page) => {
    await page.selectOption('#session-mode', 'putter');
    await page.waitForTimeout(120);
    await page.click('#start-btn');
    await settleShot(page);
    await page.evaluate(async () => {
      await window.advanceTime(2200);
    });
    await page.locator('#putt-distance-m').evaluate((input) => {
      input.value = '5.5';
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await page.click('#start-btn');
    const settled = await settleShot(page);
    return {
      render: settled,
      metricLabel1: await page.textContent('#hud-metric-label-1'),
      metricLabel2: await page.textContent('#hud-metric-label-2'),
      metricLabel3: await page.textContent('#hud-metric-label-3'),
      metricLabel4: await page.textContent('#hud-metric-label-4'),
      currentValue: await page.textContent('#comparison-current-value'),
      previousValue: await page.textContent('#comparison-previous-value'),
      summary: await page.textContent('#comparison-summary'),
      resultPrimary: await page.textContent('#session-result-primary'),
      resultSecondary: await page.textContent('#session-result-secondary'),
      resultTertiary: await page.textContent('#session-result-tertiary'),
    };
  });

  assert.equal(payload.render.sessionKind, 'putter');
  assert.match(payload.metricLabel1 ?? '', /남은 거리/);
  assert.match(payload.metricLabel2 ?? '', /굴러간 거리/);
  assert.match(payload.metricLabel3 ?? '', /라인 오차/);
  assert.match(payload.metricLabel4 ?? '', /스트로크 속도/);
  assert.match(payload.currentValue ?? '', /남은|홀 아웃/);
  assert.match(payload.previousValue ?? '', /남은|홀 아웃/);
  assert.match(payload.summary ?? '', /직전 퍼트 대비 남은 거리/);
  assert.match(payload.resultPrimary ?? '', /남은|홀 아웃/);
  assert.match(payload.resultSecondary ?? '', /롤/);
  assert.match(payload.resultTertiary ?? '', /라인/);
});

test('regression: compact layout folds both side panels until toggled open', async () => {
  const payload = await withPage(async (page) => {
    await page.setViewportSize({ width: 1080, height: 800 });
    await page.evaluate(() => window.dispatchEvent(new Event('resize')));
    await page.waitForTimeout(240);

    const initial = await page.evaluate(() => {
      const shell = document.getElementById('game-shell');
      const hud = document.getElementById('hud-panel').getBoundingClientRect();
      const control = document.getElementById('control-sidebar').getBoundingClientRect();
      return {
        compact: shell.dataset.compact,
        leftOpen: shell.dataset.leftOpen,
        rightOpen: shell.dataset.rightOpen,
        hudRight: hud.right,
        controlLeft: control.left,
        width: window.innerWidth,
      };
    });

    await page.click('#hud-toggle');
    await page.waitForTimeout(240);
    const afterHudOpen = await page.evaluate(() => {
      const shell = document.getElementById('game-shell');
      const hud = document.getElementById('hud-panel').getBoundingClientRect();
      return {
        leftOpen: shell.dataset.leftOpen,
        hudRight: hud.right,
        expanded: document.getElementById('hud-toggle').getAttribute('aria-expanded'),
      };
    });

    await page.click('#panel-scrim');
    await page.click('#control-toggle');
    await page.waitForTimeout(240);
    const afterControlOpen = await page.evaluate(() => {
      const shell = document.getElementById('game-shell');
      const control = document.getElementById('control-sidebar').getBoundingClientRect();
      return {
        rightOpen: shell.dataset.rightOpen,
        controlLeft: control.left,
        expanded: document.getElementById('control-toggle').getAttribute('aria-expanded'),
        width: window.innerWidth,
      };
    });

    return { initial, afterHudOpen, afterControlOpen };
  });

  assert.equal(payload.initial.compact, 'true');
  assert.equal(payload.initial.leftOpen, 'false');
  assert.equal(payload.initial.rightOpen, 'false');
  assert.ok(payload.initial.hudRight < 48);
  assert.ok(payload.initial.controlLeft > payload.initial.width - 48);
  assert.equal(payload.afterHudOpen.leftOpen, 'true');
  assert.equal(payload.afterHudOpen.expanded, 'true');
  assert.ok(payload.afterHudOpen.hudRight > 120);
  assert.equal(payload.afterControlOpen.rightOpen, 'true');
  assert.equal(payload.afterControlOpen.expanded, 'true');
  assert.ok(payload.afterControlOpen.controlLeft < payload.afterControlOpen.width - 120);
});

test('regression: pressing space during flight returns to tee-ready state immediately', async () => {
  const payload = await withPage(async (page) => {
    await page.click('#start-btn');
    await waitForMode(page, 'in_flight');
    await triggerSpaceLaunch(page);
    const interrupted = await readPayload(page);
    let completed = await readPayload(page);
    let elapsed = 0;
    while (elapsed <= 15000) {
      if (completed.currentShot && completed.detachedFlights.length === 0) break;
      await page.evaluate(async () => {
        await window.advanceTime(250);
      });
      completed = await readPayload(page);
      elapsed += 250;
    }
    return { interrupted, completed };
  });

  assert.equal(payload.interrupted.mode, 'session_ready');
  assert.equal(payload.interrupted.totalShots, 1);
  assert.equal(payload.interrupted.currentShot, null);
  assert.equal(payload.interrupted.ball.moving, false);
  assert.equal(payload.interrupted.detachedFlights.length, 1);
  assert.match(payload.interrupted.message, /이전 샷은 계속 비행 중이고, 다시 조준할 수 있습니다\./);
  assert.equal(payload.completed.detachedFlights.length, 0);
  assert.ok(payload.completed.currentShot);
  assert.equal(payload.completed.currentShot.shotNo, 1);
});

test('regression: in-flight payload exposes live distance and curve telemetry', async () => {
  const payload = await withPage(async (page) => {
    await page.fill('#side-spin-rpm', '900');
    await page.click('#start-btn');
    await waitForMode(page, 'in_flight');
    const early = await readPayload(page);
    await page.evaluate(async () => {
      await window.advanceTime(700);
    });
    const later = await readPayload(page);
    return { early, later };
  });

  assert.equal(payload.early.liveFlight.active, true);
  assert.equal(typeof payload.early.liveFlight.distanceMeters, 'number');
  assert.equal(typeof payload.early.liveFlight.curveMeters, 'number');
  assert.match(payload.early.liveFlight.summary, /거리 .*m · 커브 .*m/);
  assert.ok(payload.early.liveFlight.distanceMeters > 0);
  assert.ok(payload.later.liveFlight.distanceMeters > payload.early.liveFlight.distanceMeters);
  assert.notEqual(payload.later.liveFlight.curveDirection, undefined);
});

test('regression: settled shot exposes a landing marker in the render payload', async () => {
  const payload = await withPage(async (page) => {
    await page.click('#start-btn');
    return settleShot(page);
  });

  assert.ok(payload.currentShot);
  assert.ok(payload.currentShot.landing);
  assert.ok(Array.isArray(payload.currentShot.trajectory));
  assert.ok(payload.currentShot.trajectory.length > 5);
  assert.equal(typeof payload.currentShot.landing.x, 'number');
  assert.equal(typeof payload.currentShot.landing.z, 'number');
  assert.equal(payload.recentShots.length, 1);
  assert.equal(payload.recentShots[0].shotNo, payload.currentShot.shotNo);
  assert.ok(payload.currentShot.trajectory[0].x > 0.05);
});

test('regression: two settled shots populate current shot previous shot and change', async () => {
  const payload = await withPage(async (page) => {
    await page.click('#start-btn');
    await settleShot(page);
    await page.evaluate(async () => {
      await window.advanceTime(3200);
    });
    await page.evaluate(() => {
      const direction = document.getElementById('aim-direction');
      direction.value = '8';
      direction.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await triggerSpaceLaunch(page);
    return settleShot(page);
  });

  assert.equal(payload.totalShots, 2);
  assert.ok(payload.currentShot);
  assert.ok(payload.previousShot);
  assert.equal(payload.previousShot.shotNo, 1);
  assert.equal(payload.currentShot.shotNo, 2);
  assert.ok(payload.change);
  assert.match(payload.comparisonSummary, /직전 샷 대비 캐리/);
  assert.equal(payload.recentShots.length, 2);
  assert.equal(payload.recentShots[0].shotNo, 2);
  assert.equal(payload.recentShots[1].shotNo, 1);
  assert.ok(payload.recentShots[0].trajectory.length > 5);
});

test('regression: distance unit selector switches shot history cards between meters and yards', async () => {
  const payload = await withPage(async (page) => {
    await page.click('#start-btn');
    await settleShot(page);
    const metricInMeters = await page.textContent('#comparison-current-value');
    await page.selectOption('#distance-unit', 'yd');
    const metricInYards = await page.textContent('#comparison-current-value');
    return {
      metricInMeters,
      metricInYards,
      render: await readPayload(page),
    };
  });

  assert.match(payload.metricInMeters, /캐리 .*m/);
  assert.match(payload.metricInYards, /캐리 .*y/);
  assert.equal(payload.render.distanceUnit, 'yd');
});

test('regression: recent shot history keeps the latest seven landing points and trajectories', async () => {
  const payload = await withPage(async (page) => {
    for (let i = 0; i < 8; i += 1) {
      await page.evaluate(async ({ shotIndex }) => {
        const direction = document.getElementById('aim-direction');
        direction.value = String(-10 + shotIndex * 3);
        direction.dispatchEvent(new Event('input', { bubbles: true }));
        const speed = document.getElementById('ball-speed-mph');
        speed.value = String(145 + shotIndex);
        speed.dispatchEvent(new Event('input', { bubbles: true }));
        document.getElementById('start-btn').click();
      }, { shotIndex: i });
      await settleShot(page);
      await page.evaluate(async () => {
        await window.advanceTime(2400);
      });
    }
    return readPayload(page);
  });

  assert.equal(payload.totalShots, 8);
  assert.equal(payload.recentShots.length, 7);
  assert.equal(payload.recentShots[0].shotNo, 8);
  assert.equal(payload.recentShots.at(-1).shotNo, 2);
  for (const shot of payload.recentShots) {
    assert.ok(shot.landing);
    assert.ok(Array.isArray(shot.trajectory));
    assert.ok(shot.trajectory.length > 4);
  }
});

test('regression: successful shot keeps a 2-second auto ready window before returning to ready', async () => {
  const payload = await withPage(async (page) => {
    await page.click('#start-btn');
    const pending = await waitForMode(page, 'auto_reset_pending');
    await page.evaluate(async () => {
      await window.advanceTime(1000);
    });
    const stillPending = await readPayload(page);
    await page.evaluate(async () => {
      await window.advanceTime(1500);
    });
    const ready = await readPayload(page);
    return { pending, stillPending, ready };
  });

  assert.equal(payload.pending.mode, 'auto_reset_pending');
  assert.ok(payload.pending.session.autoResetTimer <= 2);
  assert.ok(payload.pending.session.autoResetTimer > 1.4);
  assert.equal(payload.stillPending.mode, 'auto_reset_pending');
  assert.ok(payload.stillPending.session.autoResetTimer < payload.pending.session.autoResetTimer);
  assert.ok(payload.stillPending.session.autoResetTimer > 0.5);
  assert.equal(payload.ready.mode, 'session_ready');
  assert.match(payload.ready.message, /다음 샷 준비 완료\. 지금 바로 다시 칠 수 있습니다\./);
});

test('regression: reset clears current shot previous shot and change state', async () => {
  const payload = await withPage(async (page) => {
    await page.click('#start-btn');
    await settleShot(page);
    await page.click('#reset-btn');
    return readPayload(page);
  });

  assert.equal(payload.totalShots, 0);
  assert.equal(payload.currentShot, null);
  assert.equal(payload.previousShot, null);
  assert.equal(payload.change, null);
  assert.match(payload.comparisonSummary, /아직 현재 샷이 없습니다/);
});
