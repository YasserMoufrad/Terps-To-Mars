// "What it looks like on the ground": a real NASA lander photo for the current stage,
// always labeled as example terrain from another site, with credit and a source link.

import { useState } from 'react';
import type { StageId } from '../data/types';
import { appLogger } from '../lib/appLogger';
import { EXAMPLE_LABEL, groundViewsFor } from '../content/groundViews';

export function GroundViewCard({ stage }: { stage: StageId }) {
  // Purpose: show the example photo(s) for `stage`. `failed` holds ids whose image did
  // not load; those show a text link instead, and the failure is logged once per photo.
  const [failed, setFailed] = useState<string[]>([]);
  const views = groundViewsFor(stage);
  if (views.length === 0) return null;

  return (
    <section className="card ground-view">
      <h3>What it looks like on the ground</h3>
      {views.map((v) => (
        <figure key={v.id}>
          <div className="example-tag">{EXAMPLE_LABEL}</div>
          {failed.includes(v.id) ? (
            <p className="muted">Photo could not load. <a href={v.pageUrl} target="_blank" rel="noreferrer">Open it on NASA Photojournal</a>.</p>
          ) : (
            <a href={v.pageUrl} target="_blank" rel="noreferrer">
              <img
                src={v.imageUrl}
                alt={`${v.title} (${v.mission})`}
                loading="lazy"
                onError={() => {
                  // A missing outside image is a missing layer (section 16): log it once.
                  appLogger.warn('content', 'ground_view.load_error', { photo_id: v.id, url: v.imageUrl });
                  setFailed((f) => (f.includes(v.id) ? f : [...f, v.id]));
                }}
              />
            </a>
          )}
          <figcaption>
            <strong>{v.title}</strong> · {v.mission}
            <br />
            {v.shows}
            <br />
            <span className="muted">
              {v.id}, {v.credit}
            </span>
          </figcaption>
        </figure>
      ))}
    </section>
  );
}
