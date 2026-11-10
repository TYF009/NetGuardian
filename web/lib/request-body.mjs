/** Bound bytes before decoding, including chunked requests and slow senders. */
export class BodyReadError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

export async function readRequestBody(request, maxBytes = 8192, timeoutMs = 10000) {
  const encoding = request.headers.get("content-encoding");
  if (encoding && encoding.toLowerCase() !== "identity")
    throw new BodyReadError("Unsupported content encoding", 415);
  const length = request.headers.get("content-length");
  if (length !== null && !/^\d+$/.test(length))
    throw new BodyReadError("Invalid content length", 400);
  if (length !== null && Number(length) > maxBytes) {
    void request.body?.cancel().catch(() => {});
    throw new BodyReadError("Request too large", 413);
  }
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  let timer;
  const deadline = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new BodyReadError("Request body timed out", 408)), timeoutMs);
  });
  try {
    while (true) {
      const {done, value} = await Promise.race([reader.read(), deadline]);
      if (done) break;
      size += value.byteLength;
      if (size > maxBytes) throw new BodyReadError("Request too large", 413);
      chunks.push(value);
    }
    const bytes = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      bytes.set(chunk, offset);
      offset += chunk.byteLength;
    }
    try { return new TextDecoder("utf-8", {fatal: true}).decode(bytes); }
    catch { throw new BodyReadError("Invalid UTF-8 request body", 400); }
  } catch (error) {
    // Do not await cancellation: a stalled producer must not delay the rejection.
    void reader.cancel().catch(() => {});
    throw error;
  } finally {
    clearTimeout(timer);
    reader.releaseLock();
  }
}
