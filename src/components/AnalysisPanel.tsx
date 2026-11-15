import { useState } from 'react';
import type { AnalysisResults } from '../data/analysis';
import { measured } from '../data/analysis';
import { appLogger } from '../lib/appLogger';

export function AnalysisPanel({analysis}:{analysis:AnalysisResults}) {
  // analysis carries independently loaded offline results, including legitimate infeasibility.
  const [report,setReport]=useState('feasibility_report.json');
  const data=analysis.reports[report], reportState=analysis.reportStates?.[report]??analysis.state;
  // Collapsed by default in the side panel: the stage story comes first; the raw reports are one click away.
  return <details className="analysis-panel" aria-label="Offline analytical results">
    <summary>Offline analysis (advanced) · {analysis.state}</summary><p role="status">{analysis.state}: {analysis.reason}</p>
    <p>Planning evidence · crew clearance not established. Missing artifact review does not mean artifact-free.</p>
    <p>Selected report: {reportState}</p><label>Report <select value={report} onChange={e=>{
      // Report selection changes presentation only; it never starts a backend operation.
      setReport(e.target.value);appLogger.info('analysis','report.inspect',{report:e.target.value,state:analysis.state});
    }}><option value="feasibility_report.json">Site feasibility and uncertainty</option>
      <option value="itinerary_report.json">EVA budgets, walkback and backup independence</option></select></label>
    {reportState==='current' && data ? <ResultTree value={data}/> : <p>{reportState==='stale'?'Stale — requires regeneration':reportState==='invalid'?'Invalid report — requires regeneration':'Not measured'}</p>}
  </details>;
}

function ResultTree({value}:{value:unknown}) {
  // Recursively retain report field names, zero values and nested reason/evidence distinctions.
  if(value===null || value===undefined) return <span>Not measured</span>;
  if(typeof value==='number') return <span>{measured(value)}</span>;
  if(typeof value!=='object') return <span>{String(value)}</span>;
  const entries=Object.entries(value);
  if(!entries.length) return <span>Not measured (no declared assessment)</span>;
  return <dl className="result-tree">{entries.map(([key,item])=><div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{
    typeof item==='object'&&item!==null?<details><summary>Inspect {key.replaceAll('_',' ')}</summary><ResultTree value={item}/></details>:<ResultTree value={item}/>}</dd></div>)}</dl>;
}
