// Severity of a mission alert line, so cautions never look like good news.
// Pure (no React) so the Node test runner can check it.

export type AlertSeverity = 'stop' | 'caution' | 'info';

const STOP = /\b(stopped|stop|blocked|no viable|unavailable|excluded|failed)\b/i;
const CAUTION = /\b(unverified|not verified|suspected|requesting|requires|inspection|uncertain|simulated|caution|below orbital|shares?)\b/i;

export function alertSeverity(text: string): AlertSeverity {
  // Purpose: classify one alert sentence. "stop" = the plan cannot proceed as drawn; "caution" = needs
  // review or rests on simulated/unverified evidence; "info" = neutral. There is deliberately no "ok"
  // level: nothing in this demo is crew clearance, so no alert is rendered green.
  if (STOP.test(text)) return 'stop';
  if (CAUTION.test(text)) return 'caution';
  return 'info';
}
