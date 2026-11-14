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
  orbital: 'Review preliminary orbital candidates and modeled hazards. Dashed candidate lines require inspection; later discoveries are not yet included.',
  rover: 'The simulated rover stopped at the red marker: suspected soft ground. Compare the previous route with the proposed alternative and its reported status.',
  drone: 'Review the drone concept, available coverage evidence, and inspection limits. A proposed perch does not establish a flight or checked field of view.',
  eva: 'Review the proposed route, the post-discovery backup assessment, and the evidence behind each hazard. Route geometry is not crew clearance.',
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
