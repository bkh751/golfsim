import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

import { createFlightState, stepFlightState } from '../flight-engine.js';
import { computeAeroCoefficients } from '../aero-model.js';
import { DEFAULT_PARAMS } from '../swing-model.js';

const MATRIX_PATH = new URL('./fixtures/flight-benchmark-matrix.json', import.meta.url);

function mphToMps(mph) {
  return mph * 0.44704;
}

function fpsToMps(fps) {
  return fps * 0.3048;
}

function toYards(meters) {
  return meters * 1.09361;
}

function inWindow(value, window) {
  if (!window) return true;
  if (Number.isFinite(window.min) && value < window.min) return false;
  if (Number.isFinite(window.max) && value > window.max) return false;
  return true;
}

function simulateBenchmark(entry) {
  const speedMps = Number.isFinite(entry.inputs.speedMph)
    ? mphToMps(entry.inputs.speedMph)
    : fpsToMps(entry.inputs.speedFps);
  const launchRad = entry.inputs.launchDeg * Math.PI / 180;

  let state = createFlightState({
    position: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 },
    velocity: {
      x: speedMps * Math.cos(launchRad),
      y: speedMps * Math.sin(launchRad),
      z: 0,
    },
    spinRateRpm: entry.inputs.backspinRpm,
    spinAxisTiltDeg: 0,
    backspinRpm: entry.inputs.backspinRpm,
    sidespinRpm: 0,
    moving: true,
    launchDeg: entry.inputs.launchDeg,
    launchPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 },
    landingPos: { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 },
    apexHeight: DEFAULT_PARAMS.ballRadius,
  });

  for (let i = 0; i < 8000 && state.moving; i += 1) {
    state = stepFlightState(
      state,
      { wind: { x: 0, y: 0, z: 0 }, airDensity: 1 },
      DEFAULT_PARAMS,
      1 / 240
    );
  }

  return {
    carryYards: toYards(state.carryDistance),
    totalYards: toYards(state.totalDistance),
  };
}

test('benchmark matrix stays inside documented carry and total windows', async () => {
  const matrix = JSON.parse(await fs.readFile(MATRIX_PATH, 'utf8'));

  for (const entry of matrix) {
    const actual = simulateBenchmark(entry);
    assert.ok(
      inWindow(actual.carryYards, entry.expected.carryYards),
      `${entry.id} carry=${actual.carryYards.toFixed(1)} yd`
    );
    assert.ok(
      inWindow(actual.totalYards, entry.expected.totalYards),
      `${entry.id} total=${actual.totalYards.toFixed(1)} yd`
    );
  }
});

test('aero model uses dynamic spin decay and climb-aware drag in driver windows', () => {
  const lowSpeed = computeAeroCoefficients(
    {
      velocity: { x: mphToMps(150), y: 0, z: 0 },
      spinRateRpm: 2500,
      spinAxisTiltDeg: 0,
      launchDeg: 10.4,
    },
    { wind: { x: 0, y: 0, z: 0 }, airDensity: 1 },
    DEFAULT_PARAMS
  );
  const highSpeed = computeAeroCoefficients(
    {
      velocity: { x: mphToMps(171), y: 0, z: 0 },
      spinRateRpm: 2500,
      spinAxisTiltDeg: 0,
      launchDeg: 10.4,
    },
    { wind: { x: 0, y: 0, z: 0 }, airDensity: 1 },
    DEFAULT_PARAMS
  );
  const flatter = computeAeroCoefficients(
    {
      velocity: { x: mphToMps(150) * Math.cos(10.4 * Math.PI / 180), y: mphToMps(150) * Math.sin(10.4 * Math.PI / 180), z: 0 },
      spinRateRpm: 2500,
      spinAxisTiltDeg: 0,
      launchDeg: 10.4,
    },
    { wind: { x: 0, y: 0, z: 0 }, airDensity: 1 },
    DEFAULT_PARAMS
  );
  const steeper = computeAeroCoefficients(
    {
      velocity: { x: mphToMps(150) * Math.cos(15 * Math.PI / 180), y: mphToMps(150) * Math.sin(15 * Math.PI / 180), z: 0 },
      spinRateRpm: 2500,
      spinAxisTiltDeg: 0,
      launchDeg: 15,
    },
    { wind: { x: 0, y: 0, z: 0 }, airDensity: 1 },
    DEFAULT_PARAMS
  );

  assert.ok(highSpeed.spinDecayAir < lowSpeed.spinDecayAir);
  assert.ok(steeper.dragCoeff > flatter.dragCoeff);
});
