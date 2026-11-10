import type {DiagnosticClient} from "../lib/diagnostic-client";

// Compile-only contract checks; this function is never executed.
export function checkDiagnosticContract(client:DiagnosticClient) {
  client.POST("/jobs",{body:{kind:"dns",target:"https://example.com"}});
  // @ts-expect-error arbitrary commands are not a probe kind
  client.POST("/jobs",{body:{kind:"shell",target:"https://example.com"}});
  // @ts-expect-error target is required
  client.POST("/jobs",{body:{kind:"dns"}});
  // @ts-expect-error a job identifier is required
  client.GET("/jobs/{job_id}");
}
