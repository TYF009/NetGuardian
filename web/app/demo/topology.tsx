"use client";
import {useState} from "react";
import {Background, Controls, ReactFlow, type Node, type NodeProps, Handle, Position} from "@xyflow/react";
import {formatUtc} from "../../lib/time.mjs";
import {assets, assetObservation, incidents} from "./scenario";

type AssetNode = Node<{label: string; monitoring: string}, "asset">;

function Asset({data, selected}: NodeProps<AssetNode>) {
  return <div className={`ops-node ${selected ? "ops-node-selected" : ""}`}>
    <Handle type="target" position={Position.Top} isConnectable={false}/>
    <strong>{data.label}</strong><small>{data.monitoring}</small>
    <Handle type="source" position={Position.Bottom} isConnectable={false}/>
  </div>;
}

const nodeTypes = {asset: Asset};
const edges = assets.flatMap(asset => asset.parent
  ? [{id: `${asset.parent}-${asset.id}`, source: asset.parent, target: asset.id, type: "smoothstep"}] : []);

export default function Topology() {
  const [id, setId] = useState("pos");
  const selected = assets.find(asset => asset.id === id)!;
  const observed = assetObservation(id);
  const related = incidents.filter(incident => incident.asset === id);
  const nodes: AssetNode[] = assets.map(asset => ({
    id: asset.id, type: "asset", position: {x: asset.x, y: asset.y},
    data: {label: asset.name, monitoring: asset.monitor},
    ariaLabel: `${asset.name}, ${asset.monitor}`, selected: asset.id === id,
  }));
  return <section className="ops-card" id="topology">
    <h2>Network topology</h2>
    <p className="ops-muted">SIMULATED · Configured logical links</p>
    <div className="ops-topology">
      <div className="ops-flow" aria-label="Configured logical network map">
        <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView minZoom={0.25} maxZoom={1.75}
          nodesDraggable={false} nodesConnectable={false} edgesFocusable={false} elementsSelectable={false}
          onNodeClick={(_, node) => setId(node.id)} zoomOnScroll={false} panOnScroll={false}
          colorMode="system">
          <Background gap={18}/><Controls showInteractive={false}/>
        </ReactFlow>
      </div>
      <div className="ops-node-detail" aria-label="Asset details">
        <label>Inspect asset<select value={id} onChange={event => setId(event.target.value)}>
          {assets.map(asset => <option key={asset.id} value={asset.id}>{asset.name}</option>)}
        </select></label>
        <dl>
          <dt>Asset name</dt><dd>{selected.name}</dd>
          <dt>Asset type</dt><dd>{selected.type}</dd>
          <dt>Zone</dt><dd>{selected.zone}</dd>
          <dt>Monitoring status</dt><dd>{selected.monitor}</dd>
          <dt>Last observation</dt><dd>{observed ? formatUtc(observed) : "No Data"}</dd>
          <dt>Related incidents</dt><dd>{related.length ? related.map(incident =>
            <a key={incident.id} href={`#${incident.id}`}>{incident.id} · {incident.state}</a>) : "None recorded"}</dd>
        </dl>
      </div>
    </div>
  </section>;
}
