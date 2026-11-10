import createClient from "openapi-fetch";
import type {paths, components} from "./api-schema";

// The local proxy removes the API prefix, without changing operation contracts.
type ProxyPaths = {[P in keyof paths as P extends `/api${infer Rest}` ? Rest : never]: paths[P]};
export type JobSummary = components["schemas"]["JobSummary"];
export type JobDetail = components["schemas"]["JobDetail"];
export type CreateJob = components["schemas"]["CreateJob"];
export function createDiagnosticClient(token:string,signal:AbortSignal,baseUrl="/api/backend") {
  return createClient<ProxyPaths>({baseUrl,signal,
    headers:{Authorization:`Bearer ${token}`}});
}
export type DiagnosticClient = ReturnType<typeof createDiagnosticClient>;
