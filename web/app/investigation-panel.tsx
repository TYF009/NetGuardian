import {formatUtc} from "../lib/time.mjs";

export type Investigation = {
  id:string; report_id:string; created_at:string; model:string;
  prompt_version:string; evidence_hash:string;
  output:{status:string; facts:{evidence_id:string;field:string;value:string|number|null}[];
    hypotheses:{text:string;evidence_ids:string[];label?:string}[];limitations:string[]};
};

export default function InvestigationPanel({record,busy,onSource,onClose}:{
  record:Investigation;busy:boolean;onSource:()=>void;onClose:()=>void;
}) {
  const output=record.output;
  const validated=output.status==="validated";
  return <section className="panel">
    <div className="record"><h2>AI-assisted investigation</h2>
      <button disabled={busy} onClick={onSource}>Open source report</button>
      <button onClick={onClose}>Close investigation</button></div>
    <p>{record.model} · {formatUtc(record.created_at)} · Prompt {record.prompt_version}</p>
    <p>{validated?"Recorded facts passed evidence checks. Hypotheses have not been verified.":
      "No validated model findings are available. Use the recorded source report."}</p>
    <p>Citations do not establish a root cause or verify the accuracy of a measurement.</p>
    <h3>Evidence-checked facts</h3>
    {!validated||!output.facts.length?<p>No validated facts in this investigation.</p>:
      <ul>{output.facts.map((fact,index)=><li key={index}>
        <strong>{fact.field.replaceAll("_"," ")}</strong>: {fact.value===null?"Not recorded":String(fact.value)}
        <p className="mono">Evidence {fact.evidence_id}</p>
      </li>)}</ul>}
    <h3>Unverified hypotheses</h3>
    {!validated||!output.hypotheses.length?<p>No causal hypothesis was established.</p>:
      <ul>{output.hypotheses.map((hypothesis,index)=><li key={index}>
        <p><strong>Unverified hypothesis:</strong> {hypothesis.text}</p>
        <p className="mono">Cited evidence: {hypothesis.evidence_ids.join(", ")}</p>
      </li>)}</ul>}
    <h3>Limitations</h3><ul>{output.limitations.map((text,index)=><li key={index}>{text}</li>)}</ul>
    <p className="mono">Source report {record.report_id}</p>
    <p className="mono">Evidence SHA-256 {record.evidence_hash}</p>
    <details><summary>Raw investigation JSON</summary><pre className="report">{JSON.stringify(record,null,2)}</pre></details>
  </section>;
}
