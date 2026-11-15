// "Detected by": which instrument found a hazard. The rover's discovery names the scout's (simulated) sensors from
// mission.discovery.sensor_evidence; everything else names its orbital source. Pure, so the Node tests can check it.

import type { HazardProperties, Mission } from '../data/types.ts';

const SENSOR_NAMES: Record<string, (v: string | number) => string> = {
  // Known sensor_evidence keys, written as instrument + reading.
  wheel_slip_pct: (v) => `wheel-slip sensor (${v}% slip)`,
  thermal: () => 'thermal camera (surface cooler than surroundings)',
  stereo_cam: () => 'stereo cameras',
};

export function detectedBy(hazard: HazardProperties, mission: Mission | null): string {
  // Purpose: one line naming the instrument(s) behind `hazard`, labelled simulated / NASA-derived / inferred.
  if (mission && hazard.id === mission.discovery.hazard_id) {
    // Fixed order (SENSOR_NAMES): wheel slip first, the reading that stopped the rover.
    const evidence = mission.discovery.sensor_evidence ?? {};
    const sensors = Object.keys(SENSOR_NAMES).filter((k) => k in evidence).map((k) => SENSOR_NAMES[k](evidence[k]));
    return `Scout rover (simulated): ${sensors.length ? sensors.join(' + ') : 'onboard sensors'}`;
  }
  if (hazard.evidence === 'simulated') return 'Robot sensors (simulated)';
  if (hazard.category === 'slope' || hazard.category === 'no_data') return 'From orbit: HiRISE stereo elevation model (DTM) slope, NASA-derived';
  if (hazard.category === 'shadow') return 'From orbit: sun angle and terrain (inferred)';
  return 'From orbit: HiRISE image trace of the scarp + hazard rules (inferred)';
}
