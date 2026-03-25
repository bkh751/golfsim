function horizontalDistance(a, b) {
  return Math.hypot(a.x - b.x, a.z - b.z);
}

export function computeTrajectoryMetrics(flightState) {
  const launch = flightState.launchPos;
  const current = flightState.position;
  const landing = flightState.firstBounceDone ? flightState.landingPos : current;

  return {
    carryDistance: flightState.firstBounceDone ? horizontalDistance(landing, launch) : 0,
    totalDistance: horizontalDistance(current, launch),
    offlineDistance: current.z - launch.z,
    apexHeight: Math.max(flightState.apexHeight, current.y),
  };
}
