import {diagnosticGuidance, diagnosticLayers, type LayerInput} from "../../lib/operations";

export default function DiagnosticLayers({result, raw = result}: {result: LayerInput; raw?: unknown}) {
  const layers = diagnosticLayers(result);
  if (!layers.length) return null;
  const guidance = diagnosticGuidance(result);
  const next = layers.find(layer => layer.error)
    ?? (result.error ? undefined : layers.find(layer => layer.status === "No evidence"));
  return <section className="ops-diagnosis" aria-label="Layered diagnostic evidence">
    <h3>Layered diagnostic evidence</h3>
    <div className="ops-layers">{layers.map(layer => <div key={layer.name}>
      <strong>{layer.name}</strong><span>{layer.status}</span>
      <span>{layer.duration == null ? "No timing" : `${layer.duration.toFixed(2)} ms`}</span>
      {layer.error && <small>{layer.error.replaceAll("_", " ")}</small>}
    </div>)}</div>
    <dl className="ops-facts">
      <dt>Observed facts</dt><dd>{result.error
        ? `${result.error.code.replaceAll("_", " ")}: ${result.error.message}`
        : result.http_status != null ? `HTTP ${result.http_status} received.` : "See recorded layer evidence."}</dd>
      <dt>Possible explanation</dt><dd>{guidance ?? "No fault hypothesis from this observation."}</dd>
      <dt>Suggested next check</dt><dd>{next?.suggestion ?? (result.error
        ? "Review the recorded probe outcome and repeat only from an authorized vantage."
        : "Compare with another authorized observation if symptoms persist.")}</dd>
    </dl>
    <details><summary>Raw probe evidence (JSON)</summary><pre className="report">{JSON.stringify(raw, null, 2)}</pre></details>
  </section>;
}
