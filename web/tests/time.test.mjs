import test from "node:test";
import assert from "node:assert/strict";
import {formatUtc, formatUtcTime} from "../lib/time.mjs";

test("offset timestamps represent the same UTC instant across date boundaries", () => {
  assert.equal(formatUtc("2026-11-05T00:30:00+08:00"), "2026-11-04 16:30:00.000 UTC");
  assert.equal(formatUtc("2026-11-04T16:30:00Z"), formatUtc("2026-11-05T00:30:00+08:00"));
  assert.equal(formatUtcTime("2026-11-05T00:30:00+08:00"), "16:30:00.000 UTC");
});
test("missing, malformed and epoch-zero timestamps stay distinct", () => {
  assert.equal(formatUtc(null), "Not recorded");
  assert.equal(formatUtc("broken"), "Invalid timestamp");
  assert.equal(formatUtc("2026-11-05T00:30:00"), "Invalid timestamp");
  assert.equal(formatUtc(0), "1970-01-01 00:00:00.000 UTC");
});
