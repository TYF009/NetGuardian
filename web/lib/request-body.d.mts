export class BodyReadError extends Error {
  status: number;
  constructor(message: string, status: number);
}
export function readRequestBody(request: Request, maxBytes?: number, timeoutMs?: number): Promise<string>;
