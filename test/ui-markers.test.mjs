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
  assert.match(src, /SESSION HUD/);
  assert.match(src, /Range Session View/);
  assert.match(src, /Ball Control/);
  assert.match(src, /Aim Direction/);
  assert.match(src, /Ball Parameters/);
  assert.match(src, /캐리 \(Carry\)/);
  assert.match(src, /총거리 \(Total\)/);
  assert.match(src, /좌우 편차 \(Offline\)/);
  assert.match(src, /볼 스피드 \(Ball Speed\)/);
  assert.match(src, /백스핀 \(Backspin\)/);
  assert.match(src, /사이드스핀 \(Sidespin\)/);
  assert.match(src, /Ball Speed \(mph\)/);
  assert.match(src, /Side Spin \(rpm\)/);
  assert.match(src, /Back Spin \(rpm\)/);
  assert.match(src, /HOLD TO SWING/);
  assert.match(src, /NEW SESSION/);
});

test('regression: result panel metric order follows primary then secondary hierarchy', () => {
  const src = fs.readFileSync(INDEX_PATH, 'utf8');
  const carryIndex = src.indexOf('캐리 (Carry)');
  const totalIndex = src.indexOf('총거리 (Total)');
  const offlineIndex = src.indexOf('좌우 편차 (Offline)');
  const ballSpeedIndex = src.indexOf('볼 스피드 (Ball Speed)');
  const backspinIndex = src.indexOf('백스핀 (Backspin)');
  const sidespinIndex = src.indexOf('사이드스핀 (Sidespin)');

  assert.ok(carryIndex >= 0);
  assert.ok(totalIndex > carryIndex);
  assert.ok(offlineIndex > totalIndex);
  assert.ok(ballSpeedIndex > offlineIndex);
  assert.ok(backspinIndex > ballSpeedIndex);
  assert.ok(sidespinIndex > backspinIndex);
});

test('regression: figma main layout hooks and state copy rules should exist', () => {
  const src = fs.readFileSync(INDEX_PATH, 'utf8');
  assert.match(src, /id="hud-carry"/);
  assert.match(src, /id="hud-total"/);
  assert.match(src, /id="hud-offline"/);
  assert.match(src, /id="hud-side-spin"/);
  assert.match(src, /id="hud-back-spin"/);
  assert.match(src, /id="hud-ball-speed"/);
  assert.match(src, /id="session-state"/);
  assert.match(src, /id="game-viewport"/);
  assert.match(src, /id="aim-direction"/);
  assert.match(src, /function updateChrome/);
  assert.match(src, /function formatHudStatus/);
  assert.match(src, /function beginLaunchCharge/);
  assert.match(src, /function releaseLaunchCharge/);
  assert.match(src, /formatWindDirection/);
  assert.match(src, /샷을 준비하세요/);
  assert.match(src, /탄도를 관찰하세요/);
  assert.match(src, /볼 정지/);
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
