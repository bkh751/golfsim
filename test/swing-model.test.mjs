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
  let state = createInitialState({ ballPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 } });
  const controls = createDefaultControls({
    initiateSwing: true,
    powerNorm: 0.78,
    tempoNorm: 0.9,
    aimDeg: 27,
    yawDeg: 4,
    windX: 0,
    windZ: 0,
    strikeOffsetX: 0,
    strikeOffsetY: 0,
  });

  let sawFlight = false;
  let didImpactCount = 0;
  let steps = 0;

  while (steps < 2400) {
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
  assert.ok(state.ballPos.x > 0);
  assert.ok(Number.isFinite(state.ballPos.z));
  assert.ok(state.totalDistance >= state.carryDistance);
  assert.ok(state.apexHeight > DEFAULT_PARAMS.ballRadius);
});

test('boundary: extreme control and dt values remain finite', () => {
  const state = createInitialState({ ballPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 } });
  const controls = createDefaultControls({
    initiateSwing: true,
    powerNorm: 99,
    tempoNorm: -5,
    aimDeg: 999,
    yawDeg: 999,
    loftDeltaDeg: 999,
    strikeOffsetX: 999,
    strikeOffsetY: 999,
    faceAngleBias: 999,
    clubPathBias: -999,
    windX: 999,
    windZ: -999,
  });

  const next = stepSwingModel(state, controls, DEFAULT_PARAMS, 10);

  const keysToCheck = [
    'ballX', 'ballY', 'ballZ', 'ballVx', 'ballVy', 'ballVz',
    'thetaTorso', 'thetaArm', 'thetaClub',
    'omegaTorso', 'omegaArm', 'omegaClub',
    'clubHeadSpeed', 'attackAngleDeg', 'spinRpm',
    'launchAzimuthDeg', 'carryDistance', 'totalDistance', 'offlineDistance', 'apexHeight',
  ];

  for (const key of keysToCheck) {
    assert.equal(isFiniteNumber(next[key]), true, `${key} should be finite`);
  }

  assert.ok(next.launchDeg >= 0 && next.launchDeg <= 90);
  assert.ok(next.launchAzimuthDeg >= -35 && next.launchAzimuthDeg <= 35);
});

test('regression: without initiateSwing state remains idle', () => {
  let state = createInitialState({ ballPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 } });
  const controls = createDefaultControls({
    initiateSwing: false,
    powerNorm: 0.7,
    tempoNorm: 0.8,
    aimDeg: 20,
    yawDeg: 8,
  });

  for (let i = 0; i < 180; i += 1) {
    state = stepSwingModel(state, controls, DEFAULT_PARAMS, 1 / 60);
  }

  assert.equal(state.phase, 'address');
  assert.equal(state.ballMoving, false);
  assert.equal(state.ballPos.x, 0);
  assert.equal(state.ballPos.y, DEFAULT_PARAMS.ballRadius);
  assert.equal(state.ballPos.z, 0);
  assert.equal(state.didImpact, false);
});

test('regression: higher spin produces a higher apex and longer carry at matched speed', () => {
  const baseState = createInitialState({
    phase: 'flight',
    ballMoving: true,
    ballPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 },
    ballVel: { x: 62, y: 22, z: 0 },
    launchPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 },
    ballSpeed: 66,
    spinRateRpm: 2200,
    backspinRpm: 2200,
    sidespinRpm: 0,
    spinAxisTiltDeg: 0,
    launchDeg: 18,
  });

  function settle(state) {
    let next = state;
    for (let i = 0; i < 1200; i += 1) {
      next = stepSwingModel(next, createDefaultControls(), DEFAULT_PARAMS, 1 / 60);
      if (next.phase === 'rest') return next;
    }
    return next;
  }

  const lowSpin = settle(baseState);
  const highSpin = settle({ ...baseState, spinRateRpm: 5200, backspinRpm: 5200 });

  assert.ok(highSpin.apexHeight > lowSpin.apexHeight);
  assert.ok(highSpin.carryDistance > lowSpin.carryDistance);
});

test('regression: spin axis tilt and crosswind move the ball offline', () => {
  const settle = (controls) => {
    let next = createInitialState({ ballPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 } });
    let currentControls = createDefaultControls({ initiateSwing: true, powerNorm: 0.82, tempoNorm: 0.9, aimDeg: 18, ...controls });
    for (let i = 0; i < 1200; i += 1) {
      next = stepSwingModel(next, currentControls, DEFAULT_PARAMS, 1 / 60);
      currentControls.initiateSwing = false;
      if (next.phase === 'rest') return next;
    }
    return next;
  };

  const drawShot = settle({ yawDeg: 0, faceAngleBias: 5, clubPathBias: -4, windZ: 0 });
  const fadeShot = settle({ yawDeg: 0, faceAngleBias: -5, clubPathBias: 4, windZ: 0 });
  const windyShot = settle({ yawDeg: 0, windZ: 8 });

  assert.ok(drawShot.offlineDistance > 0);
  assert.ok(fadeShot.offlineDistance < 0);
  assert.ok(Math.abs(windyShot.offlineDistance) > 0.5);
});

test('regression: higher power creates a meaningfully longer shot', () => {
  const settle = (powerNorm) => {
    let next = createInitialState({ ballPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 } });
    let currentControls = createDefaultControls({
      initiateSwing: true,
      powerNorm,
      tempoNorm: Math.min(1.25, 0.62 + powerNorm * 0.55),
      aimDeg: 15,
      yawDeg: 0,
      windX: 0,
      windZ: 0,
      strikeOffsetX: (0.52 - powerNorm) * 0.12,
      strikeOffsetY: (0.74 - powerNorm) * 0.08,
      faceAngleBias: ((0.52 - powerNorm) * 0.12) * 16,
      clubPathBias: 0,
    });
    for (let i = 0; i < 2000; i += 1) {
      next = stepSwingModel(next, currentControls, DEFAULT_PARAMS, 1 / 60);
      currentControls.initiateSwing = false;
      if (next.phase === 'rest') return next;
    }
    return next;
  };

  const softShot = settle(0.2);
  const fullShot = settle(0.6);

  assert.ok(fullShot.carryDistance > softShot.carryDistance + 120);
  assert.ok(fullShot.totalDistance > softShot.totalDistance + 150);
  assert.ok(fullShot.apexHeight > softShot.apexHeight);
});

test('regression: manual ball inputs use the requested launch window directly', () => {
  let state = createInitialState({ ballPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 } });
  let controls = createDefaultControls({
    initiateSwing: true,
    powerNorm: 0.68,
    tempoNorm: 0.9,
    aimDeg: 10.4,
    yawDeg: 0,
    manualBallSpeedMps: 150 * 0.44704,
    manualBackspinRpm: 2500,
    manualSideSpinRpm: 0,
  });

  for (let i = 0; i < 2000; i += 1) {
    state = stepSwingModel(state, controls, DEFAULT_PARAMS, 1 / 60);
    controls.initiateSwing = false;
    if (state.phase === 'rest') break;
  }

  assert.ok(Math.abs(state.launchDeg - 10.4) < 0.25, `launchDeg=${state.launchDeg}`);
  const carryYards = state.carryDistance * 1.09361;
  assert.ok(carryYards > 235 && carryYards < 245, `carry=${carryYards.toFixed(1)} yd`);
});

test('regression: slower manual ball speed stays materially shorter than the tour-average benchmark', () => {
  const settleManual = (ballSpeedMph) => {
    let state = createInitialState({ ballPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 } });
    let controls = createDefaultControls({
      initiateSwing: true,
      powerNorm: 0.68,
      tempoNorm: 0.9,
      aimDeg: 10.4,
      yawDeg: 0,
      manualBallSpeedMps: ballSpeedMph * 0.44704,
      manualBackspinRpm: ballSpeedMph >= 170 ? 2545 : 2500,
      manualSideSpinRpm: 0,
    });
    for (let i = 0; i < 2400; i += 1) {
      state = stepSwingModel(state, controls, DEFAULT_PARAMS, 1 / 60);
      controls.initiateSwing = false;
      if (state.phase === 'rest') return state;
    }
    return state;
  };

  const slower = settleManual(150);
  const tour = settleManual(171);

  assert.ok(tour.carryDistance > slower.carryDistance + 35);
  assert.ok(tour.totalDistance > slower.totalDistance + 40);
});
