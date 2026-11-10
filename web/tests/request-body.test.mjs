import test from "node:test";
import assert from "node:assert/strict";
import {readRequestBody} from "../lib/request-body.mjs";

function request(chunks, headers = {}) {
  return new Request("http://localhost/", {method: "POST", headers, duplex: "half",
    body: new ReadableStream({start(controller) {
      for (const chunk of chunks) controller.enqueue(chunk);
      controller.close();
    }})});
}
const encode = text => new TextEncoder().encode(text);
test("accept exact byte boundary and split UTF-8", async () => {
  const bytes = encode("你好");
  assert.equal(await readRequestBody(request([bytes.slice(0, 2), bytes.slice(2)]), 6), "你好");
});
test("reject chunked overflow by bytes rather than characters", async () => {
  await assert.rejects(readRequestBody(request([encode("你好")]), 5), {status: 413});
});
test("reject oversized content length before consuming stream", async () => {
  await assert.rejects(readRequestBody(request([], {"content-length": "8193"})), {status: 413});
});
test("reject invalid encoding and malformed UTF-8", async () => {
  await assert.rejects(readRequestBody(request([], {"content-encoding": "gzip"})), {status: 415});
  await assert.rejects(readRequestBody(request([new Uint8Array([255])])), {status: 400});
});
test("slow body times out and cancels source", async () => {
  let cancelled = false;
  const req = new Request("http://localhost/", {method: "POST", duplex: "half",
    body: new ReadableStream({cancel() { cancelled = true; }})});
  await assert.rejects(readRequestBody(req, 8192, 20), {status: 408});
  assert.equal(cancelled, true);
});
test("empty body is supported", async () => {
  assert.equal(await readRequestBody(new Request("http://localhost/", {method:"POST"})), "");
});
