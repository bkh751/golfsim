const DEG_TO_RAD = Math.PI / 180;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function copyVector(v) {
  return { x: v.x, y: v.y, z: v.z };
}

export function createImpactContext(overrides = {}) {
  return {
    clubHeadSpeed: 0,
    attackAngleDeg: 0,
    ballPos: { x: 0, y: 0, z: 0 },
    impactQuality: 1,
    ...overrides,
  };
}

export function createImpactOutput(context, controls, params) {
  const manualLaunchMode =
    Number.isFinite(controls.manualBallSpeedMps) ||
    Number.isFinite(controls.manualBackspinRpm) ||
    Number.isFinite(controls.manualSideSpinRpm);
  const strikePenalty = Math.abs(controls.strikeOffsetX) * 0.12 + Math.abs(controls.strikeOffsetY) * 0.09;
  const powerTransfer = 0.34 + controls.powerNorm * 0.72;
  const smash = clamp(
    params.smashMin + (params.smashMax - params.smashMin) * (0.48 + 0.52 * controls.powerNorm) - strikePenalty,
    params.smashMin,
    params.smashMax
  );

  const computedBallSpeed = clamp(smash * context.clubHeadSpeed * powerTransfer, 10, 112);
  const dynamicLoftDeg =
    params.loftBaseDeg +
    controls.loftDeltaDeg +
    params.attackLoftCoupling * context.attackAngleDeg -
    Math.abs(controls.strikeOffsetY) * 2.4;
  const launchElevationDeg = manualLaunchMode
    ? clamp(controls.aimDeg, 3, 48)
    : clamp(
      controls.aimDeg +
        0.2 * context.attackAngleDeg +
        0.48 * dynamicLoftDeg -
        params.strikeLaunchPenalty * controls.strikeOffsetY,
      3,
      48
    );
  const faceToPathDeg = controls.faceAngleBias - controls.clubPathBias + controls.strikeOffsetX * 5.5;
  const launchAzimuthDeg = manualLaunchMode
    ? clamp(controls.yawDeg, -35, 35)
    : clamp(
      controls.yawDeg + controls.clubPathBias * 0.55 + controls.faceAngleBias * 0.35 + controls.strikeOffsetX * 2.8,
      -35,
      35
    );
  const computedSpinRateRpm = clamp(
    params.spinBase +
      (dynamicLoftDeg - context.attackAngleDeg) * params.spinLoftGain +
      controls.strikeOffsetY * params.strikeSpinGain +
      Math.abs(faceToPathDeg) * 120,
    params.spinMin,
    params.spinMax
  );
  const computedSpinAxisTiltDeg = clamp(faceToPathDeg * 2.8 + controls.strikeOffsetX * 13, -32, 32);
  const computedTiltRad = computedSpinAxisTiltDeg * DEG_TO_RAD;
  const computedBackspinRpm = computedSpinRateRpm * Math.cos(computedTiltRad);
  const computedSidespinRpm = computedSpinRateRpm * Math.sin(computedTiltRad);

  const ballSpeed = Number.isFinite(controls.manualBallSpeedMps)
    ? clamp(controls.manualBallSpeedMps, 5, 112)
    : computedBallSpeed;
  const sidespinRpm = Number.isFinite(controls.manualSideSpinRpm)
    ? clamp(controls.manualSideSpinRpm, -4000, 4000)
    : computedSidespinRpm;
  const backspinRpm = Number.isFinite(controls.manualBackspinRpm)
    ? clamp(controls.manualBackspinRpm, params.spinMin, params.spinMax)
    : computedBackspinRpm;
  const spinRateRpm = clamp(Math.hypot(backspinRpm, sidespinRpm), params.spinMin, params.spinMax);
  const spinAxisTiltDeg = clamp(Math.atan2(sidespinRpm, Math.max(1e-6, backspinRpm)) / DEG_TO_RAD, -45, 45);

  const launchRad = launchElevationDeg * DEG_TO_RAD;
  const azimuthRad = launchAzimuthDeg * DEG_TO_RAD;

  return {
    ballSpeed,
    dynamicLoftDeg,
    launchElevationDeg,
    launchAzimuthDeg,
    spinRateRpm,
    spinAxisTiltDeg,
    backspinRpm,
    sidespinRpm,
    launchPos: copyVector(context.ballPos),
    initialBallState: {
      position: copyVector(context.ballPos),
      velocity: {
        x: ballSpeed * Math.cos(launchRad) * Math.cos(azimuthRad),
        y: ballSpeed * Math.sin(launchRad),
        z: ballSpeed * Math.cos(launchRad) * Math.sin(azimuthRad),
      },
      launchDeg: launchElevationDeg,
      launchAzimuthDeg,
      spinRateRpm,
      spinAxisTiltDeg,
      backspinRpm,
      sidespinRpm,
      moving: true,
      firstBounceDone: false,
      launchPos: copyVector(context.ballPos),
      landingPos: copyVector(context.ballPos),
      apexHeight: context.ballPos.y,
    },
  };
}
