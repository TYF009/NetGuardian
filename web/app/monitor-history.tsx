"use client";
import {formatUtc,formatUtcTime} from "../lib/time.mjs";
import {useState} from "react";

export type MonitorHistory = {monitor_id:string;name:string;runs:{id:string;created_at:string;state:string;status:string|null;http_status:number|null;timings:Record<string,number|null>}[]};
import {metricLabels} from "../lib/operations";
const metrics = Object.keys(metricLabels) as (keyof typeof metricLabels)[];
export default function MonitorHistoryPanel({history,onClose,onInspect}:{history:MonitorHistory;onClose:()=>void;onInspect:(id:string)=>void}) {
  const [metric,setMetric]=useState<keyof typeof metricLabels>("http_total_ms");
  const runs=history.runs;
  const points=runs.flatMap(run=>{
    const value=run.timings[metric];const time=Date.parse(run.created_at);
    return typeof value==="number"&&Number.isFinite(value)&&Number.isFinite(time)?[{run,value,time}]:[];
  });
  const start=runs.length?Date.parse(runs[0].created_at):0;
  const end=runs.length?Date.parse(runs[runs.length-1].created_at):start;
  const maximum=Math.max(1,...points.map(p=>p.value));
  return <section className="panel"><div className="record"><h2>Monitor history: {history.name}</h2><button onClick={onClose}>Close history</button></div>
    <p>Latest 100 scheduled runs. Time axis uses server job creation time. Missing values are absent, never zero; points are not joined across gaps.</p>
    <label>Timing metric<select value={metric} onChange={e=>setMetric(e.target.value as keyof typeof metricLabels)}>{metrics.map(m=><option key={m} value={m}>{metricLabels[m]}</option>)}</select></label>
    {points.length?<><svg viewBox="0 0 720 220" role="img" aria-label={`${metricLabels[metric]} in milliseconds; ${points.length} observations. Values are also in the table below.`} style={{width:"100%",maxHeight:280}}>
      <line x1="60" y1="20" x2="60" y2="180" stroke="#7796a4"/><line x1="60" y1="180" x2="690" y2="180" stroke="#7796a4"/>
      <text x="4" y="25" fontSize="12">{maximum.toFixed(1)} ms</text><text x="18" y="180" fontSize="12">0 ms</text>
      {points.map(p=><circle key={p.run.id} cx={60+(p.time-start)/Math.max(1,end-start)*630} cy={180-p.value/maximum*155} r="4" fill="#147c69"><title>{formatUtc(p.time)}: {p.value} ms · {p.run.status}</title></circle>)}
      <text x="60" y="205" fontSize="11">{formatUtcTime(start)}</text><text x="690" y="205" textAnchor="end" fontSize="11">{formatUtcTime(end)}</text>
    </svg><p>Timing is not a health verdict; failed requests may have partial timing evidence.</p></>:<p className="empty">No recorded values for this metric.</p>}
    <div className="table-wrap"><table><thead><tr><th>Created</th><th>Job / outcome</th><th>HTTP</th><th>{metricLabels[metric]}</th><th>Evidence</th></tr></thead><tbody>{runs.map(run=><tr key={run.id}><td>{formatUtc(run.created_at)}</td><td>{run.state} / {run.status??"No measurement"}</td><td>{run.http_status??"—"}</td><td>{run.timings[metric] == null?"Missing":`${run.timings[metric]} ms`}</td><td><button onClick={()=>onInspect(run.id)}>Inspect</button></td></tr>)}</tbody></table></div>
    {!runs.length&&<p className="empty">No scheduled runs yet.</p>}
  </section>;
}
