"use client";
import {useState} from "react";
import {formatUtc} from "../../lib/time.mjs";
import {currentObservation, endpointStatus, metricLabels, observationStatus} from "../../lib/operations";
import type {MonitorHistory} from "../monitor-history";
import Trend from "./trend";

export type DashboardMonitor = {
  id: string; name: string; target: string; kind: string; enabled: boolean;
  telemetry: {state: string; latest_job_id: string | null};
};
export type DashboardIncident = {
  id: string; monitor_id: string; state: string; opened_at: string; recovered_at?: string | null;
};

export default function WorkspaceDashboard({monitors, incidents, history, snapshot, busy, onLoad, onIncidents}: {
  monitors: DashboardMonitor[]; incidents: DashboardIncident[];
  history: MonitorHistory | null; snapshot: string | null; busy: boolean;
  onLoad: (id: string) => void; onIncidents: () => void;
}) {
  const [selected, setSelected] = useState("");
  const [metric, setMetric] = useState<keyof typeof metricLabels>("http_total_ms");
  const runs = selected && history?.monitor_id === selected ? history.runs : [];
  const active = incidents.filter(incident => incident.state === "open");
  const totals = [
    ["Monitored targets / services", snapshot ? new Set(monitors.map(monitor => monitor.target)).size : "Unknown", "Distinct configured origins"],
    ["Active incidents", snapshot ? active.length : "Unknown", "Among the latest 100 incidents"],
    ["Current collection", snapshot ? monitors.filter(monitor => monitor.telemetry.state === "current").length : "Unknown", "Current monitor observations"],
    ["Device online status", "Unknown", "No device uptime telemetry"],
  ] as const;
  return <div className="ops-workspace">
    <h2>Infrastructure Health Overview</h2>
    <p className="ops-muted">{snapshot ? `Workspace snapshot · ${formatUtc(snapshot)}` : "No current workspace snapshot."}</p>
    <div className="ops-kpis">{totals.map(([label, value, description]) =>
      <section className="ops-card" key={label}><span>{label}</span>
        <strong className={typeof value === "string" ? "ops-kpi-text" : undefined}>{value}</strong><small>{description}</small>
      </section>)}</div>
    <section className="ops-card">
      <h2>Business Service Health</h2>
      <p className="ops-muted">Business workflow availability: Unknown. HEAD checks describe only the configured endpoint. Load a monitor’s history to see its latest matching probe outcome.</p>
      {!monitors.length ? <p className="ops-empty">No Data · No monitors loaded</p> : <div className="table-wrap">
        <table><thead><tr><th scope="col">Monitor</th><th scope="col">Probe result</th><th scope="col">Endpoint</th><th scope="col">Collection</th></tr></thead>
          <tbody>{monitors.map(monitor => {
            const current = snapshot && selected === monitor.id ? currentObservation(monitor.telemetry, runs) : undefined;
            return <tr key={monitor.id}>
              <th scope="row">{monitor.name}<small className="ops-target">{monitor.target} · {monitor.kind.toUpperCase()}</small></th>
              <td>{observationStatus(current)}</td><td>{endpointStatus(current)}</td>
              <td>{snapshot ? monitor.telemetry.state.replaceAll("_", " ") : "Unknown"}</td>
            </tr>;
          })}</tbody></table>
      </div>}
    </section>
    <section className="ops-card">
      <h2>Trend scope</h2>
      <form className="probe-form" onSubmit={event => {event.preventDefault(); if (selected) onLoad(selected)}}>
        <label>Monitor<select value={selected} onChange={event => setSelected(event.target.value)}>
          <option value="">Select a monitor</option>
          {monitors.map(monitor => <option key={monitor.id} value={monitor.id}>{monitor.name}</option>)}
        </select></label>
        <label>Timing metric<select value={metric} onChange={event => setMetric(event.target.value as keyof typeof metricLabels)}>
          {Object.entries(metricLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
        <button type="submit" disabled={busy || !selected}>Load history</button>
      </form>
      <p className="ops-muted">Availability samples show HTTP 2xx–3xx as 100% and other recorded HTTP responses as 0%. Missing responses have no value. Times are job creation times.</p>
    </section>
    <div className="ops-grid">
      <Trend title="Network Availability Trends · HTTP endpoint" unit="%" ceiling={100}
        points={runs.map(run => ({id: run.id, time: run.created_at,
          value: run.http_status == null ? null : run.http_status >= 200 && run.http_status < 400 ? 100 : 0,
          detail: run.http_status == null ? undefined : `HTTP ${run.http_status}`}))}/>
      <Trend title={`Latency and Connectivity Trends · ${metricLabels[metric]}`} unit="ms"
        points={runs.map(run => ({id: run.id, time: run.created_at, value: run.timings[metric] ?? null}))}/>
    </div>
    <section className="ops-card"><h2>Recent Incident Timeline</h2>
      {!incidents.length ? <p className="ops-empty">No recorded incidents in this view.</p> :
        incidents.slice(0, 8).map(incident => <article className="ops-incident" key={incident.id}>
          <span className={`ops-chip ${incident.state === "open" ? "ops-critical" : ""}`}>{incident.state}</span>
          <div><h3>{monitors.find(monitor => monitor.id === incident.monitor_id)?.name ?? "Monitor incident"}</h3>
            <small>Opened {formatUtc(incident.opened_at)}{incident.recovered_at && ` · Resolved ${formatUtc(incident.recovered_at)}`}</small></div>
        </article>)}
      <button onClick={onIncidents}>Open incident evidence</button>
    </section>
  </div>;
}
