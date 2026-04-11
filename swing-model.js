const DEG_TO_RAD = Math.PI / 180;
const RAD_TO_DEG = 180 / Math.PI;

import { DEFAULT_AERO_MODEL } from "./aero-model.js";
import { createFlightState, stepFlightState } from "./flight-engine.js";
import { computeTrajectoryMetrics } from "./metrics-agent.js";
import { createImpactContext, createImpactOutput } from "./impact-agent.js";

export const DEFAULT_PARAMS = Object.freeze({
  torsoInertia: 2.5,
  armInertia: 0.9,
  clubInertia: 0.25,
  torsoDamping: 8.5,
  armDamping: 6.0,
  clubDamping: 4.8,
  torsoStiffness: 42,
  armStiffness: 30,
  clubStiffness: 22,
  torsoLength: 0.42,
  armLength: 0.68,
  clubLength: 1.0,
  torsoTorqueBase: 220,
  armTorqueBase: 180,
  wristTorqueBase: 120,
  armReleaseDelay: 0.05,
  wristReleaseDelay: 0.09,
  impactBaseTime: 0.18,
  clubSpeedScale: 3.1,
  smashMin: 1.2,
  smashMax: 1.52,
  loftBaseDeg: 13,
  attackLoftCoupling: 0.25,
  strikeLaunchPenalty: 8,
  spinBase: 2600,
  spinLoftGain: 55,
  strikeSpinGain: 420,
  spinMin: 1400,
  spinMax: 7200,
  // Calibrated against TrackMan and USGA driver benchmark windows while keeping the real ball size.
  gravity: 9.81,
  dragCoeff: 0.00078,
  magnusCoeff: 0.00017,
  sideMagnusScale: 0.88,
  spinDecayAir: 0.998,
  spinDecayGround: 0.88,
  bounceRestitution: 0.18,
  bounceLateralRestitution: 0.88,
  rollFrictionForward: 0.995,
  rollFrictionLateral: 0.985,
  stopVxz: 1.6,
  stopVy: 1.6,
  windMin: -14,
  windMax: 14,
  ballRadius: 0.02135,
  groundY: 0,
});

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function clampFinite(value, fallback, min, max) {
  const base = Number.isFinite(value) ? value : fallback;
  return clamp(base, min, max);
}

function phaseTarget(phase) {
  if (phase === "downswing") {
    return {
      torso: -0.05,
      arm: 0.08,
      club: 0.24,
    };
  }
  return {
    torso: -0.65,
    arm: -0.95,
    club: -1.32,
  };
}

function computeClubKinematics(state, params) {
  const a1 = state.thetaTorso;
  const a2 = state.thetaTorso + state.thetaArm;
  const a3 = state.thetaTorso + state.thetaArm + state.thetaClub;

  const w1 = state.omegaTorso;
  const w2 = state.omegaTorso + state.omegaArm;
  const w3 = state.omegaTorso + state.omegaArm + state.omegaClub;

  const vx =
    -params.torsoLength * Math.sin(a1) * w1 -
    params.armLength * Math.sin(a2) * w2 -
    params.clubLength * Math.sin(a3) * w3;
  const vy =
    params.torsoLength * Math.cos(a1) * w1 +
    params.armLength * Math.cos(a2) * w2 +
    params.clubLength * Math.cos(a3) * w3;

  const speed = Math.hypot(vx, vy) * params.clubSpeedScale;
  const attackAngleDeg = Math.atan2(vy, Math.max(0.001, vx)) * RAD_TO_DEG;

  return {
    clubHeadSpeed: speed,
    attackAngleDeg,
  };
}

function ensureVector(value, fallback) {
  if (!value || typeof value !== "object") return { ...fallback };
  return {
    x: Number.isFinite(value.x) ? value.x : fallback.x,
    y: Number.isFinite(value.y) ? value.y : fallback.y,
    z: Number.isFinite(value.z) ? value.z : fallback.z,
  };
}

function copyVector(v) {
  return { x: v.x, y: v.y, z: v.z };
}

function createBasePosition() {
  return { x: 0, y: DEFAULT_PARAMS.ballRadius, z: 0 };
}

export function createInitialState(overrides = {}) {
  const initialBallPos = ensureVector(overrides.ballPos, createBasePosition());
  const initialBallVel = ensureVector(overrides.ballVel, { x: 0, y: 0, z: 0 });

  const state = {
    phase: "address",
    swingTime: 0,
    thetaTorso: -0.65,
    thetaArm: -0.95,
    thetaClub: -1.32,
    omegaTorso: 0,
    omegaArm: 0,
    omegaClub: 0,
    clubHeadSpeed: 0,
    attackAngleDeg: 0,
    dynamicLoftDeg: 0,
    launchDeg: 0,
    launchAzimuthDeg: 0,
    ballSpeed: 0,
    impactQuality: 1,
    spinRateRpm: 0,
    spinAxisTiltDeg: 0,
    backspinRpm: 0,
    sidespinRpm: 0,
    didImpact: false,
    ballPos: initialBallPos,
    ballVel: initialBallVel,
    ballMoving: false,
    launchPos: copyVector(initialBallPos),
    landingPos: copyVector(initialBallPos),
    carryDistance: 0,
    totalDistance: 0,
    offlineDistance: 0,
    apexHeight: initialBallPos.y,
    firstBounceDone: false,
  };

  const merged = {
    ...state,
    ...overrides,
  };

  merged.ballPos = ensureVector(merged.ballPos, initialBallPos);
  merged.ballVel = ensureVector(merged.ballVel, initialBallVel);
  merged.launchPos = ensureVector(merged.launchPos, merged.ballPos);
  merged.landingPos = ensureVector(merged.landingPos, merged.ballPos);
  merged.ballX = merged.ballPos.x;
  merged.ballY = merged.ballPos.y;
  merged.ballZ = merged.ballPos.z;
  merged.ballVx = merged.ballVel.x;
  merged.ballVy = merged.ballVel.y;
  merged.ballVz = merged.ballVel.z;
  merged.spinRpm = merged.spinRateRpm;
  return merged;
}

export function createDefaultControls(overrides = {}) {
  return {
    initiateSwing: false,
    powerNorm: 0.5,
    tempoNorm: 0.7,
    aimDeg: 10.4,
    yawDeg: 0,
    loftDeltaDeg: 0,
    strikeOffsetX: 0,
    strikeOffsetY: 0,
    clubPathBias: 0,
    faceAngleBias: 0,
    windX: 0,
    windZ: 0,
    manualBallSpeedMps: null,
    manualBackspinRpm: null,
    manualSideSpinRpm: null,
    ...overrides,
  };
}

function updateCompatibilityFields(next) {
  next.ballX = next.ballPos.x;
  next.ballY = next.ballPos.y;
  next.ballZ = next.ballPos.z;
  next.ballVx = next.ballVel.x;
  next.ballVy = next.ballVel.y;
  next.ballVz = next.ballVel.z;
  next.spinRpm = next.spinRateRpm;
}

function buildImpactState(next, controls, params) {
  const impactOutput = createImpactOutput(
    createImpactContext({
      clubHeadSpeed: next.clubHeadSpeed,
      attackAngleDeg: next.attackAngleDeg,
      ballPos: next.ballPos,
      impactQuality: next.impactQuality,
    }),
    controls,
    params
  );

  next.ballVel = impactOutput.initialBallState.velocity;
  next.ballMoving = true;
  next.phase = "flight";
  next.didImpact = true;
  next.dynamicLoftDeg = impactOutput.dynamicLoftDeg;
  next.launchDeg = impactOutput.launchElevationDeg;
  next.launchAzimuthDeg = impactOutput.launchAzimuthDeg;
  next.ballSpeed = impactOutput.ballSpeed;
  next.spinRateRpm = impactOutput.spinRateRpm;
  next.spinAxisTiltDeg = impactOutput.spinAxisTiltDeg;
  next.backspinRpm = impactOutput.backspinRpm;
  next.sidespinRpm = impactOutput.sidespinRpm;
  next.launchPos = copyVector(impactOutput.launchPos);
  next.landingPos = copyVector(impactOutput.launchPos);
  Object.assign(
    next,
    computeTrajectoryMetrics(createFlightState(impactOutput.initialBallState))
  );
  next.firstBounceDone = false;
}

export function stepSwingModel(state, controls = {}, params = {}, dt = 1 / 60) {
  const safeDt = clampFinite(dt, 1 / 60, 1e-6, 0.1);
  const p = { ...DEFAULT_PARAMS, ...params };
  const uRaw = { ...createDefaultControls(), ...controls };
  const u = {
    ...uRaw,
    powerNorm: clampFinite(uRaw.powerNorm, 0.5, 0, 1),
    tempoNorm: clampFinite(uRaw.tempoNorm, 0.7, 0.4, 1.3),
    aimDeg: clampFinite(uRaw.aimDeg, 14, 3, 45),
    yawDeg: clampFinite(uRaw.yawDeg, 0, -35, 35),
    loftDeltaDeg: clampFinite(uRaw.loftDeltaDeg, 0, -8, 8),
    strikeOffsetX: clampFinite(uRaw.strikeOffsetX, 0, -0.35, 0.35),
    strikeOffsetY: clampFinite(uRaw.strikeOffsetY, 0, -0.35, 0.35),
    clubPathBias: clampFinite(uRaw.clubPathBias, 0, -12, 12),
    faceAngleBias: clampFinite(uRaw.faceAngleBias, 0, -12, 12),
    windX: clampFinite(uRaw.windX, 0, p.windMin, p.windMax),
    windZ: clampFinite(uRaw.windZ, 0, p.windMin, p.windMax),
    manualBallSpeedMps: Number.isFinite(uRaw.manualBallSpeedMps)
      ? clamp(uRaw.manualBallSpeedMps, 5, 112)
      : null,
    manualBackspinRpm: Number.isFinite(uRaw.manualBackspinRpm)
      ? clamp(uRaw.manualBackspinRpm, 1200, 7200)
      : null,
    manualSideSpinRpm: Number.isFinite(uRaw.manualSideSpinRpm)
      ? clamp(uRaw.manualSideSpinRpm, -4000, 4000)
      : null,
  };

  const next = createInitialState(state);
  next.didImpact = false;

  if (u.initiateSwing && (next.phase === "address" || next.phase === "rest")) {
    next.phase = "downswing";
    next.swingTime = 0;
    next.thetaTorso = -0.65;
    next.thetaArm = -0.95;
    next.thetaClub = -1.32;
    next.omegaTorso = 0;
    next.omegaArm = 0;
    next.omegaClub = 0;
    next.impactQuality = clamp(1 - (Math.abs(u.strikeOffsetX) + Math.abs(u.strikeOffsetY)) * 1.2, 0.25, 1);
  }

  if (next.phase === "downswing") {
    next.swingTime += safeDt;

    const targets = phaseTarget(next.phase);
    const timingScale = 0.8 + 0.45 * u.tempoNorm;
    const powerScale = 0.4 + 0.9 * u.powerNorm;

    const armEnabled = next.swingTime >= p.armReleaseDelay / timingScale ? 1 : 0.3;
    const wristEnabled = next.swingTime >= p.wristReleaseDelay / timingScale ? 1 : 0.22;

    const tauTorso = p.torsoTorqueBase * powerScale * timingScale;
    const tauArm = p.armTorqueBase * powerScale * timingScale * armEnabled;
    const tauClub = p.wristTorqueBase * powerScale * timingScale * wristEnabled;

    const dOmegaTorso =
      (tauTorso - p.torsoDamping * next.omegaTorso - p.torsoStiffness * (next.thetaTorso - targets.torso)) /
      p.torsoInertia;
    const dOmegaArm =
      (tauArm - p.armDamping * next.omegaArm - p.armStiffness * (next.thetaArm - targets.arm)) / p.armInertia;
    const dOmegaClub =
      (tauClub - p.clubDamping * next.omegaClub - p.clubStiffness * (next.thetaClub - targets.club)) / p.clubInertia;

    next.omegaTorso += dOmegaTorso * safeDt;
    next.omegaArm += dOmegaArm * safeDt;
    next.omegaClub += dOmegaClub * safeDt;

    next.thetaTorso += next.omegaTorso * safeDt;
    next.thetaArm += next.omegaArm * safeDt;
    next.thetaClub += next.omegaClub * safeDt;

    const swing = computeClubKinematics(next, p);
    next.clubHeadSpeed = clampFinite(swing.clubHeadSpeed, next.clubHeadSpeed, 0, 95);
    next.attackAngleDeg = clampFinite(swing.attackAngleDeg, next.attackAngleDeg, -20, 24);

    const impactTime = p.impactBaseTime / (0.72 + 0.5 * u.tempoNorm);
    const impactReached = next.swingTime >= impactTime || (next.thetaClub > -0.16 && next.omegaClub > 0);

    if (impactReached) {
      buildImpactState(next, u, p);
    }
  }

  if (next.phase === "flight") {
    const environment = {
      wind: { x: u.windX, y: 0, z: u.windZ },
    };
    const flightStep = 1 / 240;
    let remainingDt = safeDt;
    let flight = createFlightState({
      position: next.ballPos,
      velocity: next.ballVel,
      spinRateRpm: next.spinRateRpm,
      spinAxisTiltDeg: next.spinAxisTiltDeg,
      backspinRpm: next.backspinRpm,
      sidespinRpm: next.sidespinRpm,
      moving: next.ballMoving,
      firstBounceDone: next.firstBounceDone,
      launchDeg: next.launchDeg,
      launchAzimuthDeg: next.launchAzimuthDeg,
      launchPos: next.launchPos,
      landingPos: next.landingPos,
      apexHeight: next.apexHeight,
    });

    while (remainingDt > 1e-9 && flight.moving) {
      const dtStep = Math.min(flightStep, remainingDt);
      flight = stepFlightState(
        flight,
        environment,
        p,
        dtStep,
        DEFAULT_AERO_MODEL
      );
      remainingDt -= dtStep;
    }

    next.ballPos = flight.position;
    next.ballVel = flight.velocity;
    next.spinRateRpm = flight.spinRateRpm;
    next.spinAxisTiltDeg = flight.spinAxisTiltDeg;
    next.backspinRpm = flight.backspinRpm;
    next.sidespinRpm = flight.sidespinRpm;
    next.ballMoving = flight.moving;
    next.firstBounceDone = flight.firstBounceDone;
    next.launchPos = flight.launchPos;
    next.landingPos = flight.landingPos;
    next.carryDistance = flight.carryDistance;
    next.totalDistance = flight.totalDistance;
    next.offlineDistance = flight.offlineDistance;
    next.apexHeight = flight.apexHeight;

    if (!flight.moving) {
      next.phase = "rest";
    }
  }

  if (next.phase !== "flight") {
    next.ballMoving = false;
  }

  const finiteValues = [
    next.ballPos.x,
    next.ballPos.y,
    next.ballPos.z,
    next.ballVel.x,
    next.ballVel.y,
    next.ballVel.z,
    next.spinRateRpm,
    next.spinAxisTiltDeg,
    next.carryDistance,
    next.totalDistance,
    next.offlineDistance,
    next.apexHeight,
  ];

  if (finiteValues.some((value) => !Number.isFinite(value))) {
    const reset = createInitialState({
      ballPos: { x: 0, y: p.groundY + p.ballRadius, z: 0 },
      phase: "rest",
    });
    updateCompatibilityFields(reset);
    return reset;
  }

  updateCompatibilityFields(next);
  return next;
}
