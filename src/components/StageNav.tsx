// Step bar: Back / Next plus the four numbered stages, and one plain-language
// caption telling the viewer what to look at in this step.

import { STAGE_IDS, type StageId } from '../data/types';

const STAGE_NAMES: Record<StageId, string> = {
  orbital: 'Orbital planning',
  rover: 'Rover reconnaissance',
  drone: 'Drone inspection',
  eva: 'Astronaut mission review',
};

// What to look for on the map at each step.
const LOOK_FOR: Record<StageId, string> = {
  orbital: 'The amber dashed line is the first route planned from orbit: unverified, it crosses terrain too steep for a suited astronaut. Colored areas are hazards NASA data can show.',
  rover: 'The rover (dotted line) stopped at the red marker: soft ground. The gray dashed line is the old route; green is the new one.',
  drone: 'The drone images the cliff face the rover cannot see. Green lines are the confirmed main route and backup.',
  eva: 'The crew walks the solid green route to the observation point. The blue drone watches the cliff for rockfall.',
};

interface StageNavProps {
  stage: StageId;
  onChange: (stage: StageId) => void;
}

export function StageNav({ stage, onChange }: StageNavProps) {
  // Purpose: Back/Next plus the four numbered steps and the current step's caption.
  // `stage` is the current step; `onChange` moves to another one.
  const index = STAGE_IDS.indexOf(stage);
  const previous = index > 0 ? STAGE_IDS.at(index - 1) : undefined;
  const next = index < STAGE_IDS.length - 1 ? STAGE_IDS.at(index + 1) : undefined;

  return (
    <div className="stagenav">
      <div className="stagenav-row">
        <button className="nav-btn" onClick={() => previous && onChange(previous)} disabled={!previous}>
          ← Back
        </button>
        <ol className="steps">
          {STAGE_IDS.map((id, i) => (
            <li key={id}>
              <button
                className={id === stage ? 'step active' : i < index ? 'step done' : 'step'}
                onClick={() => onChange(id)}
                aria-current={id === stage ? 'step' : undefined}
              >
                <span className="step-num">{i + 1}</span>
                <span className="step-name">{STAGE_NAMES[id]}</span>
              </button>
            </li>
          ))}
        </ol>
        <button className="nav-btn primary" onClick={() => next && onChange(next)} disabled={!next}>
          Next →
        </button>
      </div>
      <p className="lookfor">
        <strong>Step {index + 1} of 4:</strong> {LOOK_FOR[stage]}
      </p>
    </div>
  );
}
