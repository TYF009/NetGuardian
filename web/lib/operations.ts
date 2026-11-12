import type {JobDetail} from "./diagnostic-client";

export type Observation = {
  id: string;
  created_at: string;
  status: string | null;
  http_status: number | null;
  timings: Record<string, number | null>;
};

export function observationStatus(run: Observation | undefined) {
  if (!run?.status || !["success", "error", "timeout"].includes(run.status)) return "Unknown";
  return run.status === "success" ? "Succeeded" : "Failed";
}

export function endpointStatus(run: Observation | undefined) {
  if (!run || run.status !== "success" || run.http_status == null) return "Unknown";
  return run.http_status >= 200 && run.http_status < 400 ? "Responding" : "HTTP failure";
}

export function currentObservation(
  telemetry: {state: string; latest_job_id: string | null},
  runs: Observation[],
) {
  return telemetry.state === "current"
    ? runs.find(run => run.id === telemetry.latest_job_id)
    : undefined;
}

export const metricLabels = {
  dns_lookup_ms: "DNS lookup",
  tcp_connect_ms: "TCP connect",
  tls_handshake_ms: "TLS handshake",
  http_ttfb_ms: "HTTP time to first byte",
  http_total_ms: "HTTP total request",
  icmp_rtt_ms: "ICMP round-trip time",
};

export type LayerInput = Pick<NonNullable<JobDetail["result"]>,
  "target" | "kind" | "dns" | "tls" | "timings" | "connected_ip" | "http_status" | "error">;

const checks = [
  {name: "DNS", metric: "dns_lookup_ms", suggestion: "Check resolver reachability and compare A and AAAA answers from the same probe location."},
  {name: "TCP", metric: "tcp_connect_ms", suggestion: "Verify the service is listening on the approved port and review firewall rules from this probe location."},
  {name: "TLS", metric: "tls_handshake_ms", suggestion: "Check certificate hostname, validity, trust chain and probe clock."},
  {name: "HTTP", metric: "http_total_ms", suggestion: "Compare the HEAD response with an authorized application check and review service logs."},
] as const;

export function diagnosticLayers(result: LayerInput) {
  const requested = ["dns", "tcp", "tls", "http"].indexOf(result.kind);
  if (requested < 0) return [];
  const timing = result.timings;
  const skipped = [
    result.dns?.used_dns === false,
    false,
    result.kind === "http" && result.target.startsWith("http://"),
    false,
  ];
  const evidence = [
    Boolean(result.dns?.answers.length || timing?.dns_lookup_ms != null),
    Boolean(result.connected_ip || timing?.tcp_connect_ms != null),
    Boolean(result.tls),
    result.http_status != null,
  ];
  const explicitError = result.error?.code === "resolution_failed" ? 0
    : result.error?.code === "tls_verification_failed" ? 2 : -1;
  return checks.map((check, index) => {
    const httpFailure = index === 3 && result.http_status != null && result.http_status >= 400;
    const status = index > requested ? "Not requested" : skipped[index] ? "Skipped"
      : index === explicitError ? "Failed" : httpFailure ? "HTTP failure"
        : evidence[index] ? "Observed" : "No evidence";
    return {
      ...check,
      status,
      duration: timing?.[check.metric],
      error: index === explicitError ? result.error?.code
        : httpFailure ? `HTTP ${result.http_status}` : undefined,
    };
  });
}

export function diagnosticGuidance(result: LayerInput) {
  switch (result.error?.code) {
    case "resolution_failed": return "Resolver reachability or a missing DNS record may explain the failed lookup.";
    case "tls_verification_failed": return "A hostname mismatch, expired certificate or trust-chain issue may explain the verification failure.";
    case "timeout":
    case "transport_error": return "Routing, filtering or an unresponsive service may explain the interruption. The error does not identify a specific layer.";
    case "policy_denied": return "The target or its resolved address may be outside the approved policy. Review the authorization and recorded addresses before retrying.";
    case "unsupported":
    case "cancelled": return "Probe execution did not establish a network or service fault.";
  }
  if (result.http_status != null && result.http_status >= 500)
    return "The application or an upstream dependency may be failing. The HTTP response alone does not identify which component.";
  if (result.http_status != null && result.http_status >= 400)
    return "The endpoint may reject HEAD, require credentials or have a route mismatch.";
  return null;
}
