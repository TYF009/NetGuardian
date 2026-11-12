import {test} from "node:test";
import assert from "node:assert/strict";
import {currentObservation, diagnosticGuidance, diagnosticLayers, endpointStatus, observationStatus} from "../lib/operations.ts";
import {assets, assetObservation, diagnostic, incidents, runs} from "../app/demo/scenario.ts";

test("collection, probe completion and endpoint health remain independent", () => {
  const run = runs.at(-1);
  assert.equal(observationStatus(run), "Succeeded");
  assert.equal(endpointStatus(run), "HTTP failure");
  assert.equal(currentObservation({state: "stale", latest_job_id: run.id}, runs), undefined);
  assert.equal(currentObservation({state: "current", latest_job_id: "missing"}, runs), undefined);
  assert.equal(currentObservation({state: "current", latest_job_id: run.id}, runs), run);
  const missing = runs.find(run => run.status === null);
  assert.equal(observationStatus(missing), "Unknown");
  assert.equal(endpointStatus(missing), "Unknown");
  assert.equal(missing.timings.http_total_ms ?? null, null);
});

test("a received HTTP 503 is evidence, not a failed TCP or TLS handshake", () => {
  const layers = diagnosticLayers(diagnostic);
  assert.deepEqual(layers.map(layer => layer.status), ["Observed", "Observed", "Observed", "HTTP failure"]);
  assert.equal(layers[3].error, "HTTP 503");
  assert.equal(layers[3].duration, 152);
  assert.match(diagnosticGuidance(diagnostic), /may be failing/);
});

test("a generic timeout leaves the unobserved layer unknown", () => {
  const result = {...diagnostic, http_status: null, tls: null, timings: {tcp_connect_ms: 8},
    error: {code: "timeout", message: "Probe deadline exceeded"}};
  assert.deepEqual(diagnosticLayers(result).map(layer => layer.status), ["Observed", "Observed", "No evidence", "No evidence"]);
  assert.ok(diagnosticLayers(result).every(layer => layer.error === undefined));
  assert.match(diagnosticGuidance(result), /does not identify a specific layer/);
});

test("DNS literal and plain HTTP do not fabricate DNS or TLS measurements", () => {
  const result = {...diagnostic, target: "http://192.0.2.10", dns: {used_dns: false, answers: []},
    tls: null, timings: {tcp_connect_ms: 8}, http_status: 204};
  assert.deepEqual(diagnosticLayers(result).map(layer => layer.status), ["Skipped", "Observed", "Skipped", "Observed"]);
  assert.deepEqual(diagnosticLayers({...result, kind: "dns"}).map(layer => layer.status),
    ["Skipped", "Not requested", "Not requested", "Not requested"]);
});

test("the simulated topology links only known assets and marks missing observations", () => {
  const ids = new Set(assets.map(asset => asset.id));
  assert.equal(ids.size, assets.length);
  assert.equal(assets.filter(asset => !asset.parent).length, 1);
  assert.ok(assets.every(asset => !asset.parent || ids.has(asset.parent)));
  assert.ok(incidents.every(incident => ids.has(incident.asset)));
  assert.equal(assetObservation("internet"), null);
  assert.ok(incidents.every(incident => incident.id.startsWith("DEMO-")));
  assert.match(diagnostic.target, /^https:\/\/[^/]+\.example$/);
  assert.match(diagnostic.connected_ip, /^192\.0\.2\./);
});
