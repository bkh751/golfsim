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
  assert.match(src, /2\. 최신 확정 결과/);
  assert.match(src, /1\. 현재 입력값 확인과 비행 추적/);
  assert.match(src, /3\. 현재 입력값 조정/);
  assert.match(src, /현재 방향 입력값/);
  assert.match(src, /현재 볼 입력값/);
  assert.match(src, /비교 기준 없음/);
  assert.match(src, /현재 상태/);
  assert.match(src, /최신 결과 기준/);
  assert.match(src, /지금 조정한 값은 다음 실행에 반영됩니다\./);
  assert.match(src, /현재 방향 입력값은 기본값이고, 현재 볼 입력값은 입력창 값이 적용됩니다\./);
  assert.match(src, /현재 입력값이 직전 확정 실행 기준과 일치합니다\./);
  assert.match(src, /현재 입력값 중 직전 확정 실행과 다른 항목:/);
  assert.match(src, /\(변경됨\)/);
  assert.match(src, /보조 지표/);
  assert.match(src, /캐리 \(Carry\)/);
  assert.match(src, /총거리 \(Total\)/);
  assert.match(src, /좌우 편차 \(Offline\)/);
  assert.match(src, /볼 스피드 \(Ball Speed\)/);
  assert.match(src, /백스핀 \(Backspin\)/);
  assert.match(src, /사이드스핀 \(Sidespin\)/);
  assert.match(src, /볼 스피드 \(mph\)/);
  assert.match(src, /사이드스핀 \(rpm\)/);
  assert.match(src, /백스핀 \(rpm\)/);
  assert.match(src, /길게 눌러 실행/);
  assert.match(src, /실험 조건 초기화/);
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

test('regression: auto ready 3 seconds and visible result carry-over markers should exist', () => {
  const src = fs.readFileSync(INDEX_PATH, 'utf8');
  assert.match(src, /autoResetTimer = 3/);
  assert.match(src, /다음 샷을 바로 이어서 실험할 수 있습니다/);
  assert.match(src, /결과를 확인하는 중입니다/);
  assert.match(src, /function getVisibleResultMetrics/);
});

test('regression: figma main layout hooks and state copy rules should exist', () => {
  const src = fs.readFileSync(INDEX_PATH, 'utf8');
  assert.match(src, /id="hud-carry"/);
  assert.match(src, /id="hud-total"/);
  assert.match(src, /id="hud-offline"/);
  assert.match(src, /id="hud-ball-speed-primary"/);
  assert.match(src, /id="hud-side-spin"/);
  assert.match(src, /id="hud-back-spin"/);
  assert.match(src, /id="session-state"/);
  assert.match(src, /id="game-viewport"/);
  assert.match(src, /id="aim-direction"/);
  assert.match(src, /function updateChrome/);
  assert.match(src, /function formatHudStatus/);
  assert.match(src, /function beginLaunchCharge/);
  assert.match(src, /function releaseLaunchCharge/);
  assert.match(src, /function formatBallInputSummary/);
  assert.match(src, /function formatRecentFlightSummary/);
  assert.match(src, /function snapshotCurrentInputs/);
  assert.match(src, /function sameNullableNumber/);
  assert.match(src, /function hasPendingInputChanges/);
  assert.match(src, /function getChangedInputKeys/);
  assert.match(src, /function formatChangedInputSummary/);
  assert.match(src, /function formatInputHeading/);
  assert.match(src, /function currentResultReferenceKind/);
  assert.match(src, /function formatResultReferenceLabel/);
  assert.match(src, /function formatCurrentStateSummary/);
  assert.match(src, /function formatResultStatusNote/);
  assert.match(src, /function formatNextActionHint/);
  assert.match(src, /formatWindDirection/);
  assert.match(src, /먼저 캐리, 총거리, 좌우 편차를 확인하세요\./);
  assert.match(src, /핵심 결과를 해석할 때 스핀 지표를 함께 참고하세요\./);
  assert.match(src, /샷을 준비하세요/);
  assert.match(src, /발사 강도를 유지한 뒤 놓으세요/);
  assert.match(src, /샷 데이터를 수집 중입니다/);
  assert.match(src, /탄도를 관찰하세요/);
  assert.match(src, /결과를 확인하는 중입니다/);
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
