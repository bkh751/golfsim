import test from 'node:test';
import assert from 'node:assert/strict';

import { createImpactContext, createImpactOutput } from '../impact-agent.js';
import { DEFAULT_PARAMS, createDefaultControls } from '../swing-model.js';
import { compareShotMetrics, suggestParameterUpdates } from '../fitting-agent.js';

test('impact agent produces a 3D initial ball state', () => {
  const output = createImpactOutput(
    createImpactContext({
      clubHeadSpeed: 52,
      attackAngleDeg: 3,
      ballPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 },
      impactQuality: 0.93,
    }),
    createDefaultControls({
      powerNorm: 0.82,
      aimDeg: 16,
      yawDeg: 5,
      strikeOffsetX: 0.08,
      strikeOffsetY: -0.03,
      faceAngleBias: 2.4,
      clubPathBias: -1.2,
    }),
    DEFAULT_PARAMS
  );

  assert.ok(output.ballSpeed > 0);
  assert.ok(output.launchElevationDeg > 0);
  assert.ok(output.launchAzimuthDeg > 0);
  assert.ok(Math.abs(output.initialBallState.velocity.z) > 0.01);
  assert.ok(output.spinRateRpm >= DEFAULT_PARAMS.spinMin);
});

test('impact agent honors manual ball speed and side spin overrides', () => {
  const output = createImpactOutput(
    createImpactContext({
      clubHeadSpeed: 52,
      attackAngleDeg: 1,
      ballPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 },
    }),
    createDefaultControls({
      powerNorm: 0.6,
      aimDeg: 14,
      yawDeg: 0,
      manualBallSpeedMps: 71.5,
      manualSideSpinRpm: -1450,
    }),
    DEFAULT_PARAMS
  );

  assert.equal(output.ballSpeed, 71.5);
  assert.equal(output.sidespinRpm, -1450);
  assert.ok(output.initialBallState.velocity.x > 0);
  assert.ok(output.spinAxisTiltDeg < 0);
});

test('impact agent honors manual backspin override', () => {
  const output = createImpactOutput(
    createImpactContext({
      clubHeadSpeed: 48,
      attackAngleDeg: 2,
      ballPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 },
    }),
    createDefaultControls({
      powerNorm: 0.55,
      aimDeg: 15,
      yawDeg: 0,
      manualBackspinRpm: 5100,
      manualSideSpinRpm: 600,
    }),
    DEFAULT_PARAMS
  );

  assert.equal(output.backspinRpm, 5100);
  assert.equal(output.sidespinRpm, 600);
  assert.ok(output.spinRateRpm >= 5100);
});

test('fitting agent compares measured vs simulated shots and suggests bounded updates', () => {
  const report = compareShotMetrics(
    [
      { carry: 182, apex: 28, offline: -3 },
      { carry: 177, apex: 25, offline: -1 },
    ],
    [
      { carry: 175, apex: 23, offline: 1 },
      { carry: 171, apex: 21, offline: 2 },
    ]
  );

  assert.equal(report.sampleCount, 2);
  assert.ok(report.meanCarryError > 0);
  assert.ok(report.meanApexError > 0);
  assert.ok(report.meanOfflineError < 0);

  const tuned = suggestParameterUpdates(DEFAULT_PARAMS, report);
  assert.notEqual(tuned.dragCoeff, DEFAULT_PARAMS.dragCoeff);
  assert.notEqual(tuned.magnusCoeff, DEFAULT_PARAMS.magnusCoeff);
  assert.notEqual(tuned.sideMagnusScale, DEFAULT_PARAMS.sideMagnusScale);
});
