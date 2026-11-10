# NetGuardian V2 Implementation Plan

Status: original migration plan plus historical implementation notes. The working tree now contains multiple implementation stages; see DELIVERY_STATUS.md for current evidence and remaining gates.

## Audit scope and evidence
All four tracked files at `b0ce286802db07d02a912de2bcc577de3f2a6deb` were read or visually inspected. Git history, deployed service, dependency vulnerabilities and production settings were not audited. There is no dependency inventory to substantiate CVE claims. Static inspection identifies the following; only the syntax failure was independently checked with Python AST parsing.

| Priority | File / location | Finding and consequence |
|---|---|---|
| P0 | app.py, immediately after default_sites | Extra `}` prevents parsing and startup; AST check confirms unmatched brace |
| P1 | app.py, check_http_status / check_port | Arbitrary server-side URLs/ports enable SSRF and network probing when reachable; no quotas or access controls |
| P1 | app.py, run_traceroute | Shell interpolation is an unsafe execution boundary; current UI uses fixed targets, so direct input exploitability is not demonstrated |
| P1 | .devcontainer/devcontainer.json, postAttachCommand | Explicitly disables CORS and XSRF protections |
| P1 | app.py, get_ping_latency | Measures HTTPS HEAD request duration with wall clock, not ICMP RTT; status ignored and failures collapsed to None |
| P2 | app.py, st.columns / trace selection | Empty target selection passes zero columns and leaves no valid trace target; needs an explicit empty state |
| P2 | app.py, latency display | Valid zero-millisecond rounded samples are shown as Timeout; unrelated errors also labeled Timeout |
| P2 | app.py, while True | Browser-session loop, sequential probes and sleep cause interval drift; no durable schedule or incident history |
| P2 | app.py, get_public_ip / sidebar | External failure JSON can omit keys and crash rendering; displayed identity is the server's, not necessarily the user's |
| P2 | app.py, run_traceroute | Windows command and GBK decoding conflict with Linux devcontainer; no total subprocess timeout; IPv4-only parsing drops missing hops and IPv6; errors return string where UI expects tabular data |
| P2 | app.py, check_port | IPv4 only; unrestricted numeric port input; closed, filtered and other socket failures conflated |
| P2 | app.py, get_ip_info | Plaintext third-party requests disclose addresses; private-range classification incomplete; route location is not reliable path attribution |
| P2 | app.py, history / exception handling | Time-only timestamps lose dates/timezones; session data is ephemeral; broad exceptions erase diagnostic evidence; DNS has no explicit application deadline |
| P2 | README.md | Claims ICMP/TCP latency while implementation uses HTTP; claims exact routes/CDN identification beyond evidence; clone command/repo name wrong, code fence unfinished, referenced requirements.txt absent |
| P2 | .devcontainer/devcontainer.json | Missing dependency manifest, unconditional success message despite possible install failures, unpinned installs and broad apt upgrade undermine reproducibility |
| P2 | repository | No tests, CI, license or dependency locks; UI, networking and persistence concerns coupled in one script |
| Info | Felix.jpg | Portrait used by sidebar; no functional defect observed. Asset redistribution permission remains unverified |

## Incremental delivery
Each row is a separately reviewable PR or small PR series. Do not deploy cloud execution before the policy gate passes.

| Step | Scope and dependency | Acceptance criteria |
|---|---|---|
| 1 | Repair and contain legacy app | Parse/startup smoke passes; explicit dependencies; empty selection works; HTTP timing labeled accurately; unsafe arbitrary HTTP/TCP tools disabled until policy exists; no shell invocation; restore framework security defaults; tests run in CI |
| 2 | Shared schemas and target policy, after 1 | Versioned Pydantic request/result fixtures; durations/errors distinct; all special-address, rebinding, redirect and port-policy negative cases reject before connection; no user command fields |
| 3 | Extract probe-core, after 2 | DNS/TCP/TLS/HTTP adapters tested against local controlled fixtures; deadlines, body caps and certificate errors verified; Streamlit consumes the same core; no uncontrolled external test traffic |
| 4 | API, PostgreSQL and worker, after 3 | Authenticated job create/read; tenant-isolation tests; migrations upgrade clean database; lease crash/retry/idempotency tests; Compose starts reproducibly; backup restore smoke passes |
| 5 | Next.js diagnostic slice, after 4 | User submits approved target, sees durable result, error and vantage; typed OpenAPI client; accessibility/empty/loading states; legacy rollback remains available |
| 6 | Monitoring/incidents, after 4–5 | Browser-independent scheduling; duplicate occurrences deduplicated; missing data separate from failure; opening/recovery thresholds and history tested; retention job verified |
| 7 | Agent enrollment and packaging, after 3–4 | Windows/Linux supported matrix declared; outbound-only operation; single-use enrollment, rotation/revocation, local policy, bounded spool and version mismatch tests; release verification documented |
| 8 | ICMP/traceroute, after 3 and platform fixtures | Permission denied is explicit; packet/hop/time caps; IPv4/IPv6 and missing-hop fixtures; no full-service administrator requirement |
| 9 | Cloud/local comparisons, after 6–7 | Matching configuration/group IDs; skew and IP/resolver differences visible; unmatched or stale results cannot imply a comparative conclusion |
| 10 | Deterministic reports then optional AI, after 6/9 | Reproducible redacted evidence export; retained citations; unsupported claims labeled; prompt-injection fixtures; cross-tenant evidence rejected; model outage leaves reports usable |
| 11 | Release hardening | Load-test budgets documented, security matrix passes, supported platforms tested, operational runbooks and license selected; no claim of unmeasured capacity |

## Migration safeguards
Freeze new functionality in Streamlit beyond safety and shared-core adaptation. Introduce features behind explicit flags and compare recorded fixtures rather than probing unapproved public services. Keep old HTTP duration data labeled legacy HTTP observations; never convert it into ICMP or component timings. There is no database backfill from the current session state. Switch default UI only after diagnostic parity, security checks and operator review. Roll back UI/API versions with compatible schemas; never restore unrestricted scanning.

## Proposed first implementation PR
**Title: Restore safe Streamlit startup and establish baseline checks.**

Remove the unmatched brace; declare and lock direct/runtime dependencies; add an empty-selection state; rename HTTP request timing and distinguish zero/failed samples; label identity as probe-server identity. Temporarily disable free-form HTTP/TCP execution and traceroute until shared policy and safe platform adapters land. Restore CORS/XSRF defaults, correct README setup and capability claims, and add syntax, pure helper and UI smoke checks using mocked networking. No Next.js rewrite, database or AI work in this PR.

Acceptance: clean-environment install and syntax/UI smoke pass; no uncontrolled network activity in tests; no unsafe free-form probe path or shell subprocess remains reachable; security defaults retained; README matches actual limitations. Application changes are intentionally deferred to that PR. This proposal does not open or publish a PR.

## Phase 1 implementation update (2026-11-04)

The original audit above describes commit b0ce286, not the repaired working tree.
Phase 1 now restores a runnable Streamlit UI and fails closed at every legacy probe
entry point. HTTP monitoring, DNS, TCP, traceroute, identity enrichment and their
charts/exports are temporarily unavailable until approved measurements can be collected.
This broader containment is intentional: fixed hostnames do not prevent DNS rebinding
or establish authorization. No mock measurements are shown to users.
Dependency locking, linting and offline UI/security regression checks are provided.
See README for commands; remote CI execution and cross-platform results must be
verified separately rather than inferred from the workflow definition.

## Historical step 2 implementation boundary

Versioned Pydantic envelopes and a pure HTTP(S) cloud-policy foundation now exist in
`probe_core`. Tests cover malformed targets, special addresses, mixed DNS answers,
changed DNS answers, redirect authorization, immutable policies and measurement semantics.
At that checkpoint this did not complete the transport acceptance gate: zero real network connections were
made because no transport was implemented. DNS/TCP/TLS-specific authorization adapters,
full protocol result payloads, shared quotas, resolver deadlines, actual numeric-address
connection pinning and TLS hostname verification remain required before re-enabling probes.
The policy deliberately rejects Unicode hostnames and trailing-dot forms for now.

## Current-state interpretation

The audit and stage notes above preserve their original checkpoints; they are not
current capability claims. README describes the present source and local setup.
DELIVERY_STATUS.md records unfulfilled release gates. No remote PR, deployment or
release has been created by this implementation session. Stage acceptance remains
partial wherever platform, persistence, UI or operational evidence is missing.
