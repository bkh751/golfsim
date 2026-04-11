const DEG_TO_RAD = Math.PI / 180;
const RAD_PER_RPM = (2 * Math.PI) / 60;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function getRelativeVelocity(ballState, environment) {
  const wind = environment.wind ?? { x: 0, y: 0, z: 0 };
  return {
    x: (ballState.velocity?.x ?? 0) - wind.x,
    y: (ballState.velocity?.y ?? 0) - wind.y,
    z: (ballState.velocity?.z ?? 0) - wind.z,
  };
}

function getSpeed(relVel) {
  return Math.max(0.001, Math.hypot(relVel.x, relVel.y, relVel.z));
}

function getSpinRatio(ballState, params, speed) {
  const spinRateRpm = Math.max(0, ballState.spinRateRpm ?? 0);
  return clamp((spinRateRpm * RAD_PER_RPM * params.ballRadius) / speed, 0, 0.35);
}

function getLaunchWindow(ballState) {
  const launchRef = Number.isFinite(ballState.launchDeg)
    ? ballState.launchDeg
    : Number.isFinite(ballState.launchElevationDeg)
      ? ballState.launchElevationDeg
      : 10;
  return clamp(1 - Math.abs(launchRef - 10) / 5.5, 0.02, 1);
}

export function computeAeroCoefficients(ballState, environment, params) {
  const airDensity = environment.airDensity ?? 1;
  const relVel = getRelativeVelocity(ballState, environment);
  const speed = getSpeed(relVel);
  const spinRateRpm = Math.max(0, ballState.spinRateRpm ?? 0);
  const spinRatio = getSpinRatio(ballState, params, speed);
  const lowSpeedLiftBoost = clamp((72 - speed) / 18, 0, 1);
  const highSpeedDragBoost = clamp((speed - 70) / 12, 0, 1);
  const climbRatio = clamp(Math.abs(relVel.y) / speed, 0, 0.5);
  const launchWindow = getLaunchWindow(ballState);
  const tilt = Math.abs((ballState.spinAxisTiltDeg ?? 0) * DEG_TO_RAD);
  const highSpinPenalty = clamp((spinRateRpm - 2525) / 525, 0, 1.4);
  const highSpeedSpinPenalty = highSpeedDragBoost * highSpinPenalty;

  return {
    dragCoeff:
      params.dragCoeff *
      airDensity *
      (1 + 0.03 * spinRatio + 0.85 * highSpeedDragBoost + 1.055 * highSpeedSpinPenalty + 1.8 * climbRatio),
    magnusCoeff:
      params.magnusCoeff *
      airDensity *
      (1.08 + 2.6 * spinRatio + 4.4 * lowSpeedLiftBoost * spinRatio * launchWindow - 0.85 * highSpeedSpinPenalty),
    sideMagnusScale: params.sideMagnusScale * (1 - tilt * 0.08),
    spinDecayAir: clamp(
      0.9990 -
        0.004 * spinRatio -
        0.01 * lowSpeedLiftBoost * spinRatio -
        0.18 * highSpeedDragBoost * spinRatio -
        0.037 * highSpeedSpinPenalty,
      0.968,
      0.9997
    ),
    spinDecayGround: params.spinDecayGround,
  };
}

export const DEFAULT_AERO_MODEL = Object.freeze({
  getCoefficients(ballState, environment, params) {
    return computeAeroCoefficients(ballState, environment, params);
  },
});
