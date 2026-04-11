import test from 'node:test';
import assert from 'node:assert/strict';

import {
  DEFAULT_SESSION_KIND,
  SESSION_KIND_PUTTER,
  SESSION_KIND_RANGE,
  SESSION_MODE_STORAGE_KEY,
  buildSessionContractPayload,
  normalizeSessionKind,
  persistSessionKind,
  restoreSessionKind,
} from '../session-contract.js';

test('session contract normalizes and restores persisted session kind safely', () => {
  const storage = new Map();
  const fakeStorage = {
    getItem(key) {
      return storage.has(key) ? storage.get(key) : null;
    },
    setItem(key, value) {
      storage.set(key, value);
    },
  };

  assert.equal(DEFAULT_SESSION_KIND, SESSION_KIND_RANGE);
  assert.equal(normalizeSessionKind('unknown'), SESSION_KIND_RANGE);
  assert.equal(persistSessionKind('putter', fakeStorage), SESSION_KIND_PUTTER);
  assert.equal(storage.get(SESSION_MODE_STORAGE_KEY), SESSION_KIND_PUTTER);
  assert.equal(restoreSessionKind(fakeStorage), SESSION_KIND_PUTTER);
});

test('session contract payload exposes replay and input structure for range and putter', () => {
  const rangePayload = buildSessionContractPayload({
    sessionKind: 'range',
    mode: 'session_ready',
    totalShots: 2,
    distanceUnit: 'm',
    autoResetTimer: 0,
    currentShot: { shotNo: 2, sessionKind: 'range' },
    previousShot: { shotNo: 1, sessionKind: 'range' },
    recentShots: [{ shotNo: 2 }, { shotNo: 1 }],
    detachedFlights: [{ shotNo: 3 }],
    aimDeg: 10.4,
    yawDeg: -3,
    manualLaunch: { ballSpeedMps: 67.2, backspinRpm: 2500, sideSpinRpm: -150 },
    putt: {
      holeDistanceM: 4,
      greenDecel: 1.55,
      manualStrokeSpeedMps: 3.1,
      motion: { supported: true, permission: 'granted', calibrated: true, armed: false, pendingStroke: null, lastStroke: null },
    },
  });

  assert.equal(rangePayload.selection.currentKind, 'range');
  assert.equal(rangePayload.replay.currentShotNo, 2);
  assert.deepEqual(rangePayload.replay.recentShotNos, [2, 1]);
  assert.deepEqual(rangePayload.replay.detachedFlightShotNos, [3]);
  assert.equal(rangePayload.input.kind, 'range');
  assert.equal(rangePayload.result.comparisonAvailable, true);

  const putterPayload = buildSessionContractPayload({
    sessionKind: 'putter',
    mode: 'session_ready',
    totalShots: 0,
    distanceUnit: 'yd',
    autoResetTimer: 0,
    currentShot: null,
    previousShot: null,
    recentShots: [],
    detachedFlights: [],
    aimDeg: 0,
    yawDeg: 0,
    manualLaunch: { ballSpeedMps: null, backspinRpm: null, sideSpinRpm: null },
    putt: {
      holeDistanceM: 5.5,
      greenDecel: 1.65,
      manualStrokeSpeedMps: 2.85,
      motion: { supported: true, permission: 'idle', calibrated: false, armed: false, pendingStroke: null, lastStroke: null },
    },
  });

  assert.equal(putterPayload.selection.currentKind, 'putter');
  assert.equal(putterPayload.input.kind, 'putter');
  assert.equal(putterPayload.input.holeDistanceM, 5.5);
  assert.equal(putterPayload.result.currentShotAvailable, false);
});
