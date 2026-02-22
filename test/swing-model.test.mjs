import test from 'node:test';
import assert from 'node:assert/strict';

import {
  DEFAULT_PARAMS,
  createInitialState,
  createDefaultControls,
  stepSwingModel,
} from '../swing-model.js';

function isFiniteNumber(v) {
  return typeof v === 'number' && Number.isFinite(v);
}

test('happy path: swing progresses to flight then rest with forward ball travel', () => {
  let state = createInitialState({ ballX: 110, ballY: 400 });
  const controls = createDefaultControls({
    initiateSwing: true,
    powerNorm: 0.78,
    tempoNorm: 0.9,
    aimDeg: 27,
    windX: 0,
    strikeOffset: 0,
  });

  let sawFlight = false;
  let didImpactCount = 0;
  let steps = 0;

  while (steps < 900) {
    state = stepSwingModel(state, controls, DEFAULT_PARAMS, 1 / 60);
    controls.initiateSwing = false;
    if (state.didImpact) {
      didImpactCount += 1;
    }
    if (state.phase === 'flight') sawFlight = true;
    if (sawFlight && state.phase === 'rest') break;
    steps += 1;
  }

  assert.equal(sawFlight, true);
  assert.equal(didImpactCount, 1);
  assert.equal(state.phase, 'rest');
  assert.equal(state.ballMoving, false);
  assert.ok(state.ballX > 110);
});

test('boundary: extreme control and dt values remain finite', () => {
  const state = createInitialState({ ballX: 110, ballY: 400 });
  const controls = createDefaultControls({
    initiateSwing: true,
    powerNorm: 99,
    tempoNorm: -5,
    aimDeg: 999,
    loftDeltaDeg: 999,
    strikeOffset: 999,
    windX: 999,
  });

  const next = stepSwingModel(state, controls, DEFAULT_PARAMS, 10);

  const keysToCheck = [
    'ballX', 'ballY', 'ballVx', 'ballVy',
    'thetaTorso', 'thetaArm', 'thetaClub',
    'omegaTorso', 'omegaArm', 'omegaClub',
    'clubHeadSpeed', 'attackAngleDeg', 'spinRpm',
  ];

  for (const key of keysToCheck) {
    assert.equal(isFiniteNumber(next[key]), true, `${key} should be finite`);
  }

  assert.ok(next.launchDeg >= 0 && next.launchDeg <= 90);
});

test('regression: without initiateSwing state remains idle', () => {
  let state = createInitialState({ ballX: 110, ballY: 400 });
  const controls = createDefaultControls({
    initiateSwing: false,
    powerNorm: 0.7,
    tempoNorm: 0.8,
    aimDeg: 20,
  });

  for (let i = 0; i < 180; i += 1) {
    state = stepSwingModel(state, controls, DEFAULT_PARAMS, 1 / 60);
  }

  assert.equal(state.phase, 'address');
  assert.equal(state.ballMoving, false);
  assert.equal(state.ballX, 110);
  assert.equal(state.ballY, 400);
  assert.equal(state.didImpact, false);
});
