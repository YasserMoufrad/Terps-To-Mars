import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { loadAnalysis, measured } from '../src/data/analysis.ts';
import { createLogger } from '../src/lib/logger.ts';
import { currentEntry, nearestCell } from '../src/map/routeInspection.ts';
import { DEFAULT_SCIENCE_TARGETS, checkScienceTargets, resolveScienceTarget, activeScienceTarget } from '../src/map/scienceTargets.ts';
import { diagnosticRows } from '../src/map/routeAudit.ts';
import { logRouteReview } from '../src/map/reviewPresentation.ts';
const root=new URL('../public/data/',import.meta.url);
const read=f=>JSON.parse(fs.readFileSync(new URL(f,root)));
const routes=read('routes.geojson'), audit={...read('route_audit.json'),freshness:'current'};
test('zero is measured; absent, invalid and stale values are distinct',()=>{
  assert.equal(measured(0,' m'),'0 m');assert.equal(measured(null),'Not measured');
  assert.equal(measured(NaN),'Not measured');assert.match(measured(0,'','stale'),/Stale/);
});
test('every diagnostic count remains visible including zero',()=>{
  const rows=Object.fromEntries(diagnosticRows({audit_status:'candidate_requires_inspection',claimed_status:'inspection_required',cells_excluded:0,cells_unknown:0,cells_outside:0,cells_caution:0,reasons:[]}));
  assert.equal(rows['Excluded cells crossed'],'0');assert.equal(rows['Unknown cells'],'0');
  assert.equal(rows['Outside assessed terrain'],'0');assert.equal(rows['Measured length'],'Not measured');
});
test('same ID with edited geometry or claimed statistics invalidates the snapshot',()=>{
  const f=structuredClone(routes.features[0]);assert.ok(currentEntry(audit,f));
  f.geometry.coordinates[0][0]+=.001;assert.equal(currentEntry(audit,f),null);
  const g=structuredClone(routes.features[0]);g.properties.stats.length_m=0;assert.equal(currentEntry(audit,g),null);
});
test('stale, missing and empty audits never supply measurements',()=>{
  assert.equal(currentEntry({...audit,freshness:'stale'},routes.features[0]),null);
  assert.equal(currentEntry(null,routes.features[0]),null);
  assert.equal(currentEntry({...audit,routes:[]},routes.features[0]),null);
});
test('segment click selects the nearest native cell, not a route maximum',()=>{
  const cells=[{coordinates:[0,0],slope:0},{coordinates:[.01,0],slope:80}];
  assert.equal(nearestCell(cells,{lat:0,lon:0}).slope,0);
  assert.equal(nearestCell([],{lat:0,lon:0}),null);
});
test('science target remains unresolved; absent upper geometry and outside imagery disable inspection',()=>{
  assert.equal(activeScienceTarget(DEFAULT_SCIENCE_TARGETS,[]).target,null);
  const lines=read('scarp_lines.geojson');
  // The upper scarp is published since #17; removing its lines must disable it with a reason.
  const mainOnly={...lines,features:lines.features.filter(f=>!f.properties.id.startsWith('upper-'))};
  assert.match(resolveScienceTarget(DEFAULT_SCIENCE_TARGETS.targets[1],mainOnly,[]).reason,/not published/);
  assert.match(resolveScienceTarget(DEFAULT_SCIENCE_TARGETS.targets[1],lines,[]).reason,/outside/);
  assert.match(resolveScienceTarget(DEFAULT_SCIENCE_TARGETS.targets[0],lines,[]).reason,/outside/);
  assert.equal(checkScienceTargets({...DEFAULT_SCIENCE_TARGETS,status:'selected',active_id:'invented'}),null);
  assert.equal(checkScienceTargets({...DEFAULT_SCIENCE_TARGETS,schema_version:'1.1'}),null);
});
test('rejected claimed-ok geometry never logs positive feasibility',()=>{
  const events=[],logger=createLogger({runId:'science-test',sink:e=>events.push(e)});
  // No published route claims ok (the audit flags that as an overclaim), so test a copy that does.
  const claimedOk=structuredClone(routes.features.find(f=>f.properties.kind==='rover_path'));claimedOk.properties.status='ok';
  logRouteReview(logger,claimedOk,'rover',audit);
  assert.equal(events[0].geometric_feasibility,false);assert.equal(events[0].crew_clearance,'not_established');
});
test('all published bytes verify and changed mission or artifact bytes become stale',async()=>{
  const original=global.fetch,events=[],logger=createLogger({runId:'freshness',sink:e=>events.push(e)});
  let changed=null;
  global.fetch=async url=>{
    const name=String(url).split('/data/')[1];
    if(changed==='missing-bundle' && ['routes.geojson','hazards.geojson','coverage.geojson','route_audit.json','itinerary_report.json'].includes(name)) return {ok:false,status:404};
    const bytes=fs.readFileSync(new URL(name,root)),body=Buffer.concat([bytes,Buffer.from(name===changed?' ':'')]);
    return {ok:true,headers:new Headers(),json:async()=>JSON.parse(body.toString()),text:async()=>body.toString(),arrayBuffer:async()=>body};
  };
  try {
    assert.equal((await loadAnalysis('/',logger)).state,'current');
    for(const name of ['mission.json','route_audit.json','hazards.geojson','scarp_lines.geojson','analysis_rules.json','terrain_source.json']) {
      changed=name;assert.equal((await loadAnalysis('/',logger)).state,'stale',name);
    }
    assert.ok(events.some(e=>e.event==='results.freshness'&&e.state==='stale'));
    changed='missing-bundle';
    const independent=await loadAnalysis('/',logger);
    assert.equal(independent.state,'stale');
    assert.equal(independent.reportStates['feasibility_report.json'],'current');
    assert.ok(independent.reports['feasibility_report.json'].verdict);
  } finally {global.fetch=original;}
});
