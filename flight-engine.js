import { DEFAULT_AERO_MODEL } from "./aero-model.js";
import { computeTrajectoryMetrics } from "./metrics-agent.js";

const RAD_PER_RPM = (2 * Math.PI) / 60;

function length3(v) {
  return Math.hypot(v.x, v.y, v.z);
}

function cross(a, b) {
  return {
    x: a.y * b.z - a.z * b.y,
    y: a.z * b.x - a.x * b.z,
    z: a.x * b.y - a.y * b.x,
  };
}

function copyVector(v) {
  return { x: v.x, y: v.y, z: v.z };
}

export function createFlightState(overrides = {}) {
  const basePosition = overrides.position ?? { x: 0, y: 0, z: 0 };
  return {
    position: { x: basePosition.x, y: basePosition.y, z: basePosition.z },
    velocity: { x: 0, y: 0, z: 0, ...(overrides.velocity ?? {}) },
    spinRateRpm: 0,
    spinAxisTiltDeg: 0,
    backspinRpm: 0,
    sidespinRpm: 0,
    moving: false,
    firstBounceDone: false,
    launchPos: { x: basePosition.x, y: basePosition.y, z: basePosition.z },
    landingPos: { x: basePosition.x, y: basePosition.y, z: basePosition.z },
    apexHeight: basePosition.y,
    ...overrides,
  };
}

export function stepFlightState(
  flightState,
  environment,
  params,
  dt,
  aeroModel = DEFAULT_AERO_MODEL
) {
  const next = createFlightState(flightState);
  const wind = environment.wind ?? { x: 0, y: 0, z: 0 };
  const coefficients = (aeroModel ?? DEFAULT_AERO_MODEL).getCoefficients(next, environment, params);
  const relVel = {
    x: next.velocity.x - wind.x,
    y: next.velocity.y - wind.y,
    z: next.velocity.z - wind.z,
  };
  const speed = Math.max(0.001, length3(relVel));
  const spinVector = {
    x: 0,
    y: -next.sidespinRpm * RAD_PER_RPM * coefficients.sideMagnusScale,
    z: next.backspinRpm * RAD_PER_RPM,
  };
  const magnus = cross(spinVector, relVel);
  const accel = {
    x: -coefficients.dragCoeff * speed * relVel.x + coefficients.magnusCoeff * magnus.x,
    y: -params.gravity - coefficients.dragCoeff * speed * relVel.y + coefficients.magnusCoeff * magnus.y,
    z: -coefficients.dragCoeff * speed * relVel.z + coefficients.magnusCoeff * magnus.z,
  };

  next.velocity = {
    x: next.velocity.x + accel.x * dt,
    y: next.velocity.y + accel.y * dt,
    z: next.velocity.z + accel.z * dt,
  };
  next.position = {
    x: next.position.x + next.velocity.x * dt,
    y: next.position.y + next.velocity.y * dt,
    z: next.position.z + next.velocity.z * dt,
  };

  next.backspinRpm *= Math.pow(coefficients.spinDecayAir, dt * 60);
  next.sidespinRpm *= Math.pow(coefficients.spinDecayAir, dt * 60);
  next.spinRateRpm = Math.hypot(next.backspinRpm, next.sidespinRpm);
  next.spinAxisTiltDeg = Math.atan2(next.sidespinRpm, Math.max(1e-6, next.backspinRpm)) * (180 / Math.PI);
  next.apexHeight = Math.max(next.apexHeight, next.position.y);

  if (next.position.y <= params.groundY + params.ballRadius) {
    next.position.y = params.groundY + params.ballRadius;

    if (!next.firstBounceDone) {
      next.firstBounceDone = true;
      next.landingPos = copyVector(next.position);
    }

    next.velocity.y = Math.abs(next.velocity.y) * params.bounceRestitution;
    next.velocity.x *= params.bounceLateralRestitution;
    next.velocity.z *= params.bounceLateralRestitution;
    next.backspinRpm *= 0.72;
    next.sidespinRpm *= 0.58;

    if (Math.abs(next.velocity.y) < params.stopVy) {
      next.velocity.y = 0;
      next.velocity.x *= params.rollFrictionForward;
      next.velocity.z *= params.rollFrictionLateral;
      next.sidespinRpm *= coefficients.spinDecayGround;

      if (Math.hypot(next.velocity.x, next.velocity.z) < params.stopVxz) {
        next.velocity = { x: 0, y: 0, z: 0 };
        next.moving = false;
      }
    }
  }

  const metrics = computeTrajectoryMetrics(next);
  return {
    ...next,
    ...metrics,
  };
}
