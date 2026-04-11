export const SESSION_KIND_RANGE = "range";
export const SESSION_KIND_PUTTER = "putter";
export const DEFAULT_SESSION_KIND = SESSION_KIND_RANGE;
export const SESSION_MODE_STORAGE_KEY = "golfsim.sessionKind";

export function normalizeSessionKind(value) {
  return value === SESSION_KIND_PUTTER ? SESSION_KIND_PUTTER : SESSION_KIND_RANGE;
}

export function persistSessionKind(kind, storage = globalThis?.localStorage) {
  const normalized = normalizeSessionKind(kind);
  try {
    storage?.setItem?.(SESSION_MODE_STORAGE_KEY, normalized);
  } catch {}
  return normalized;
}

export function restoreSessionKind(storage = globalThis?.localStorage) {
  try {
    return normalizeSessionKind(storage?.getItem?.(SESSION_MODE_STORAGE_KEY));
  } catch {
    return DEFAULT_SESSION_KIND;
  }
}

export function buildSessionReplaySnapshot({
  currentShot = null,
  previousShot = null,
  recentShots = [],
  detachedFlights = [],
}) {
  return {
    currentShotNo: currentShot?.shotNo ?? null,
    previousShotNo: previousShot?.shotNo ?? null,
    recentShotCount: recentShots.length,
    recentShotNos: recentShots.map((record) => record?.shotNo).filter(Number.isFinite),
    detachedFlightCount: detachedFlights.length,
    detachedFlightShotNos: detachedFlights.map((flight) => flight?.shotNo).filter(Number.isFinite),
  };
}

function buildRangeInputSnapshot({ aimDeg, yawDeg, manualLaunch = {} }) {
  return {
    kind: SESSION_KIND_RANGE,
    aimDeg: Number.isFinite(aimDeg) ? Number(aimDeg.toFixed(2)) : 0,
    yawDeg: Number.isFinite(yawDeg) ? Number(yawDeg.toFixed(2)) : 0,
    manualLaunch: {
      ballSpeedMps: manualLaunch.ballSpeedMps == null ? null : Number(manualLaunch.ballSpeedMps.toFixed(2)),
      ballSpeedMph: manualLaunch.ballSpeedMps == null ? null : Number((manualLaunch.ballSpeedMps * 2.2369362920544).toFixed(2)),
      backspinRpm: manualLaunch.backspinRpm == null ? null : Number(manualLaunch.backspinRpm.toFixed(0)),
      sideSpinRpm: manualLaunch.sideSpinRpm == null ? null : Number(manualLaunch.sideSpinRpm.toFixed(0)),
    },
  };
}

function buildPutterInputSnapshot({ putt }) {
  return {
    kind: SESSION_KIND_PUTTER,
    holeDistanceM: Number(putt.holeDistanceM.toFixed(2)),
    greenDecel: Number(putt.greenDecel.toFixed(2)),
    manualStrokeSpeedMps: Number(putt.manualStrokeSpeedMps.toFixed(2)),
    motion: {
      supported: Boolean(putt.motion?.supported),
      permission: putt.motion?.permission ?? "idle",
      calibrated: Boolean(putt.motion?.calibrated),
      armed: Boolean(putt.motion?.armed),
      pendingStroke: putt.motion?.pendingStroke ?? null,
      lastStroke: putt.motion?.lastStroke ?? null,
    },
  };
}

export function buildSessionContractPayload({
  sessionKind,
  mode,
  totalShots,
  distanceUnit,
  autoResetTimer,
  currentShot = null,
  previousShot = null,
  recentShots = [],
  detachedFlights = [],
  aimDeg,
  yawDeg,
  manualLaunch,
  putt,
}) {
  const normalizedKind = normalizeSessionKind(sessionKind);
  const currentShotKind = currentShot?.sessionKind ? normalizeSessionKind(currentShot.sessionKind) : null;
  return {
    version: 1,
    selection: {
      storageKey: SESSION_MODE_STORAGE_KEY,
      currentKind: normalizedKind,
      defaultKind: DEFAULT_SESSION_KIND,
      persistedKind: normalizedKind,
      distanceUnit,
    },
    transition: {
      mode,
      totalShots,
      autoResetTimer: Number.isFinite(autoResetTimer) ? Number(autoResetTimer.toFixed(2)) : 0,
      canLaunch: mode === "session_ready",
      canInterrupt: mode === "launching" || mode === "in_flight" || mode === "rollout",
    },
    replay: buildSessionReplaySnapshot({
      currentShot,
      previousShot,
      recentShots,
      detachedFlights,
    }),
    input: normalizedKind === SESSION_KIND_PUTTER
      ? buildPutterInputSnapshot({ putt })
      : buildRangeInputSnapshot({ aimDeg, yawDeg, manualLaunch }),
    result: {
      currentShotAvailable: Boolean(currentShot),
      previousShotAvailable: Boolean(previousShot),
      comparisonAvailable: Boolean(currentShot && previousShot),
      currentShotKind,
    },
  };
}
