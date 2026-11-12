import Link from "next/link";
import {formatUtc} from "../../lib/time.mjs";
import {endpointStatus, observationStatus} from "../../lib/operations";
import DiagnosticLayers from "../operations/diagnostic-layers";
import ThemeControl from "../operations/theme";
import Trend from "../operations/trend";
import Topology from "./topology";
import {assets, diagnostic, incidents, property, runs, snapshot} from "./scenario";
import "@xyflow/react/dist/style.css";

const services = [
  {name: "Guest Wi-Fi portal", zone: "Guest network", probe: "Succeeded", endpoint: "Responding", freshness: "Current"},
  {name: "Front desk system", zone: "Front office", probe: "Succeeded", endpoint: "Responding", freshness: "Current"},
  {name: "POS endpoint", zone: "Food & beverage", probe: observationStatus(runs.at(-1)), endpoint: endpointStatus(runs.at(-1)), freshness: "Current"},
  {name: "Office services", zone: "Back office", probe: "Unknown", endpoint: "Unknown", freshness: "Stale"},
];

export default function DemoPage() {
  return <div className="shell ops-shell">
    <aside>
      <div className="brand"><span className="mark">N</span>NetGuardian</div>
      <p className="eyebrow">HOTEL IT OPERATIONS</p>
      <nav aria-label="Demo sections">
        <a className="active" href="#overview">Overview</a>
        <a href="#services">Services</a>
        <a href="#topology">Topology</a>
        <a href="#incidents">Incidents</a>
        <a href="#diagnosis">Troubleshooting</a>
      </nav>
      <div className="aside-bottom"><Link href="/" prefetch={false}>Open authenticated workspace</Link></div>
    </aside>
    <main className="ops-main" id="overview">
      <header>
        <div><p className="eyebrow">PROPERTY OPERATIONS</p><h1>{property}</h1><p className="ops-muted">Infrastructure Health Overview</p></div>
        <ThemeControl/>
      </header>
      <div className="ops-demo-banner"><strong>DEMO / SIMULATED</strong><span>Fictional property and assets · Snapshot {formatUtc(snapshot)}</span></div>
      <div className="ops-kpis">
        <section className="ops-card"><span>Monitored devices / services</span><strong>{assets.filter(asset => asset.monitor !== "Unmonitored").length}</strong><small>Configured sample assets</small></section>
        <section className="ops-card"><span>Active incidents</span><strong>{incidents.filter(incident => incident.state === "Open").length}</strong><small>POS endpoint HTTP 503</small></section>
        <section className="ops-card"><span>Current collection</span><strong>{assets.filter(asset => asset.monitor === "Current").length}</strong><small>1 stale monitored segment</small></section>
        <section className="ops-card"><span>Device online status</span><strong className="ops-kpi-text">Unknown</strong><small>No device uptime telemetry</small></section>
      </div>
      <div className="ops-grid">
        <Trend title="Network Availability Trends · POS endpoint" unit="%" ceiling={100} points={runs.map(run => ({
          id: run.id, time: run.created_at, value: run.http_status == null ? null : run.http_status < 400 ? 100 : 0,
          detail: run.http_status == null ? undefined : `HTTP ${run.http_status}`,
        }))}/>
        <Trend title="Latency and Connectivity Trends · HTTP total" unit="ms" points={runs.map(run => ({
          id: run.id, time: run.created_at, value: run.timings.http_total_ms ?? null,
          detail: run.http_status == null ? undefined : `HTTP ${run.http_status}`,
        }))}/>
      </div>
      <section className="ops-card" id="services"><h2>Business Service Health</h2>
        <p className="ops-muted">Endpoint checks measure the HEAD response. Business workflow availability: Unknown (no transaction checks).</p>
        <div className="table-wrap"><table><thead><tr><th scope="col">Service</th><th scope="col">Zone</th><th scope="col">Probe</th><th scope="col">Endpoint</th><th scope="col">Collection</th></tr></thead>
          <tbody>{services.map(service => <tr key={service.name}><th scope="row">{service.name}</th><td>{service.zone}</td>
            <td>{service.probe}</td><td><span className={`ops-chip ${service.endpoint === "HTTP failure" ? "ops-critical" : service.endpoint === "Responding" ? "ops-positive" : ""}`}>{service.endpoint}</span></td><td>{service.freshness}</td></tr>)}</tbody>
        </table></div>
      </section>
      <Topology/>
      <section className="ops-card" id="incidents"><h2>Recent Incident Timeline</h2>
        {incidents.map(incident => <article className="ops-incident" key={incident.id} id={incident.id}>
          <span className={`ops-chip ${incident.state === "Open" ? "ops-critical" : "ops-positive"}`}>{incident.state}</span>
          <div><h3>{incident.title}</h3><small>{incident.id} · {formatUtc(incident.time)}</small></div>
          {incident.asset === "pos" && <a href="#diagnosis">Inspect evidence</a>}
        </article>)}
      </section>
      <section className="ops-card" id="diagnosis"><h2>POS troubleshooting</h2>
        <p className="ops-muted">SIMULATED · POS endpoint · {formatUtc(snapshot)}</p>
        <DiagnosticLayers result={diagnostic} raw={{simulation: true, ...diagnostic}}/>
      </section>
      <footer>NetGuardian · Hospitality IT Operations Demo</footer>
    </main>
  </div>;
}
