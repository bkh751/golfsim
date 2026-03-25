function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function average(values) {
  if (values.length === 0) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

export function compareShotMetrics(measuredShots, simulatedShots) {
  const count = Math.min(measuredShots.length, simulatedShots.length);
  const carryErrors = [];
  const apexErrors = [];
  const offlineErrors = [];

  for (let i = 0; i < count; i += 1) {
    carryErrors.push((measuredShots[i].carry ?? 0) - (simulatedShots[i].carry ?? 0));
    apexErrors.push((measuredShots[i].apex ?? 0) - (simulatedShots[i].apex ?? 0));
    offlineErrors.push((measuredShots[i].offline ?? 0) - (simulatedShots[i].offline ?? 0));
  }

  return {
    sampleCount: count,
    meanCarryError: average(carryErrors),
    meanApexError: average(apexErrors),
    meanOfflineError: average(offlineErrors),
  };
}

export function suggestParameterUpdates(currentParams, fitReport) {
  const nextParams = { ...currentParams };
  const carryGain = clamp(fitReport.meanCarryError * 0.0008, -0.08, 0.08);
  const apexGain = clamp(fitReport.meanApexError * 0.0015, -0.08, 0.08);
  const offlineGain = clamp(fitReport.meanOfflineError * 0.002, -0.12, 0.12);

  nextParams.dragCoeff = clamp(
    currentParams.dragCoeff * (1 - carryGain),
    currentParams.dragCoeff * 0.75,
    currentParams.dragCoeff * 1.25
  );
  nextParams.magnusCoeff = clamp(
    currentParams.magnusCoeff * (1 + apexGain),
    currentParams.magnusCoeff * 0.7,
    currentParams.magnusCoeff * 1.3
  );
  nextParams.sideMagnusScale = clamp(
    currentParams.sideMagnusScale * (1 + offlineGain),
    currentParams.sideMagnusScale * 0.65,
    currentParams.sideMagnusScale * 1.35
  );

  return nextParams;
}
