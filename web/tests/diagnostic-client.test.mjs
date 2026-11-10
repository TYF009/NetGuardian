import test from "node:test";
import assert from "node:assert/strict";
import {createDiagnosticClient} from "../lib/diagnostic-client.ts";

test("generated client preserves proxy path, credentials, JSON and cancellation",async t=>{
  let captured;
  t.mock.method(globalThis,"fetch",async request=>{
    captured=request;
    return Response.json({id:"fixture",state:"queued"},{status:202});
  });
  const controller=new AbortController();
  const client=createDiagnosticClient("test-only-token",controller.signal,"http://127.0.0.1:3000/api/backend");
  const result=await client.POST("/jobs",{body:{kind:"http",target:"https://example.com"}});
  assert.equal(captured.url,"http://127.0.0.1:3000/api/backend/jobs");
  assert.equal(captured.headers.get("authorization"),"Bearer test-only-token");
  assert.deepEqual(await captured.json(),{kind:"http",target:"https://example.com"});
  assert.equal(result.data.state,"queued");
  controller.abort();
  assert.equal(captured.signal.aborted,true);
});
