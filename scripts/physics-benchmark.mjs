import fs from 'node:fs/promises';

import { createFlightState, stepFlightState } from '../flight-engine.js';
import { DEFAULT_PARAMS } from '../swing-model.js';

const MATRIX_PATH = new URL('../test/fixtures/flight-benchmark-matrix.json', import.meta.url);

function mphToMps(mph) {
  return mph * 0.44704;
}

function fpsToMps(fps) {
  return fps * 0.3048;
}

function toYards(meters) {
  return meters * 1.09361;
}

function formatWindow(window) {
  if (!window) return '-';
  if (Number.isFinite(window.min) && Number.isFinite(window.max)) {
    return `${window.min.toFixed(1)}-${window.max.toFixed(1)}`;
  }
  if (Number.isFinite(window.min)) return `>= ${window.min.toFixed(1)}`;
  if (Number.isFinite(window.max)) return `<= ${window.max.toFixed(1)}`;
  return '-';
}

function inWindow(value, window) {
  if (!window) return true;
  if (Number.isFinite(window.min) && value < window.min) return false;
  if (Number.isFinite(window.max) && value > window.max) return false;
  return true;
}

function simulateCase(entry) {
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
    apexFeet: state.apexHeight * 3.28084,
  };
}

function printRow(row) {
  console.log(
    [
      row.id.padEnd(28),
      `${row.status}`.padEnd(6),
      `${row.carryYards.toFixed(1)} yd`.padStart(10),
      `${formatWindow(row.expected.carryYards)} yd`.padStart(16),
      `${row.totalYards.toFixed(1)} yd`.padStart(10),
      `${formatWindow(row.expected.totalYards)} yd`.padStart(16),
      `${row.apexFeet.toFixed(1)} ft`.padStart(10),
    ].join(' | ')
  );
}

const matrix = JSON.parse(await fs.readFile(MATRIX_PATH, 'utf8'));
const results = matrix.map((entry) => {
  const actual = simulateCase(entry);
  const pass =
    inWindow(actual.carryYards, entry.expected.carryYards) &&
    inWindow(actual.totalYards, entry.expected.totalYards);
  return {
    id: entry.id,
    status: pass ? 'PASS' : 'FAIL',
    expected: entry.expected,
    ...actual,
  };
});

console.log('id'.padEnd(28), '|', 'status'.padEnd(6), '|', 'carry'.padStart(10), '|', 'carry window'.padStart(16), '|', 'total'.padStart(10), '|', 'total window'.padStart(16), '|', 'apex'.padStart(10));
console.log('-'.repeat(115));
for (const row of results) printRow(row);

if (results.some((row) => row.status === 'FAIL')) {
  process.exitCode = 1;
}
