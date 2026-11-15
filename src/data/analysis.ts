import type { Logger } from '../lib/logger.ts';
export type Freshness = 'current'|'missing'|'invalid'|'stale';
export interface AnalysisResults {
  state:Freshness; reason:string; reportStates?:Record<string,Freshness>; reports:Record<string,unknown>;
}
export const ANALYSIS_INPUTS = ['routes.geojson','mission.json','hazards.geojson','coverage.geojson','scarp_lines.geojson',
  'science_targets.json','slope.meta.json','slope.bounds.json','analysis_rules.json','terrain_source.json','slope.png'];
export const REPORT_INPUTS:Record<string,string[]> = {"route_audit.json":["routes.geojson","mission.json","hazards.geojson","coverage.geojson","scarp_lines.geojson","science_targets.json","slope.meta.json","slope.bounds.json","slope.png","analysis_rules.json","terrain_source.json","route_audit.json"],"terrain_samples.json":["terrain_source.json","analysis_rules.json","terrain_samples.json"],"feasibility_report.json":["mission.json","scarp_lines.geojson","analysis_rules.json","terrain_source.json","feasibility_report.json"],"itinerary_report.json":["routes.geojson","mission.json","analysis_rules.json","itinerary_report.json"]};
export const ANALYSIS_REPORTS = ['route_audit.json','terrain_samples.json','feasibility_report.json','itinerary_report.json'];

export async function loadAnalysis(baseUrl:string,logger:Logger):Promise<AnalysisResults> {
  // Exact-byte SHA-256 binds all reports to all published inputs; fetch only this fixed local allowlist.
  const reports:Record<string,unknown>={};
  try {
    const response=await fetch(baseUrl+'data/analysis_manifest.json');
    if(!response.ok || response.headers?.get('content-type')?.includes('text/html')) return {state:'missing',reason:'Analysis manifest not published.',reports};
    const manifest=await response.json();
    const names=[...ANALYSIS_INPUTS,...ANALYSIS_REPORTS];
    if(manifest.schema_version!=='1.0' || stable(manifest.report_inputs)!==stable(REPORT_INPUTS) || !manifest.files || Object.keys(manifest.files).sort().join()!==names.sort().join())
      throw new Error('Incomplete or unsupported analysis manifest.');
    const changed:string[]=[], missing:string[]=[], invalid:string[]=[];
    await Promise.all(names.map(async name=>{
      try {
      // Text is hashed as received: formatting changes also require regeneration.
      const r=await fetch(baseUrl+'data/'+name);
      if(!r.ok || (typeof r.text!=='function' && typeof r.arrayBuffer!=='function')) {changed.push(name);missing.push(name);return;}
      const bytes=typeof r.arrayBuffer==='function'?await r.arrayBuffer():new TextEncoder().encode(await r.text());
      const text=name.endsWith('.png')?'':new TextDecoder().decode(bytes);
      const sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
      if(sha!==manifest.files[name]) changed.push(name);
      if(!name.endsWith('.png')) reports[name]=JSON.parse(text);
      } catch(error) { changed.push(name);invalid.push(name); logger.warn('analysis','results.file_invalid',{file:name,reason:String(error)}); }
    }));
    const state=changed.length?'stale':'current';
    logger[state==='current'?'info':'warn']('analysis','results.freshness',{state,changed,crew_clearance:'not_established'});
    const reportStates=Object.fromEntries(Object.entries(REPORT_INPUTS).map(([name,inputs])=>[name,missing.includes(name)?'missing':invalid.includes(name)?'invalid':inputs.some(input=>changed.includes(input))?'stale':'current'])) as Record<string,Freshness>;
    return {state,reportStates,reason:changed.length?'Stale — requires regeneration: '+changed.join(', '):'Exact input and report digests verified.',reports};
  } catch(error) {
    logger.error('analysis','results.invalid',{reason:String(error)});
    return {state:'invalid',reason:'Analysis unavailable: '+String(error),reports:{}};
  }
}

export function measured(value:unknown,unit='',state:Freshness='current'):string {
  // Preserve zero; finite numbers have units, absent values are explicitly unmeasured.
  if(state==='stale') return 'Stale — requires regeneration';
  return typeof value==='number'&&Number.isFinite(value)?value.toLocaleString(undefined,{maximumFractionDigits:2})+unit:'Not measured';
}

export function stable(value:unknown):string {
  // Sort object keys for semantic snapshot comparison; arrays retain their scientific ordering.
  if(Array.isArray(value)) return '['+value.map(stable).join(',')+']';
  if(value && typeof value==='object') return '{'+Object.entries(value).sort(([a],[b])=>a.localeCompare(b)).map(([k,v])=>JSON.stringify(k)+':'+stable(v)).join(',')+'}';
  return JSON.stringify(value);
}
