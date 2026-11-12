import type {LayerInput, Observation} from "../../lib/operations";

export const property = "Aster Quay Hotel";
export const snapshot = "2026-10-14T10:45:00Z";

export const assets = [
  {id: "internet", name: "Internet uplink", type: "External service", zone: "WAN", x: 230, y: 0, monitor: "Unmonitored"},
  {id: "gateway", parent: "internet", name: "Gateway / Firewall", type: "Firewall", zone: "Edge", x: 230, y: 75, monitor: "Current"},
  {id: "core", parent: "gateway", name: "Core switch", type: "Switch", zone: "Distribution", x: 230, y: 150, monitor: "Current"},
  {id: "access", parent: "core", name: "Access network", type: "Logical segment", zone: "Access", x: 230, y: 225, monitor: "Unmonitored"},
  {id: "guest", parent: "access", name: "Guest Wi-Fi", type: "Wireless service", zone: "Guest", x: 0, y: 310, monitor: "Current"},
  {id: "desk", parent: "access", name: "Front desk", type: "Business service", zone: "Front office", x: 155, y: 310, monitor: "Current"},
  {id: "pos", parent: "access", name: "POS terminals", type: "Business service", zone: "Food & beverage", x: 310, y: 310, monitor: "Current"},
  {id: "office", parent: "access", name: "Office LAN", type: "Logical segment", zone: "Back office", x: 465, y: 310, monitor: "Stale"},
];

export const incidents = [
  {id: "DEMO-104", asset: "pos", state: "Open", title: "POS endpoint returns HTTP 503", time: "2026-10-14T10:15:00Z"},
  {id: "DEMO-103", asset: "guest", state: "Resolved", title: "Guest portal endpoint recovered", time: "2026-10-14T08:30:00Z"},
];

const elapsed = [74, 83, 78, 96, 82, 91, 86, 79, 93, 85, 118, 153, 161, 137, 148, 152];
export const runs: Observation[] = elapsed.map<Observation>((ms, index) => ({
  id: `demo-run-${index}`,
  created_at: new Date(Date.parse(snapshot) - (elapsed.length - 1 - index) * 300000).toISOString(),
  status: index === 6 ? null : "success",
  http_status: index === 6 ? null : index >= 9 ? 503 : 204,
  timings: {http_total_ms: index === 6 ? null : ms, tcp_connect_ms: index === 6 ? null : 8 + index % 5},
}));

export const diagnostic: LayerInput = {
  kind: "http", target: "https://pos.aster-quay.example", connected_ip: "192.0.2.10",
  timings: {dns_lookup_ms: 7, tcp_connect_ms: 8, tls_handshake_ms: 31, http_total_ms: 152},
  dns: {used_dns: true, answers: [{record_type: "A", addresses: ["192.0.2.10"],
    ttl_seconds: 60, canonical_name: "pos.aster-quay.example"}]},
  tls: {protocol: "TLSv1.3", cipher: "TLS_AES_128_GCM_SHA256", cipher_bits: 128,
    hostname_verified: true, leaf_sha256: "0".repeat(64), not_before: "2026-10-01T00:00:00Z", not_after: "2027-01-01T00:00:00Z"},
  http_status: 503,
};

export function assetObservation(id: string) {
  if (id === "office") return "2026-10-14T07:00:00Z";
  return assets.find(asset => asset.id === id)?.monitor === "Current" ? snapshot : null;
}
