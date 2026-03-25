const DEG_TO_RAD = Math.PI / 180;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export const DEFAULT_AERO_MODEL = Object.freeze({
  getCoefficients(ballState, environment, params) {
    const airDensity = environment.airDensity ?? 1;
    const spinRate = Math.max(0, ballState.spinRateRpm ?? 0);
    const spinRatio = clamp(spinRate / 4200, 0, 2.2);
    const tilt = Math.abs((ballState.spinAxisTiltDeg ?? 0) * DEG_TO_RAD);

    return {
      dragCoeff: params.dragCoeff * airDensity * (1 + spinRatio * 0.08),
      magnusCoeff: params.magnusCoeff * airDensity * (1 + spinRatio * 0.18),
      sideMagnusScale: params.sideMagnusScale * (1 - tilt * 0.08),
      spinDecayAir: clamp(params.spinDecayAir - spinRatio * 0.0005, 0.985, 0.9995),
      spinDecayGround: params.spinDecayGround,
    };
  },
});
