// Step bar: Back / Next plus the four numbered stages, and one plain-language
// caption telling the viewer what to look at in this step.

import { STAGE_IDS, type StageId } from '../data/types';
import { WALKTHROUGH_GUIDANCE } from './walkthrough';

const STAGE_NAMES: Record<StageId, string> = {
  orbital: 'Orbital planning',
  rover: 'Rover reconnaissance',
  drone: 'Drone inspection',
  eva: 'Astronaut mission review',
};

interface StageNavProps {
  stage: StageId;
  onChange: (stage: StageId) => void;
  onAction: (stage: StageId) => void;
  onFinish: () => void;
}

export function StageNav({ stage, onChange, onAction, onFinish }: StageNavProps) {
  // Purpose: navigate four stages, offer one map action for `stage`, then finish the walkthrough.
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
        <button className="nav-btn primary" onClick={() => next ? onChange(next) : onFinish()}>
          {next ? 'Next →' : 'Finish walkthrough'}
        </button>
      </div>
      <p className="lookfor">
        <strong>Try this on the map · Step {index + 1} of 4:</strong> {WALKTHROUGH_GUIDANCE[stage].instruction}
      </p>
      <button className="guide-action" type="button" onClick={() => onAction(stage)}>{WALKTHROUGH_GUIDANCE[stage].action} →</button>
    </div>
  );
}
