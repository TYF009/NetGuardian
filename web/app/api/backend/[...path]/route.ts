import { NextRequest } from "next/server";
import { BodyReadError, readRequestBody } from "../../../../lib/request-body.mjs";
export const dynamic = "force-dynamic";
async function forward(request: NextRequest, context: {params: Promise<{path: string[]}>}) {
  const {path} = await context.params;
  const endpoint = path.join("/");
  const incidentHistory = /^incidents\/[a-f0-9-]{36}\/evidence$/.test(endpoint);
  const query = new URLSearchParams();
  if (incidentHistory) {
    for (const [name, value] of request.nextUrl.searchParams) {
      if (!["after", "limit"].includes(name) || !/^\d{1,10}$/.test(value) || query.has(name))
        return Response.json({detail:"Invalid history pagination"},{status:400});
      query.set(name,value);
    }
  }
  if (!incidentHistory && endpoint !== "agents/enrollment" && !/^monitors\/[a-f0-9-]{36}\/runs$/.test(endpoint) && !/^(audit-events|targets|jobs|diagnostic-pairs|monitors|incidents|comparisons|reports|agents|investigations)(\/[a-f0-9-]{36})?$/.test(endpoint))
    return Response.json({detail:"Unknown endpoint"},{status:404});
  const auth = request.headers.get("authorization");
  if (!auth?.startsWith("Bearer ") || auth.length > 4096)
    return Response.json({detail:"Authentication required"},{status:401});
  let body: string | undefined;
  try {
    if (["POST", "PATCH"].includes(request.method)) body = await readRequestBody(request);
  } catch (error) {
    return Response.json({detail:error instanceof BodyReadError ? error.message : "Cannot read request body"},
      {status:error instanceof BodyReadError ? error.status : 400});
  }
  try {
    const response = await fetch(`${process.env.NETGUARDIAN_API_URL || "http://127.0.0.1:8000"}/api/${endpoint}${query.size?`?${query}`:""}`, {
      method:request.method, headers:{Authorization:auth,"Content-Type":"application/json"},
      body, cache:"no-store", redirect:"error", signal:AbortSignal.timeout(35000)
    });
    return new Response(response.status === 204 ? null : await response.text(), {
      status:response.status, headers:{"Content-Type":"application/json","Cache-Control":"no-store",...(response.headers.has("Retry-After")?{"Retry-After":response.headers.get("Retry-After")!}:{})}
    });
  } catch { return Response.json({detail:"Control API unavailable"},{status:502}); }
}
export {forward as GET, forward as POST, forward as DELETE, forward as PATCH};
