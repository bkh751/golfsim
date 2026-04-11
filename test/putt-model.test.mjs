import test from "node:test";
import assert from "node:assert/strict";

import { createPuttControls, createPuttState, stepPuttState } from "../putt-model.js";

test("putt model rolls forward and stops with finite metrics", () => {
  let state = createPuttState();
  let controls = createPuttControls({
    initiateStroke: true,
    strokeSpeedMps: 1.4,
    lineAngleDeg: 0,
    holeDistanceM: 4,
    tempoScore: 0.84,
  });

  for (let i = 0; i < 360; i += 1) {
    state = stepPuttState(state, controls, {}, 1 / 60);
    controls = { ...controls, initiateStroke: false };
    if (!state.moving && state.didImpact) break;
  }

  assert.equal(state.phase, "rest");
  assert.equal(state.didImpact, true);
  assert.ok(state.rollDistance > 0);
  assert.ok(Number.isFinite(state.remainingDistance));
  assert.ok(Number.isFinite(state.paceError));
});

test("putt model captures the cup when the ball reaches the hole slowly enough", () => {
  let state = createPuttState();
  let controls = createPuttControls({
    initiateStroke: true,
    strokeSpeedMps: 2.4,
    lineAngleDeg: 0,
    holeDistanceM: 2,
    tempoScore: 0.92,
  });

  for (let i = 0; i < 360; i += 1) {
    state = stepPuttState(state, controls, {}, 1 / 60);
    controls = { ...controls, initiateStroke: false };
    if (!state.moving && state.didImpact) break;
  }

  assert.equal(state.holed, true);
  assert.equal(state.remainingDistance, 0);
  assert.equal(state.position.z, 0);
});
