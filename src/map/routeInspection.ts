import type { RouteAudit, RouteAuditEntry, RouteFeature, LatLon } from '../data/types.ts';
import { stable } from '../data/analysis.ts';
export interface AuditCell { coordinates:[number,number];segment_index:number;distance_m:number;col:number;row:number;
  on_scarp_face?:boolean;inside:boolean;known:boolean;limit:number;mode:string;slope:number|null;elevation:number|null;roughness_m:number|null }
export interface Inspection { route:RouteFeature|null;cell:AuditCell|null;point:LatLon|null;name:string;source:string;evidence:string;details?:unknown }
export function currentEntry(audit:RouteAudit|null,route:RouteFeature):RouteAuditEntry|null {
  // Exact feature snapshot rejects same-ID geometry/property edits made after loading.
  if(audit?.freshness!=='current') return null;
  const entry=audit.routes.find(r=>r.id===route.properties.id);
  return entry && stable(entry.input_route)===stable(route) ? entry:null;
}
export function nearestCell(cells:AuditCell[],point:LatLon):AuditCell|null {
  // Choose a published crossed native DTM cell by Mars local distance, never the route-wide maximum.
  return cells.reduce<AuditCell|null>((best,c)=>distance(c.coordinates,point)<(best?distance(best.coordinates,point):Infinity)?c:best,null);
}
export function distance(coordinates:[number,number],point:LatLon):number {
  // Local tangent distance in metres; geographic selection uses the actual clicked latitude.
  return Math.hypot((coordinates[0]-point.lon)*Math.cos(point.lat*Math.PI/180),coordinates[1]-point.lat)*Math.PI/180*3389500;
}
