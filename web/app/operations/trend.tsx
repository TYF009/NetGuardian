"use client";
import {useState} from "react";
import {formatUtc, formatUtcTime} from "../../lib/time.mjs";

export type Point = {id: string; time: string; value: number | null; detail?: string};

export default function Trend({title, points, unit, ceiling}: {
  title: string; points: Point[]; unit: string; ceiling?: number;
}) {
  const [selected, setSelected] = useState<string>();
  const visible = points.slice(-24);
  const max = ceiling ?? Math.max(1, ...visible.map(point => point.value ?? 0));
  const active = visible.find(point => point.id === selected) ?? visible.at(-1);
  return <section className="ops-card ops-trend">
    <h2>{title}</h2>
    <p className="ops-muted">{unit === "%" ? "One value per scheduled run" : "Recorded values"} · {visible.length} recent runs</p>
    {visible.some(point => point.value !== null) ? <>
      <div className="ops-plot">
        <span className="ops-scale"><span>{Number(max.toFixed(1))}{unit}</span><span>0{unit}</span></span>
        <div className="ops-bars" role="group" aria-label={title}>
          {visible.map(point => <button type="button" key={point.id}
            aria-label={`${formatUtc(point.time)}: ${point.value == null ? "No data" : `${point.value}${unit}`}`}
            aria-pressed={active?.id === point.id} onFocus={() => setSelected(point.id)}
            onClick={() => setSelected(point.id)}
            className={point.value === 0 && unit === "%" ? "ops-bar-failed" : ""}>
            <span style={{height: point.value == null ? 0 : `max(4px, ${point.value / max * 100}%)`}}/>
          </button>)}
        </div>
      </div>
      <div className="ops-axis"><span>{formatUtcTime(visible[0].time)}</span><span>{formatUtcTime(visible.at(-1)!.time)}</span></div>
      <p className="ops-point" aria-live="polite">{active && `${formatUtc(active.time)} · ${active.value == null ? "No data" : `${Number(active.value.toFixed(2))}${unit}`}${active.detail ? ` · ${active.detail}` : ""}`}</p>
    </> : <p className="ops-empty">No Data</p>}
  </section>;
}
