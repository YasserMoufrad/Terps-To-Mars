import type { RouteAudit } from '../data/types';
import { currentEntry, distance, type Inspection } from '../map/routeInspection';
import { diagnosticRows, profileSvg } from '../map/routeAudit';
import { measured } from '../data/analysis';

export function RouteInspector({selection,audit,onClose}:{selection:Inspection;audit:RouteAudit|null;onClose:()=>void}) {
  // Selection retains route identity and exact clicked cell independently of mission stage.
  const entry=selection.route?currentEntry(audit,selection.route):null, cell=selection.cell;
  const state=audit?.freshness??'missing';
  const rows=entry?diagnosticRows(entry):[];
  return <section className="route-inspector" aria-label="Geographic inspector">
    <button className="link-btn inspector-close" onClick={onClose}>Close inspector</button><h2>{selection.name}</h2>
    <p>{selection.source} · {selection.evidence} · {state}</p>
    {selection.point && <p>Clicked: {selection.point.lat.toFixed(6)}°, {selection.point.lon.toFixed(6)}°</p>}
    {selection.route && <>
      <p>File claims: {selection.route.properties.status}. Audit: {entry?.audit_status??(state==='stale'?'Stale — requires regeneration':'Not measured')}. Crew clearance: not established.</p>
      <dl className="inspection-fields">{rows.map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      {entry && <><p>Objective: {entry.objective??'Undeclared'} · Direction: {entry.orientation??'Not measured'}</p>
        <p>Start: {selection.route.geometry.coordinates[0]?.join(', ')??'Not measured'} · End: {selection.route.geometry.coordinates.at(-1)?.join(', ')??'Not measured'}</p>
        <p>Vertices: {selection.route.geometry.coordinates.length} · Mode thresholds: walk {audit?.thresholds_deg.crew_exclude}°, drive {audit?.thresholds_deg.rover_exclude}° (provisional)</p>
        <p>First exclusion along route: {measured(entry.first_exclusion_at_m,' m')} · actual cell: {entry.first_exclusion?.coordinates?.join(', ')??'Not measured'}</p>
        <ul>{entry.reasons.map(r=><li key={r}>{r}</li>)}</ul>
        <div dangerouslySetInnerHTML={{__html:profileSvg(entry.profile,audit?.thresholds_deg.crew_caution??15,(entry.agent==='rover'?audit?.thresholds_deg.rover_exclude:audit?.thresholds_deg.crew_exclude)??20)}}/>
      </>}
    </>}
    {selection.details!==undefined && <details open><summary>Waypoint purpose, uncertainty and restrictions</summary><pre>{JSON.stringify(selection.details,null,2)}</pre></details>}
    <h3>Local sample</h3>
    {cell ? <><p>Native crossed cell [{cell.col}, {cell.row}] · {selection.route?'segment '+(cell.segment_index+1):'sparse terrain sample'} · {cell.coordinates[1].toFixed(6)}°, {cell.coordinates[0].toFixed(6)}°</p>
      <dl className="inspection-fields">
        <div><dt>Sample offset from click</dt><dd>{selection.point?measured(distance(cell.coordinates,selection.point),' m'):'Not applicable'}</dd></div>
        <div><dt>Elevation</dt><dd>{measured(cell.elevation,' m')}</dd></div>
        <div><dt>Slope</dt><dd>{measured(cell.slope,'°')}</dd></div>
        <div><dt>Roughness (local elevation range)</dt><dd>{measured(cell.roughness_m,' m')}</dd></div>
        <div><dt>Travel mode / threshold</dt><dd>{cell.mode} / {measured(cell.limit,'°')}</dd></div>
        <div><dt>Quality</dt><dd>{!cell.inside?'Outside assessed terrain':!cell.known?'Unknown':cell.on_scarp_face || cell.slope!==null&&cell.slope>=cell.limit?'Excluded under model':'Below slope exclusion; inspection required'}</dd></div>
      </dl></>:<p>Not measured. Select a route segment with a current native-cell audit, or inspect a terrain sample.</p>}
    <p>No reviewed artifact mask. Valid DTM samples may contain stereo artifacts. Vertical uncertainty not measured; roughness classification provisional. No interpolation or crew clearance.</p>
  </section>;
}
