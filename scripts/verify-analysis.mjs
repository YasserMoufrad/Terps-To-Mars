import fs from 'node:fs';
import crypto from 'node:crypto';
const root=new URL('../public/data/',import.meta.url);
const sha=url=>crypto.createHash('sha256').update(fs.readFileSync(url)).digest('hex');
const manifest=JSON.parse(fs.readFileSync(new URL('analysis_manifest.json',root)));
for(const[name,expected]of Object.entries(manifest.files)) {
  // Published inputs and outputs must match their exact-byte digest before any build.
  if(!/^[\w./-]+$/.test(name)||name.includes('..')||sha(new URL(name,root))!==expected) throw Error('Stale analysis: '+name+'; regenerate pipeline.science_results');
}
for(const[name,expected]of Object.entries(manifest.algorithms)) {
  // Generator source changes invalidate cached analytical reports too.
  if(!/^[\w-]+\.py$/.test(name)||sha(new URL('../pipeline/'+name,import.meta.url))!==expected) throw Error('Changed analysis generator: '+name);
}
console.log('Analytical inputs, artifacts and generator digests verified.');
