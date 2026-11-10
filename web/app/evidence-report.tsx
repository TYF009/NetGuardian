import {formatUtc} from "../lib/time.mjs";
export type EvidenceReport = {
  id:string;integrity:string;content_hash:string;
  snapshot:{incident_id:string;state:string;generated_at:string;opened_at?:string;
    recovered_at?:string|null;missing_evidence_ids:string[];limitations:string[];
    claims:{text:string;evidence_ids:string[]}[];
    evidence:{job_id:string;kind:string;status:string;target:string;observed_at:string;
      vantage_id:string;attempt:number;http_status:number|null;
      timings:Record<string,number|null>;error:{code:string;message:string}|null}[]};
};
const date=(value?:string|null)=>value?formatUtc(value):"Not recorded";
export default function EvidenceReportBody({report}:{report:EvidenceReport}) {
  const snapshot=report.snapshot;
  const known=new Set(snapshot.evidence.map(item=>item.job_id));
  return <div>
    <dl><dt>Incident</dt><dd className="mono">{snapshot.incident_id}</dd>
      <dt>State at export</dt><dd>{snapshot.state}</dd>
      <dt>Opened</dt><dd>{date(snapshot.opened_at)}</dd>
      <dt>Recovered</dt><dd>{date(snapshot.recovered_at)}</dd>
      <dt>Snapshot generated</dt><dd>{date(snapshot.generated_at)}</dd></dl>
    <h3>Recorded findings</h3><p>Probe success means the measurement completed; an HTTP error status can still indicate an unhealthy target.</p>
    {!snapshot.claims.length?<p>No supported findings in this snapshot.</p>:<ul>{snapshot.claims.map((claim,index)=><li key={index}>{claim.text} <span>{claim.evidence_ids.map(id=>known.has(id)?<a key={id} href={`#evidence-${id}`}>[{id.slice(0,8)}] </a>:<span key={id}>Missing citation {id}</span>)}</span></li>)}</ul>}
    <h3>Limitations</h3><ul>{snapshot.limitations.map((text,index)=><li key={index}>{text}</li>)}</ul>
    {snapshot.missing_evidence_ids.length>0&&<div className="error"><h3>Missing evidence</h3><p>These linked jobs have no available measurement; no outcome is inferred.</p><ul>{snapshot.missing_evidence_ids.map(id=><li className="mono" key={id}>{id}</li>)}</ul></div>}
    <h3>Evidence observations ({snapshot.evidence.length})</h3>
    {snapshot.evidence.map(item=><article className="panel" id={`evidence-${item.job_id}`} key={item.job_id}>
      <h3>{item.kind.toUpperCase()} · {item.status}{item.http_status!==null?` · HTTP ${item.http_status}`:""}</h3>
      <p>{item.target}</p><p>{date(item.observed_at)} · Attempt {item.attempt}</p>
      <p className="mono">Job {item.job_id} · Vantage {item.vantage_id}</p>
      {item.error&&<p className="error">{item.error.code}</p>}
      <div className="timings">{Object.entries(item.timings).filter(([,value])=>value!==null).map(([name,value])=><div key={name}><span>{name.replaceAll("_"," ")}</span><strong>{value} ms</strong></div>)}</div>
    </article>)}
    <p className="mono">Snapshot SHA-256: {report.content_hash}</p>
    <details><summary>Raw report JSON</summary><pre className="report">{JSON.stringify(report,null,2)}</pre></details>
  </div>;
}
