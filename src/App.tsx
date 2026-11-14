// Top-level screen: loads the data once, keeps the current stage, and lays out
// the header, the guided step bar, the map and the side panel.

import { useEffect, useState } from 'react';
import { loadMissionData, type MissionData } from './data/loadMissionData';
import type { StageId, HazardProperties } from './data/types';
import { MarsMap } from './map/MarsMap';
import { routesFor } from './map/stageFilters';
import { DEFAULT_LAYERS, type LayerVisibility } from './map/layers';
import { StagePanel } from './components/StagePanel';
import { ErrorBanner, DataBadge } from './components/IssuesBanner';
import { LayerToggles } from './components/LayerToggles';
import { StageNav } from './components/StageNav';
import { MissionBrief } from './components/MissionBrief';
import { appLogger } from './lib/appLogger';

const ROUTE_STATUS_TEXT = {
  no_viable_route: 'No safe route was found',
  backup_unavailable: 'No independent backup route was found',
  inspection_required: 'This route needs inspection before use',
} as const;

export function App() {
  const [data, setData] = useState<MissionData | null>(null);
  const [stage, setStage] = useState<StageId>('orbital');
  const [layers, setLayers] = useState<LayerVisibility>(DEFAULT_LAYERS);
  const [selectedHazard, setSelectedHazard] = useState<HazardProperties | null>(null);
  const [showBrief, setShowBrief] = useState(true);

  // Runs once when the page opens: fetch every data file.
  useEffect(() => {
    loadMissionData(import.meta.env.BASE_URL, appLogger).then(setData);
  }, []);

  // Log each stage the viewer reaches, plus the safety-relevant things that stage shows.
  // Runs only when the stage (or the data) changes, never on every render or click.
  useEffect(() => {
    if (!data?.mission || !data.routes) return;
    const { mission, routes } = data;
    // "mission_stage", not "stage": the logger's own `stage` field names the app area.
    appLogger.info('ui', 'stage.change', { mission_stage: stage });

    for (const f of routesFor(stage, routes, mission).features) {
      if (f.properties.status !== 'ok') {
        appLogger.warn('safety', 'route.unavailable', { mission_stage: stage, route_id: f.properties.id, status: f.properties.status });
      }
    }
    if (stage === 'rover') {
      const d = mission.discovery;
      appLogger.info('safety', 'discovery.request_input', {
        discovery_id: d.id,
        hazard_id: d.hazard_id,
        decision: d.decision,
        evidence: d.evidence, // always "simulated" for robot observations
        uncertainty: d.uncertainty,
        chosen_option: d.chosen_option === '' ? 'pending' : d.chosen_option,
      });
    }
  }, [stage, data]);

  if (!data) return <div className="loading">Loading mission data…</div>;

  const { mission, hazards, routes, coverage, hiriseBounds, slopeBounds } = data;
  const ready = mission && hazards && routes && coverage;

  // A layer can only be switched on if its data exists.
  const available = { hirise: hiriseBounds !== null, slope: slopeBounds !== null, hazards: true, coverage: true };

  // Honest failures from the pipeline (e.g. no backup route) are shown in words.
  const routeNotices =
    ready
      ? routesFor(stage, routes, mission).features
          .filter((f) => f.properties.status !== 'ok')
          .map((f) => `${ROUTE_STATUS_TEXT[f.properties.status as keyof typeof ROUTE_STATUS_TEXT]} (${f.properties.kind.replace('_', ' ')}).`)
      : [];

  const changeStage = (next: StageId) => {
    setStage(next);
    setSelectedHazard(null); // the clicked hazard may not exist in the new stage
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="title">Terps To Mars</span>
          <span className="subtitle">Marswalk planner · {mission ? mission.site.name : 'no mission loaded'}</span>
        </div>
        <div className="topbar-actions">
          <DataBadge issues={data.issues} placeholderFiles={data.placeholderFiles} />
          <button className="link-btn" onClick={() => setShowBrief(true)}>About this mission</button>
        </div>
      </header>

      <ErrorBanner issues={data.issues} />

      {ready ? (
        <>
          <StageNav stage={stage} onChange={changeStage} />
          <main className="layout">
            <MarsMap
              stage={stage}
              mission={mission}
              hazards={hazards}
              routes={routes}
              coverage={coverage}
              hiriseBounds={hiriseBounds}
              slopeBounds={slopeBounds}
              layers={layers}
              onSelectHazard={setSelectedHazard}
            />
            <StagePanel
              stage={stage}
              mission={mission}
              selectedHazard={selectedHazard}
              onCloseHazard={() => setSelectedHazard(null)}
              routeNotices={routeNotices}
              toggles={<LayerToggles layers={layers} available={available} onChange={setLayers} />}
            />
          </main>
        </>
      ) : (
        <div className="loading">Core data files are missing; see the errors above.</div>
      )}

      {showBrief && mission && (
        <MissionBrief
          siteName={mission.site.name}
          isDemoData={data.placeholderFiles.length > 0}
          onStart={() => {
            setShowBrief(false);
            changeStage('orbital');
          }}
        />
      )}
    </div>
  );
}
