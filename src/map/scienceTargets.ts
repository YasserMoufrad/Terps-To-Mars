import type { Evidence, LatLon, ScarpLines } from '../data/types.ts';
import { normalizeLon, insideAny, scarpFocus } from './scarpTarget.ts';

export interface ScienceTarget {
  id: string; name: string; edge_id: string; foot_id: string; objective: string; source: string; evidence: Evidence;
}
export interface ScienceTargets {
  schema_version: '1.0'; status: 'unresolved' | 'selected'; active_id: string | null; targets: ScienceTarget[];
}
export interface InspectionTarget {
  id: string; name: string; target: LatLon | null; bounds: [[number, number], [number, number]] | null;
  source: string; evidence: Evidence; note: string; reason?: string; geometry?: ScarpLines; science_target_id?:string;
}
export const DEFAULT_SCIENCE_TARGETS: ScienceTargets = {
  schema_version: '1.0', status: 'unresolved', active_id: null,
  targets: [
    { id: 'original-scarp', name: 'Original traced scarp', edge_id: 'scarp-edge', foot_id: 'scarp-foot',
      objective: 'Inspect the original traced scarp; active mission objective is unresolved.',
      source: 'scarp_lines.geojson (HiRISE trace)', evidence: 'inferred' },
    { id: 'upper-scarp', name: 'Second / upper scarp', edge_id: 'upper-scarp-edge', foot_id: 'upper-scarp-foot',
      objective: 'Inspect the separately traced upper scarp if published; blue color alone is not ice confirmation.',
      source: 'scarp_lines.geojson; proposed on draft PR #17', evidence: 'inferred' },
  ],
};

export function checkScienceTargets(raw: unknown): ScienceTargets | null {
  // raw is optional target metadata; an active ID must refer to a declared stable target.
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as ScienceTargets;
  if (r.schema_version !== '1.0' || !['selected', 'unresolved'].includes(r.status) || !Array.isArray(r.targets)) return null;
  if (r.targets.some(t => !t || ['id','name','edge_id','foot_id','objective','source'].some(k => typeof t[k as keyof ScienceTarget] !== 'string' || !t[k as keyof ScienceTarget])
    || !['nasa_derived','inferred','simulated'].includes(t.evidence))) return null;
  if (new Set(r.targets.map(t => t.id)).size !== r.targets.length) return null;
  if (r.status === 'selected' && !r.targets.some(t => t.id === r.active_id)) return null;
  if (r.status === 'unresolved' && r.active_id !== null) return null;
  return r;
}

export function resolveScienceTarget(spec: ScienceTarget, lines: ScarpLines | null,
  coverage: {south:number;west:number;north:number;east:number}[]): InspectionTarget {
  // Pair IDs resolve geographic evidence; never substitute the image centre or an observation waypoint.
  const features = (lines?.features ?? []).filter(f => [spec.edge_id,spec.foot_id].includes(f.properties.id));
  const edge = features.find(f => f.properties.id === spec.edge_id);
  const foot = features.find(f => f.properties.id === spec.foot_id);
  const base = { id: spec.id, name: spec.name, source: spec.source, evidence: spec.evidence, note: spec.objective };
  if (!edge || !foot) return {...base, target:null, bounds:null, reason:'This scarp edge/foot pair is not published on this branch.'};
  const alias: ScarpLines = {type:'FeatureCollection',schema_version:'1.0',features:[
    {...edge,properties:{...edge.properties,id:'scarp-edge'}}, {...foot,properties:{...foot.properties,id:'scarp-foot'}},
  ]};
  const focus = scarpFocus(alias);
  const positions = features.flatMap(f => f.geometry.coordinates).map(([lon,lat]) => [normalizeLon(lon),lat]);
  if (!focus || !positions.every(([lon,lat]) => Number.isFinite(lon) && Number.isFinite(lat) && lat>=-90 && lat<=90)) {
    return {...base,target:null,bounds:null,reason:'Scarp geometry has no valid geographic focus.'};
  }
  if (!insideAny(focus, coverage)) return {...base,target:null,bounds:null,reason:'Selected scarp focus is outside published high-resolution imagery.'};
  return {...base,target:focus, bounds:[
    [Math.min(...positions.map(p=>p[1])),Math.min(...positions.map(p=>p[0]))],
    [Math.max(...positions.map(p=>p[1])),Math.max(...positions.map(p=>p[0]))],
  ], geometry:{type:'FeatureCollection',schema_version:'1.0',features}};
}

export function activeScienceTarget(catalog: ScienceTargets, targets: InspectionTarget[]): InspectionTarget {
  // A science objective is a team decision; unresolved selection cannot silently choose the original scarp.
  const resolved=targets.find(t => catalog.status==='selected' && t.id===catalog.active_id);
  return resolved?{...resolved,id:'active',science_target_id:resolved.id}:{
    id:'active',name:'Active science target — unresolved',target:null,bounds:null,source:'science_targets.json',
    evidence:'inferred',note:'The team has not selected a reviewed active scarp ID.',
    reason:'Science target unresolved. Select a named scarp to inspect its geometry without declaring it the mission target.',
  };
}

export function pointInspection(id:string,name:string,point:LatLon,source:string,evidence:Evidence): InspectionTarget {
  // point is the actual published waypoint/incident; bounds supply a 40 m framing radius on Mars.
  const dy=40/3389500*180/Math.PI, dx=dy/Math.max(.01,Math.cos(point.lat*Math.PI/180));
  return {id,name,target:point,bounds:[[point.lat-dy,point.lon-dx],[point.lat+dy,point.lon+dx]],
    source,evidence,note:'Published coordinate, not a terrain-clearance claim.'};
}
