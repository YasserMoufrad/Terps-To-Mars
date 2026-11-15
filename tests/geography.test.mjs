// Geographic consistency: mission.json, route endpoints and the DTM-checked site points
// (data/site/site_points_dtm.geojson, which replaces Geury's first pass) must describe the same places,
// every point moved from Geury's first pass must say why, and no over-budget or non-independent crew route
// may read "ok". Distances use the Mars mean sphere (R = 3,389,500 m), never Leaflet's Earth tools.

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const read = (path) => JSON.parse(readFileSync(new URL(`../${path}`, import.meta.url), 'utf8'));
const mission = read('public/data/mission.json');
const routes = read('public/data/routes.geojson');
const points = (file) => Object.fromEntries(read(file).features.map((f) => [f.properties.id, f]));
const site = points('data/site/site_points_dtm.geojson');
const firstPass = points('data/site/site_points.geojson');
const parkingAudit = read('data/site/feasibility_audit_from_parking.json');

const MARS_R = 3389500;
const TOLERANCE_M = 15; // stated point uncertainty
const at = (id) => site[id].geometry.coordinates;

function marsDistance([lon1, lat1], [lon2, lat2]) {
  // Purpose: great-circle metres between two [lon, lat] points on the Mars sphere.
  const r = Math.PI / 180;
  const a = Math.sin(((lat2 - lat1) * r) / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(((lon2 - lon1) * r) / 2) ** 2;
  return 2 * MARS_R * Math.asin(Math.min(1, Math.sqrt(a)));
}
const ll = (p) => [p.lon, p.lat];
const route = (id) => routes.features.find((f) => f.properties.id === id);

test('mission endpoints are the DTM-checked site points', () => {
  for (const [id, point] of [['habitat', mission.endpoints.habitat], ['observation_primary', mission.endpoints.observation_primary],
    ['observation_backup', mission.endpoints.observation_backup], ['drone_perch', mission.drone.perch]]) {
    assert.ok(marsDistance(ll(point), at(id)) <= TOLERANCE_M, `${id} is ${marsDistance(ll(point), at(id)).toFixed(1)} m from the checked point`);
  }
});

test('every point moved from Geury\'s first pass states where and on what evidence', () => {
  // Never move a scientific point silently: a move beyond the 15 m uncertainty needs a written reason.
  for (const [id, f] of Object.entries(site)) {
    if (!firstPass[id]) continue;
    const moved = marsDistance(f.geometry.coordinates, firstPass[id].geometry.coordinates);
    if (moved > TOLERANCE_M) {
      assert.ok(f.properties.where && f.properties.source, `${id} moved ${moved.toFixed(0)} m without a reason`);
    }
  }
});

test('crew routes start at the habitat and end at the primary observation point', () => {
  const main = route('rt-crew-main-v2').geometry.coordinates;
  const backup = route('rt-crew-backup-v2').geometry.coordinates;
  assert.ok(marsDistance(main[0], at('habitat')) <= TOLERANCE_M);
  assert.ok(marsDistance(main.at(-1), at('observation_primary')) <= TOLERANCE_M);
  // The backup route serves the BACKUP viewpoint (pipeline.route_audit's objective for kind "backup", #18):
  // drawn viewpoint-first (return orientation) back to the habitat. Changed deliberately in PR #17.
  assert.ok(marsDistance(backup[0], at('observation_backup')) <= TOLERANCE_M);
  assert.ok(marsDistance(backup.at(-1), at('habitat')) <= TOLERANCE_M);
});

test('the crew-rover parking point is where the drive leg ends, and matches the parking audit', () => {
  const main = route('rt-crew-main-v2');
  const drive = main.properties.legs.filter((l) => l.mode === 'drive').at(-1);
  const parking = main.geometry.coordinates[drive.to];
  assert.ok(marsDistance(parking, at('parking')) <= TOLERANCE_M);
  assert.ok(marsDistance(parking, ll(parkingAudit.points.habitat)) <= TOLERANCE_M,
    'feasibility_audit_from_parking.json "habitat" must be the parking point (partial walking audit only)');
});

test('documented expectation: habitat ~1.4 km south; #16\'s native crop covers the scarp points, not the habitat', () => {
  // The habitat moved north on 2026-11-14 (Yasser) so the whole drive + walk trip is under the 5,000 m round-trip
  // limit either way it is counted: ~1.4 km straight line to the viewpoint (it was ~5 km before).
  const habitatToScarp = marsDistance(at('habitat'), at('observation_primary'));
  assert.ok(habitatToScarp > 1200 && habitatToScarp < 4500, `${habitatToScarp.toFixed(0)} m`);
  const crop = { s: 54.1548789, n: 54.1721222, w: -147.917929, e: -147.8910703 };
  const inCrop = ([lon, lat]) => lat >= crop.s && lat <= crop.n && lon >= crop.w && lon <= crop.e;
  for (const id of ['drone_perch', 'parking', 'observation_backup']) assert.ok(inCrop(at(id)), id);
  assert.ok(!inCrop(at('habitat')));
  // The primary viewpoint (moved in PR #17 to face the bluest stretch of the second scarp, per Geury's color
  // check) sits ~70 m north of the 4K crop. #18's HiRISE "context" tiles (~1 m, 54.110-54.185 N) cover it.
  assert.ok(!inCrop(at('observation_primary')) && at('observation_primary')[1] < crop.n + 0.002, 'primary expected just north of the 4K crop');
  const context = JSON.parse(readFileSync(new URL('../public/data/hirise-tiles/context/tiles.json', import.meta.url), 'utf8')).bounds;
  for (const id of ['habitat', 'parking', 'observation_primary', 'observation_backup', 'drone_perch']) {
    const [lon, lat] = at(id);
    assert.ok(lat >= context.south && lat <= context.north && lon >= context.west && lon <= context.east, `${id} inside HiRISE context tiles`);
  }
});

test('no crew route reads "ok" while it breaks the 5,000 m rule or shares most of its length with the main route', () => {
  for (const f of routes.features.filter((r) => r.properties.agent === 'crew')) {
    const s = f.properties.stats;
    if (s.round_trip_m >= 5000) assert.notEqual(f.properties.status, 'ok', `${f.properties.id} is ${s.round_trip_m} m round trip`);
    if (f.properties.kind === 'backup' && s.shared_with_main_m > 0.5 * s.length_m) {
      assert.notEqual(f.properties.status, 'ok', `${f.properties.id} shares ${s.shared_with_main_m} m with the main route`);
    }
  }
});
