import fs from 'node:fs';
import crypto from 'node:crypto';
const root=new URL('../public/data/',import.meta.url);
const sha=url=>crypto.createHash('sha256').update(fs.readFileSync(url)).digest('hex');
const stable=value=>JSON.stringify(value,(_,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))):v);
const manifest=JSON.parse(fs.readFileSync(new URL('analysis_manifest.json',root)));
const names=["routes.geojson","mission.json","hazards.geojson","coverage.geojson","scarp_lines.geojson","science_targets.json","slope.meta.json","slope.bounds.json","slope.png","analysis_rules.json","terrain_source.json","route_audit.json","terrain_samples.json","feasibility_report.json","itinerary_report.json"];
const algorithms=['science_results.py','route_audit.py','terrain.py','hazards.py','feasibility.py','itinerary.py','routing.py'];
const dependencies={"route_audit.json":["routes.geojson","mission.json","hazards.geojson","coverage.geojson","scarp_lines.geojson","science_targets.json","slope.meta.json","slope.bounds.json","slope.png","analysis_rules.json","terrain_source.json","route_audit.json"],"terrain_samples.json":["terrain_source.json","analysis_rules.json","terrain_samples.json"],"feasibility_report.json":["mission.json","scarp_lines.geojson","analysis_rules.json","terrain_source.json","feasibility_report.json"],"itinerary_report.json":["routes.geojson","mission.json","analysis_rules.json","itinerary_report.json"]};
if(manifest.schema_version!=='1.0'||stable(manifest.report_inputs)!==stable(dependencies)
  ||Object.keys(manifest.files??{}).sort().join()!==names.sort().join()
  ||Object.keys(manifest.algorithms??{}).sort().join()!==algorithms.sort().join()) throw Error('Incomplete analysis manifest');
for(const[name,expected]of Object.entries(manifest.files)) {
  // Fixed expected names are checked above; no arbitrary manifest paths are opened.
  if(sha(new URL(name,root))!==expected) throw Error('Stale analysis: '+name+'; regenerate pipeline.science_results');
}
for(const[name,expected]of Object.entries(manifest.algorithms)) {
  // Any scientific generator change invalidates published results.
  if(sha(new URL('../pipeline/'+name,import.meta.url))!==expected) throw Error('Changed analysis generator: '+name);
}
if(stable(JSON.parse(fs.readFileSync(new URL('../pipeline/hazard_rules.json',import.meta.url))))
  !==stable(JSON.parse(fs.readFileSync(new URL('analysis_rules.json',root))))) throw Error('Changed hazard rules: regenerate science results');
console.log('Analytical inputs, artifacts, rules and generator digests verified.');
