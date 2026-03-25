import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const INDEX_PATH = path.resolve(__dirname, '../index.html');

test('happy path: index exports game rendering pipeline markers', () => {
  const src = fs.readFileSync(INDEX_PATH, 'utf8');
  assert.match(src, /drawGolfer/);
  assert.match(src, /worldToScreen/);
  assert.match(src, /render_game_to_text/);
  assert.match(src, /function drawEnvironment/);
  assert.match(src, /projectWorldToScreen/);
  assert.match(src, /buildFlightCamera/);
  assert.match(src, /sampleTrajectoryPreview/);
});

test('boundary: 3rd-person UI keywords should exist', () => {
  const src = fs.readFileSync(INDEX_PATH, 'utf8');
  assert.match(src, /HUD \(데이터\)/);
  assert.match(src, /Ball Flight View/);
  assert.match(src, /Ball Control/);
  assert.match(src, /Aim Direction/);
  assert.match(src, /Ball Parameters/);
  assert.match(src, /Distance/);
  assert.match(src, /Wind/);
  assert.match(src, /Side Spin/);
  assert.match(src, /Back Spin/);
  assert.match(src, /Ball Speed/);
  assert.match(src, /Ball Speed \(mph\)/);
  assert.match(src, /Side Spin \(rpm\)/);
  assert.match(src, /Back Spin \(rpm\)/);
  assert.match(src, /LAUNCH/);
  assert.match(src, /Reset/);
});

test('regression: figma main layout hooks and state copy rules should exist', () => {
  const src = fs.readFileSync(INDEX_PATH, 'utf8');
  assert.match(src, /id="hud-distance"/);
  assert.match(src, /id="hud-wind"/);
  assert.match(src, /id="hud-side-spin"/);
  assert.match(src, /id="hud-back-spin"/);
  assert.match(src, /id="hud-ball-speed"/);
  assert.match(src, /id="game-viewport"/);
  assert.match(src, /id="aim-direction"/);
  assert.match(src, /function updateChrome/);
  assert.match(src, /function beginLaunchCharge/);
  assert.match(src, /function releaseLaunchCharge/);
  assert.match(src, /formatWindDirection/);
  assert.match(src, /샷을 준비하세요/);
  assert.match(src, /샷 추적 중/);
  assert.match(src, /샷 결과/);
  assert.match(src, /다음 샷을 준비하세요/);
});

test('regression: render payload still includes impact markers', () => {
  const src = fs.readFileSync(INDEX_PATH, 'utf8');
  assert.match(src, /didImpact:\s*state\.model\.didImpact/);
  assert.match(src, /impactEffectCount:\s*state\.impactEffects\.length/);
  assert.match(src, /ball:\s*\{\s*position:/s);
  assert.match(src, /metrics:\s*\{\s*carry:/s);
  assert.match(src, /launchAzimuthDeg/);
  assert.match(src, /mode:\s*state\.mode/);
});
