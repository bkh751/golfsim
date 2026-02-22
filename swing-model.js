const DEG_TO_RAD = Math.PI / 180;
const RAD_TO_DEG = 180 / Math.PI;

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
  spinMax: 4800,
  gravity: 28,
  dragCoeff: 0.0011,
  liftCoeff: 0.014,
  bounceRestitution: 0.32,
  rollFriction: 0.985,
  stopVx: 12,
  stopVy: 10,
  windMin: -12,
  windMax: 12,
  ballRadius: 9,
  groundY: 410,
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
  const attackAngleDeg = Math.atan2(-vy, Math.max(0.001, vx)) * RAD_TO_DEG;

  return {
    clubHeadSpeed: speed,
    attackAngleDeg,
  };
}

export function createInitialState(overrides = {}) {
  return {
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
    impactQuality: 1,
    spinRpm: 0,
    didImpact: false,
    ballX: 110,
    ballY: 400,
    ballVx: 0,
    ballVy: 0,
    ballMoving: false,
    launchX: 110,
    apexY: 400,
    ...overrides,
  };
}

export function createDefaultControls(overrides = {}) {
  return {
    initiateSwing: false,
    powerNorm: 0.5,
    tempoNorm: 0.7,
    aimDeg: 14,
    loftDeltaDeg: 0,
    strikeOffset: 0,
    windX: 0,
    ...overrides,
  };
}

export function stepSwingModel(state, controls = {}, params = {}, dt = 1 / 60) {
  const safeDt = clampFinite(dt, 1 / 60, 1e-6, 0.1);
  const p = { ...DEFAULT_PARAMS, ...params };
  const uRaw = { ...createDefaultControls(), ...controls };
  const u = {
    ...uRaw,
    powerNorm: clampFinite(uRaw.powerNorm, 0.5, 0, 1),
    tempoNorm: clampFinite(uRaw.tempoNorm, 0.7, 0.4, 1.3),
    aimDeg: clampFinite(uRaw.aimDeg, 14, 4, 45),
    loftDeltaDeg: clampFinite(uRaw.loftDeltaDeg, 0, -8, 8),
    strikeOffset: clampFinite(uRaw.strikeOffset, 0, -0.35, 0.35),
    windX: clampFinite(uRaw.windX, 0, p.windMin, p.windMax),
  };

  const next = { ...state };
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
    next.impactQuality = clamp(1 - Math.abs(u.strikeOffset) * 1.8, 0.25, 1);
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
      (tauArm - p.armDamping * next.omegaArm - p.armStiffness * (next.thetaArm - targets.arm)) /
      p.armInertia;
    const dOmegaClub =
      (tauClub - p.clubDamping * next.omegaClub - p.clubStiffness * (next.thetaClub - targets.club)) /
      p.clubInertia;

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
      const smash = clamp(
        p.smashMin + (p.smashMax - p.smashMin) * (0.48 + 0.52 * u.powerNorm) - Math.abs(u.strikeOffset) * 0.14,
        p.smashMin,
        p.smashMax
      );
      const ballSpeed = clamp(smash * next.clubHeadSpeed, 15, 110);
      const dynamicLoftDeg =
        p.loftBaseDeg + u.loftDeltaDeg + p.attackLoftCoupling * next.attackAngleDeg - Math.abs(u.strikeOffset) * 2.4;
      const launchDeg = clamp(
        u.aimDeg + 0.22 * next.attackAngleDeg + 0.5 * dynamicLoftDeg - p.strikeLaunchPenalty * u.strikeOffset,
        4,
        44
      );
      const spinRpm = clamp(
        p.spinBase + (dynamicLoftDeg - next.attackAngleDeg) * p.spinLoftGain + u.strikeOffset * p.strikeSpinGain,
        p.spinMin,
        p.spinMax
      );
      const launchRad = launchDeg * DEG_TO_RAD;

      next.ballVx = ballSpeed * Math.cos(launchRad);
      next.ballVy = -ballSpeed * Math.sin(launchRad);
      next.ballMoving = true;
      next.phase = "flight";
      next.didImpact = true;
      next.dynamicLoftDeg = dynamicLoftDeg;
      next.launchDeg = launchDeg;
      next.spinRpm = spinRpm;
      next.launchX = next.ballX;
      next.apexY = next.ballY;
    }
  }

  if (next.phase === "flight") {
    const speed = Math.max(0.001, Math.hypot(next.ballVx, next.ballVy));
    const spinFactor = next.spinRpm / 3500;

    const ax = u.windX - p.dragCoeff * speed * next.ballVx;
    const ay = p.gravity - p.dragCoeff * speed * next.ballVy - p.liftCoeff * spinFactor * Math.abs(next.ballVx);

    next.ballVx += ax * safeDt;
    next.ballVy += ay * safeDt;

    next.ballX += next.ballVx * safeDt;
    next.ballY += next.ballVy * safeDt;
    next.apexY = Math.min(next.apexY, next.ballY);

    if (next.ballY + p.ballRadius >= p.groundY) {
      next.ballY = p.groundY - p.ballRadius;
      next.ballVy *= -p.bounceRestitution * (0.68 + 0.32 * next.impactQuality);
      next.ballVx *= p.rollFriction;

      if (Math.abs(next.ballVy) < p.stopVy) next.ballVy = 0;
      if (Math.abs(next.ballVx) < p.stopVx && Math.abs(next.ballVy) < p.stopVy) {
        next.ballVx = 0;
        next.ballVy = 0;
        next.ballMoving = false;
        next.phase = "rest";
      }
    }
  }

  if (next.phase !== "flight") {
    next.ballMoving = false;
  }

  if (!Number.isFinite(next.ballX) || !Number.isFinite(next.ballY)) {
    return {
      ...createInitialState({ ballX: 110, ballY: p.groundY - p.ballRadius }),
      phase: "rest",
    };
  }

  return next;
}
