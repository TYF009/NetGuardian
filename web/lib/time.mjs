function timestamp(value) {
  // Never interpret an offset-free server string in the browser's local timezone.
  if (typeof value === "string" && !/(Z|[+-]\d{2}:\d{2})$/.test(value)) return null;
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toISOString() : null;
}
export function formatUtc(value) {
  if (value === null || value === undefined || value === "") return "Not recorded";
  const iso = timestamp(value);
  return iso ? iso.replace("T", " ").replace("Z", " UTC") : "Invalid timestamp";
}
export function formatUtcTime(value) {
  const iso = timestamp(value);
  return iso ? iso.slice(11, -1) + " UTC" : "Invalid timestamp";
}
