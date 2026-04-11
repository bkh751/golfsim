const FT_TO_M = 0.3048;
const STIMP_RAMP_SPEED_MPS = 1.83;
export const CUP_RADIUS_M = 0.054;
const DEFAULT_LINE_ANGLE_DEG = 0;
const DEFAULT_TEMPO_SCORE = 0.78;

export const GREEN_PRESETS = Object.freeze({
  slow: Object.freeze({ id: "slow", label: "느림", stimp: 8.5 }),
  medium: Object.freeze({ id: "medium", label: "보통", stimp: 10 }),
  fast: Object.freeze({ id: "fast", label: "빠름", stimp: 11.5 }),
});

export const TARGET_DISTANCES_M = Object.freeze([1.5, 3, 5, 8]);

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function standardDeviation(values, mean = average(values)) {
  if (values.length < 2) return 0;
  const variance = average(values.map((value) => (value - mean) ** 2));
  return Math.sqrt(variance);
}

function normalizeSampleTimes(samples) {
  if (!samples.length) return [];
  const firstTimestamp = Number.isFinite(samples[0].timestamp) ? samples[0].timestamp : 0;
  let elapsed = 0;
  return samples.map((sample, index) => {
    if (index === 0) {
      return { ...sample, time: 0 };
    }
    const previous = samples[index - 1];
    const prevTimestamp = Number.isFinite(previous.timestamp) ? previous.timestamp : firstTimestamp + elapsed * 1000;
    const rawTimestamp = Number.isFinite(sample.timestamp) ? sample.timestamp : prevTimestamp + 16;
    const dt = clamp((rawTimestamp - prevTimestamp) / 1000, 1 / 240, 0.08);
    elapsed += dt;
    return { ...sample, time: elapsed };
  });
}

export function computeRollDeceleration(greenStimp = GREEN_PRESETS.medium.stimp) {
  const stimp = clamp(greenStimp, 7, 14);
  return (STIMP_RAMP_SPEED_MPS ** 2) / (2 * stimp * FT_TO_M);
}

function resolveRawGreenDeceleration(value) {
  return clamp(value ?? 1.55, 1.1, 2.1);
}

function resolveEffectiveGreenDeceleration(value) {
  return resolveRawGreenDeceleration(value) * 0.75;
}

function estimateStrokeSpeedForDistance(distanceM, greenDecel) {
  return clamp(
    Math.sqrt(Math.max(0.05, 2 * resolveEffectiveGreenDeceleration(greenDecel) * Math.max(0.5, distanceM))) * 1.02,
    0.4,
    3.5
  );
}

function createPosition(overrides = {}, ballRadius = 0.02135) {
  return {
    x: Number.isFinite(overrides.x) ? overrides.x : 0,
    y: Number.isFinite(overrides.y) ? overrides.y : ballRadius,
    z: Number.isFinite(overrides.z) ? overrides.z : 0,
  };
}

function createVelocity(overrides = {}) {
  return {
    x: Number.isFinite(overrides.x) ? overrides.x : 0,
    y: 0,
    z: Number.isFinite(overrides.z) ? overrides.z : 0,
  };
}

function computePaceError(positionX, holeDistanceM, holed = false) {
  if (holed) return 0;
  return positionX - holeDistanceM;
}

export const DEFAULT_PUTT_PARAMS = Object.freeze({
  ballRadius: 0.02135,
  cupRadius: CUP_RADIUS_M,
  cupCaptureSpeedMps: 1.65,
  stopSpeedMps: 0.02,
  greenDecel: 1.55,
  holeDistanceM: 4,
  maxRollDistanceM: 18,
});

export function createPuttControls(overrides = {}) {
  const holeDistanceM = clamp(overrides.holeDistanceM ?? DEFAULT_PUTT_PARAMS.holeDistanceM, 1, 15);
  const greenDecel = resolveRawGreenDeceleration(overrides.greenDecel ?? DEFAULT_PUTT_PARAMS.greenDecel);
  const strokeSpeedMps = clamp(
    overrides.strokeSpeedMps ?? estimateStrokeSpeedForDistance(holeDistanceM, greenDecel),
    0.4,
    3.5
  );
  return {
    initiateStroke: Boolean(overrides.initiateStroke),
    strokeSpeedMps,
    lineAngleDeg: clamp(overrides.lineAngleDeg ?? DEFAULT_LINE_ANGLE_DEG, -12, 12),
    holeDistanceM,
    tempoScore: clamp(overrides.tempoScore ?? DEFAULT_TEMPO_SCORE, 0, 1),
  };
}

export function createPuttState(overrides = {}) {
  const ballRadius = overrides.ballRadius ?? DEFAULT_PUTT_PARAMS.ballRadius;
  const holeDistanceM = clamp(overrides.holeDistanceM ?? DEFAULT_PUTT_PARAMS.holeDistanceM, 1, 15);
  const position = createPosition(overrides.position, ballRadius);
  return {
    phase: overrides.phase ?? "ready",
    moving: Boolean(overrides.moving),
    didImpact: Boolean(overrides.didImpact),
    holed: Boolean(overrides.holed),
    shotNo: Number.isFinite(overrides.shotNo) ? overrides.shotNo : 0,
    position,
    velocity: createVelocity(overrides.velocity),
    strokeSpeed: Number.isFinite(overrides.strokeSpeed) ? overrides.strokeSpeed : 0,
    startSpeed: Number.isFinite(overrides.startSpeed) ? overrides.startSpeed : 0,
    launchAzimuthDeg: Number.isFinite(overrides.launchAzimuthDeg) ? overrides.launchAzimuthDeg : DEFAULT_LINE_ANGLE_DEG,
    tempoScore: clamp(overrides.tempoScore ?? DEFAULT_TEMPO_SCORE, 0, 1),
    holeDistanceM,
    rollDistance: Number.isFinite(overrides.rollDistance) ? overrides.rollDistance : 0,
    totalDistance: Number.isFinite(overrides.totalDistance) ? overrides.totalDistance : 0,
    offlineDistance: Number.isFinite(overrides.offlineDistance) ? overrides.offlineDistance : position.z,
    remainingDistance: Number.isFinite(overrides.remainingDistance)
      ? overrides.remainingDistance
      : Math.hypot(holeDistanceM - position.x, position.z),
    paceError: Number.isFinite(overrides.paceError)
      ? overrides.paceError
      : computePaceError(position.x, holeDistanceM, Boolean(overrides.holed)),
  };
}

function launchPuttState(state, controls) {
  const next = createPuttState({
    ...state,
    phase: "roll",
    moving: true,
    didImpact: true,
    holed: false,
    holeDistanceM: controls.holeDistanceM,
    launchAzimuthDeg: controls.lineAngleDeg,
    strokeSpeed: controls.strokeSpeedMps,
    startSpeed: controls.strokeSpeedMps,
    tempoScore: controls.tempoScore,
    paceError: -controls.holeDistanceM,
  });
  const launchRad = (controls.lineAngleDeg * Math.PI) / 180;
  next.velocity = {
    x: Math.cos(launchRad) * controls.strokeSpeedMps,
    y: 0,
    z: Math.sin(launchRad) * controls.strokeSpeedMps,
  };
  return next;
}

function settlePuttState(state, { holed = false } = {}) {
  const next = createPuttState({
    ...state,
    phase: "rest",
    moving: false,
    holed,
    velocity: { x: 0, y: 0, z: 0 },
  });
  if (holed) {
    next.position = {
      x: next.holeDistanceM,
      y: next.position.y,
      z: 0,
    };
    next.offlineDistance = 0;
    next.remainingDistance = 0;
    next.paceError = 0;
  } else {
    next.offlineDistance = next.position.z;
    next.remainingDistance = Math.hypot(next.holeDistanceM - next.position.x, next.position.z);
    next.paceError = computePaceError(next.position.x, next.holeDistanceM, false);
  }
  return next;
}

export function stepPuttState(currentState, currentControls = {}, currentParams = {}, dt = 1 / 60) {
  const params = { ...DEFAULT_PUTT_PARAMS, ...currentParams };
  const controls = createPuttControls({
    ...currentControls,
    greenDecel: params.greenDecel,
  });
  let state = createPuttState({
    ...currentState,
    holeDistanceM: currentState?.holeDistanceM ?? controls.holeDistanceM,
    ballRadius: params.ballRadius,
  });

  if (controls.initiateStroke && !state.moving) {
    state = launchPuttState(state, controls);
  }

  if (!state.moving) {
    return state;
  }

  const stepDt = clamp(dt, 1 / 240, 0.08);
  const speedBefore = Math.hypot(state.velocity.x, state.velocity.z);
  const decel = resolveEffectiveGreenDeceleration(params.greenDecel);

  if (speedBefore <= params.stopSpeedMps) {
    return settlePuttState(state);
  }

  const nextSpeed = Math.max(0, speedBefore - decel * stepDt);
  const speedScale = speedBefore > 0 ? nextSpeed / speedBefore : 0;
  const nextVelocity = {
    x: state.velocity.x * speedScale,
    y: 0,
    z: state.velocity.z * speedScale,
  };
  const nextPosition = {
    x: state.position.x + nextVelocity.x * stepDt,
    y: state.position.y,
    z: state.position.z + nextVelocity.z * stepDt,
  };
  const rollIncrement = Math.hypot(nextPosition.x - state.position.x, nextPosition.z - state.position.z);
  const holeDistanceM = controls.holeDistanceM;
  const distanceToCup = Math.hypot(holeDistanceM - nextPosition.x, nextPosition.z);

  state = createPuttState({
    ...state,
    moving: nextSpeed > params.stopSpeedMps,
    position: nextPosition,
    velocity: nextVelocity,
    holeDistanceM,
    rollDistance: state.rollDistance + rollIncrement,
    totalDistance: state.totalDistance + rollIncrement,
    offlineDistance: nextPosition.z,
    remainingDistance: distanceToCup,
    paceError: computePaceError(nextPosition.x, holeDistanceM, false),
    ballRadius: params.ballRadius,
  });

  if (distanceToCup <= params.cupRadius && nextSpeed <= params.cupCaptureSpeedMps) {
    return settlePuttState(state, { holed: true });
  }

  if (!state.moving || state.rollDistance >= params.maxRollDistanceM) {
    return settlePuttState(state);
  }

  return state;
}

export function createManualStrokeProfile({
  power = 55,
  lineAdjustmentDeg = 0,
  tempoScore = 68,
} = {}) {
  const normalizedPower = clamp(power, 0, 100) / 100;
  const ballSpeedMps = 0.35 + normalizedPower * 2.55;
  const qualityScore = Math.round(clamp(62 + normalizedPower * 22 - Math.abs(lineAdjustmentDeg) * 2, 20, 99));
  return {
    source: "manual",
    valid: true,
    sampleCount: 0,
    durationMs: 0,
    peakAcceleration: 0,
    impulse: 0,
    ballSpeedMps,
    faceAngleDeg: clamp(lineAdjustmentDeg, -6, 6),
    startDirectionDeg: clamp(lineAdjustmentDeg * 0.85, -7, 7),
    tempoScore: Math.round(clamp(tempoScore, 0, 100)),
    smoothnessScore: Math.round(clamp(74 + normalizedPower * 12, 0, 100)),
    qualityScore,
    energyScore: Number((normalizedPower * 100).toFixed(1)),
  };
}

export function analyzeStrokeSamples(samples, options = {}) {
  const normalized = normalizeSampleTimes(Array.isArray(samples) ? samples : []);
  if (normalized.length < 4) {
    return {
      source: "sensor",
      valid: false,
      reason: "insufficient-samples",
      sampleCount: normalized.length,
    };
  }

  const noiseFloor = clamp(options.noiseFloor ?? 0.18, 0.05, 1.2);
  const activeThreshold = clamp(options.activeThreshold ?? noiseFloor * 2.2, 0.16, 2.8);
  const motionMagnitudes = normalized.map((sample) => Math.abs(sample.forward ?? sample.magnitude ?? 0));
  const firstActive = motionMagnitudes.findIndex((value) => value >= activeThreshold);
  const lastActive = (() => {
    for (let index = motionMagnitudes.length - 1; index >= 0; index -= 1) {
      if (motionMagnitudes[index] >= activeThreshold * 0.65) return index;
    }
    return -1;
  })();

  if (firstActive === -1 || lastActive <= firstActive) {
    return {
      source: "sensor",
      valid: false,
      reason: "motion-not-detected",
      sampleCount: normalized.length,
    };
  }

  const activeSamples = normalized.slice(firstActive, lastActive + 1);
  const magnitudes = activeSamples.map((sample) => Math.abs(sample.forward ?? sample.magnitude ?? 0));
  const peakAcceleration = Math.max(...magnitudes);
  const lateralMean = average(activeSamples.map((sample) => sample.lateral ?? 0));
  const twistMean = average(activeSamples.map((sample) => sample.twist ?? 0));
  const duration = Math.max(1 / 120, activeSamples[activeSamples.length - 1].time - activeSamples[0].time);
  const timeToPeak = activeSamples[magnitudes.indexOf(peakAcceleration)].time - activeSamples[0].time;
  const derivatives = [];
  let impulse = 0;

  for (let index = 1; index < activeSamples.length; index += 1) {
    const prev = activeSamples[index - 1];
    const next = activeSamples[index];
    const dt = Math.max(1 / 240, next.time - prev.time);
    const prevMagnitude = Math.abs(prev.forward ?? prev.magnitude ?? 0);
    const nextMagnitude = Math.abs(next.forward ?? next.magnitude ?? 0);
    impulse += ((prevMagnitude + nextMagnitude) * 0.5) * dt;
    derivatives.push((nextMagnitude - prevMagnitude) / dt);
  }

  const tempoRatio = clamp(timeToPeak / duration, 0, 1);
  const tempoScore = Math.round(clamp(100 - (Math.abs(tempoRatio - 0.58) / 0.58) * 100, 0, 100));
  const derivativeStd = standardDeviation(derivatives);
  const smoothnessScore = Math.round(clamp(100 - derivativeStd * 8.5, 0, 100));
  const energyScore = impulse * 1.45 + peakAcceleration * 0.78;
  const faceAngleDeg = clamp(twistMean * 0.055 + lateralMean * 1.2, -6, 6);
  const startDirectionDeg = clamp(faceAngleDeg * 0.82 + lateralMean * 0.8, -7.5, 7.5);
  const ballSpeedMps = clamp(0.28 + energyScore * 0.56, 0.2, 4.8);
  const qualityScore = Math.round(
    clamp(
      tempoScore * 0.34 +
        smoothnessScore * 0.31 +
        (100 - Math.abs(faceAngleDeg) * 12) * 0.2 +
        clamp(energyScore * 12, 10, 100) * 0.15,
      0,
      100
    )
  );

  return {
    source: "sensor",
    valid: true,
    sampleCount: activeSamples.length,
    durationMs: Math.round(duration * 1000),
    peakAcceleration: Number(peakAcceleration.toFixed(3)),
    impulse: Number(impulse.toFixed(3)),
    energyScore: Number(energyScore.toFixed(2)),
    ballSpeedMps: Number(ballSpeedMps.toFixed(3)),
    faceAngleDeg: Number(faceAngleDeg.toFixed(2)),
    startDirectionDeg: Number(startDirectionDeg.toFixed(2)),
    tempoScore,
    smoothnessScore,
    qualityScore,
  };
}

export function simulatePutt({
  ballSpeedMps,
  targetDistanceM,
  startDirectionDeg = 0,
  greenStimp = GREEN_PRESETS.medium.stimp,
  lineOffsetM = 0,
  dt = 1 / 120,
  maxTime = 12,
} = {}) {
  const speed = clamp(ballSpeedMps ?? 0, 0, 6);
  const targetDistance = clamp(targetDistanceM ?? 3, 0.5, 18);
  const angleRad = (startDirectionDeg * Math.PI) / 180;
  const deceleration = computeRollDeceleration(greenStimp);

  let elapsed = 0;
  let moving = speed > 0.01;
  let position = { x: 0, z: lineOffsetM };
  let velocity = {
    x: speed * Math.cos(angleRad),
    z: speed * Math.sin(angleRad),
  };
  const cup = { x: targetDistance, z: 0 };
  const trajectory = [{ x: 0, z: lineOffsetM }];
  let madePutt = false;

  while (moving && elapsed < maxTime) {
    const currentSpeed = Math.hypot(velocity.x, velocity.z);
    if (currentSpeed <= 0.01) {
      moving = false;
      break;
    }
    const nextSpeed = Math.max(0, currentSpeed - deceleration * dt);
    const speedScale = currentSpeed > 0 ? nextSpeed / currentSpeed : 0;
    velocity = {
      x: velocity.x * speedScale,
      z: velocity.z * speedScale,
    };
    position = {
      x: position.x + velocity.x * dt,
      z: position.z + velocity.z * dt,
    };
    if (trajectory.length === 0 || trajectory.length % 2 === 0) {
      trajectory.push({ x: position.x, z: position.z });
    }
    elapsed += dt;

    const distanceToCup = Math.hypot(position.x - cup.x, position.z - cup.z);
    if (distanceToCup <= CUP_RADIUS_M && nextSpeed <= 1.65) {
      madePutt = true;
      position = { ...cup };
      velocity = { x: 0, z: 0 };
      trajectory.push({ ...position });
      moving = false;
      break;
    }
  }

  const stopDistanceM = position.x;
  const distanceErrorM = stopDistanceM - targetDistance;
  const lateralMissM = position.z;
  const missDistanceM = Math.hypot(distanceErrorM, lateralMissM);

  return {
    madePutt,
    greenStimp: Number(greenStimp.toFixed(1)),
    stopDistanceM: Number(stopDistanceM.toFixed(3)),
    distanceErrorM: Number(distanceErrorM.toFixed(3)),
    lateralMissM: Number(lateralMissM.toFixed(3)),
    missDistanceM: Number(missDistanceM.toFixed(3)),
    rollTimeMs: Math.round(elapsed * 1000),
    trajectory,
  };
}

export function describePuttResult(result) {
  if (!result) return "결과 없음";
  if (result.madePutt) return "홀인";
  const distancePart = result.distanceErrorM > 0.08
    ? `${Math.abs(result.distanceErrorM).toFixed(2)}m 길게`
    : result.distanceErrorM < -0.08
      ? `${Math.abs(result.distanceErrorM).toFixed(2)}m 짧게`
      : "거리 좋음";
  const linePart = result.lateralMissM > 0.04
    ? `${Math.abs(result.lateralMissM).toFixed(2)}m 우측`
    : result.lateralMissM < -0.04
      ? `${Math.abs(result.lateralMissM).toFixed(2)}m 좌측`
      : "라인 좋음";
  return `${distancePart} · ${linePart}`;
}
