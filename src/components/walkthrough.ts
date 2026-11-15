import type { StageId } from '../data/types.ts';
import type { Logger } from '../lib/logger.ts';
import type { StageSummary } from '../map/stageSummary.ts';

export const WALKTHROUGH_GUIDANCE: Record<StageId, { instruction: string; action: string }> = {
  orbital: {
    instruction: 'Select the gray preliminary route to read its distance and terrain audit. Turn on Slope map in the layers panel to see mapped constraints; ground hazards remain unresolved.',
    action: 'Inspect preliminary route',
  },
  rover: {
    instruction: 'Locate the simulated rover incident, then use Replay on the map to compare Before the incident with After the reroute. This is a static preview, not live rover control.',
    action: 'Locate rover incident',
  },
  drone: {
    instruction: 'Find the proposed drone perch and its planned field of view. Compare it with unresolved ground; no drone flight has occurred.',
    action: 'Show drone perch',
  },
  eva: {
    instruction: 'Inspect the crew route and then select the backup in Inspect route. Compare distance, slope, and uncertainty before reviewing the science objective and pending crew decision.',
    action: 'Inspect crew route',
  },
};

export function recapRoutes(summary: StageSummary): { main: string; backup: string } {
  // Read the current EVA summary's route states; never infer clearance from green styling.
  return {
    main: summary.rows.find((row) => row.label === 'Main route')?.value ?? 'No main route assessment supplied',
    backup: summary.rows.find((row) => row.label === 'Backup')?.value ?? 'No backup assessment supplied',
  };
}

export function logWalkthroughTransition(logger: Logger, action: 'finish' | 'restart', stage: StageId): void {
  // Record a tour state change with the shared run ID and an explicit no-clearance outcome.
  logger.info('ui', `walkthrough.${action}`, { mission_stage: stage, crew_clearance: 'not_established' });
}
