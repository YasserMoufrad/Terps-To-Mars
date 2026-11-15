import L from 'leaflet';
import { useState } from 'react';
import { useMap } from 'react-leaflet';
import type { LatLon, OverlayBounds, StageId } from '../data/types';
import { appLogger } from '../lib/appLogger';
import { collectPositions } from './FitToMission';
import { IMAGERY_STATUS_TEXT, SAMPLING_DISCLOSURE, type ImageryLoadState } from './imageryState';
import type { InspectionTarget } from './scienceTargets';

interface ImageryControlsProps {
  overview:{geometries:unknown[];points:LatLon[]}; hiriseBounds:OverlayBounds|null;
  targets:InspectionTarget[]; stage:StageId; state:ImageryLoadState; registration:string; onRetry:()=>void;
  onInspect:(target:InspectionTarget|null)=>void; slopeOpacity:number; onOpacity:(value:number)=>void;
}

export function ImageryControls({overview,hiriseBounds,targets,stage,state,registration,onRetry,onInspect,slopeOpacity,onOpacity}:ImageryControlsProps) {
  // targets are geographic inspection choices; stage is independent and never changed by map navigation.
  const map=useMap(), [choice,setChoice]=useState('active'), [viewport,setViewport]=useState('Stage overview');
  const selected=targets.find(t=>t.id===choice) ?? targets[0];
  const narrow=typeof window!=='undefined' && window.matchMedia?.('(max-width: 640px)').matches;
  const reason=selected?.reason ?? (!selected?.target ? 'Target not available.' : undefined);
  const inspect=() => {
    // selected bounds come from the actual feature; asymmetric padding leaves space for map controls.
    if (!selected?.target || !selected.bounds || reason) return;
    const size=map.getSize(), left=Math.min(45,size.x*.12), top=Math.min(narrow?220:170,size.y*.4);
    map.flyToBounds(selected.bounds,{maxZoom:17,paddingTopLeft:[left,top],paddingBottomRight:[35,55]});
    onInspect(selected); setViewport(selected.name);
    appLogger.info('map','view.inspect_target',{target_id:selected.science_target_id??selected.id,target:selected.target,bounds:selected.bounds,
      source:selected.source,evidence:selected.evidence,mission_stage:stage});
  };
  const overviewView=() => {
    // overview contains this stage's geometry, keeping a rover incident distinct from the scarp view.
    const positions:[number,number][]=overview.points.map(p=>[p.lat,p.lon]);
    for (const g of overview.geometries) collectPositions(g,positions);
    if (positions.length>1) map.flyToBounds(positions,{padding:[45,65],maxZoom:16});
    onInspect(null);setViewport('Stage overview');
    appLogger.info('map','view.overview',{points:positions.length,mission_stage:stage});
  };
  const locateIncident=() => {
    // The rover coordinate is a simulated observation, not the currently selected scarp.
    const incident=targets.find(t=>t.id==='discovery');
    if (!incident?.target || !incident.bounds) return;
    map.flyToBounds(incident.bounds,{maxZoom:17,padding:[45,85]});
    onInspect(incident);setViewport(incident.name);setChoice('discovery');
    appLogger.info('map','view.rover_incident',{target:incident.target,evidence:'simulated',mission_stage:stage});
  };
  return <div className="leaflet-top leaflet-right"><div className="leaflet-control imagery-controls" ref={node=>{if(node){L.DomEvent.disableClickPropagation(node);L.DomEvent.disableScrollPropagation(node);}}}>
    <div className="imagery-buttons">
      <button type="button" onClick={overviewView}>Stage overview</button>
      <label>Inspect <select aria-label="Inspection target" value={choice} onChange={e=>setChoice(e.target.value)}>
        {targets.map(t=><option key={t.id} value={t.id}>{t.name}</option>)}
      </select></label>
      <button type="button" onClick={inspect} disabled={Boolean(reason)} title={reason??selected?.note}>Inspect selected</button>
      <button type="button" onClick={locateIncident}>Locate rover incident</button>
    </div>
    <p className="inspection-context">Stage: {stage} · Viewport: {viewport}</p>
    {reason && <p className="imagery-reason">{reason}</p>}
    {selected?.target && <p className="inspection-coordinates">{selected.name}: {selected.target.lat.toFixed(6)}°, {selected.target.lon.toFixed(6)}° · {selected.evidence}<br/>{selected.source}</p>}
    <label className="slope-opacity">Slope opacity <input aria-label="Slope opacity" type="range" min="0.1" max="0.85" step="0.05" value={slopeOpacity} onChange={e=>onOpacity(Number(e.target.value))}/>{Math.round(slopeOpacity*100)}%</label>
    {(hiriseBounds!==null || state!=='unavailable') && <div className="imagery-status" role="status" aria-live="polite">
      <span className={'imagery-state imagery-'+state}>HiRISE: {IMAGERY_STATUS_TEXT[state]}</span>
      {(state==='failed'||state==='partial') && <button type="button" className="link-btn" onClick={onRetry}>Retry</button>}
      <details className="imagery-notes" open={!narrow}><summary>Image source and alignment</summary><p>{SAMPLING_DISCLOSURE}</p><p>{registration}</p></details>
    </div>}
  </div></div>;
}
