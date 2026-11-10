# Local browser QA

## Verified on 2026-11-05

Environment: Windows, production Next.js build on loopback port 13000,
FastAPI on loopback port 8000, fresh temporary SQLite database, no authorized
origins, no worker. Authentication used a test-only local token.

Observed through the browser UI:

- Login opens the workspace and displays zero records.
- Diagnostics: no authorized targets; Run diagnostic is disabled.
- Monitors: empty state, pause/resume explanation, Create monitor disabled
  without an authorized target.
- Incidents: empty state explicitly does not imply target health.
- Agents: no enrolled agents; enrollment form renders. No enrollment performed.
- Compare: empty selectors; Compare evidence disabled.
- Disconnect returns to the login form with an empty token field.

Limits: this verifies navigation and empty-state behavior only. It does not
verify populated charts, probe execution, pause/resume clicks against an existing
monitor, report downloads, Agent registration, AI provider behavior, responsive
breakpoints, or delayed-response races after logout. Those remain release gates.

## Subsequent session-isolation change

The workspace now remounts on disconnect, aborts its pending requests, and rejects
follow-up requests from a detached session. Polling skips overlapping intervals.
This change passes TypeScript and production compilation. The browser observations
above predate this change; delayed-response logout and re-login remain unverified.


## Populated workflow check (2026-11-05)

Windows in-app browser, local Next development server and FastAPI; isolated SQLite
records created by the real HTTPS integration test. No authorized targets and no
worker were enabled in the browser session, so viewing did not initiate probes.

Observed: four diagnostics, one agent monitor, two history rows with HTTP 503 and
204; timing metric selector, accessible chart summary and evidence actions rendered.
The saved report opened with verified checksum, recovered incident, two referenced
observations and explicit limitations. The narrow browser view wrapped report
controls and long identifiers. Disconnect removed all records and returned an empty
token input. Servers were stopped after checking. Download, mutation controls,
delayed-response races and a full responsive breakpoint matrix remain unverified.

This check exposed coarse short-duration readings on Windows Python 3.11:
`monotonic` reported GetTickCount64 with 0.015625-second resolution, while
`perf_counter` reported QueryPerformanceCounter with 0.0000001-second resolution.
Probe 0.2.1 uses the latter monotonic clock for durations. Historical observations
are not rewritten. The clock resolution is not a network precision/performance
claim. Browser observations above used pre-fix records; transport regression after
the fix is tracked independently.


## Retained history, production Web build (2026-11-05)

Verified in the in-app browser against isolated loopback API/Web servers. The
fixture contained 101 failed tasks with **no measurement payloads** and a paused
monitor; no probes or model calls ran. It is UI test state, not network evidence.

- Opened Incidents and Browse retained history.
- First page contained 100 inspection controls; Previous disabled, Next enabled.
- Next page displayed position 101; Next disabled and Previous enabled.
- Inspect displayed the matching failed task and explicitly stated that missing
  measurements do not establish target health.
- Previous returned to 100 rows with the expected button states.
- Disconnect returned to the empty token form and removed workspace data.

A viewport screenshot was saved locally as `netguardian-history-qa.png` in the
session workspace. Full-page screenshot capture failed; viewport capture worked.
The two temporary local server sessions were stopped after the check. This does
not verify report downloads, AI quality, Linux or cross-machine networking.


## Real-model investigation and report export (2026-11-06)

Used an isolated database populated by the passing real Qwen2.5 1.5B CPU API
workflow, importing the previously recorded HTTPS 503/204 evidence snapshot.
The browser displayed saved investigation history, both evidence-checked integer
status facts, their original job IDs, model/prompt identity, no causal hypothesis,
limitations and the source snapshot digest. Open source report succeeded with
verified integrity. Disconnect cleared the session. A viewport screenshot was
saved as `netguardian-investigation-qa.png` in the session workspace.

The first actual JSON download failed offline checksum verification. Browser
JSON reserialization changed recorded floating-point zeros from `0.0` to `0`.
Export now fetches the authenticated original report as a Blob, preserving the
server's JSON representation. After rebuilding and repeating the browser download,
`python -m scripts.verify_report` verified the downloaded file against digest
`930e99063faf2855f4dbd3f80df813f86c8259508cb1e106fa4318faaf18cf44`.
Snapshot integrity does not verify authorship or measurement accuracy. Both local
API/Web test sessions were stopped; the separately installed CPU model service
was not stopped by this browser test.


## Windows saved comparison and monitor controls (2026-11-06)

Using the production Web build and an isolated SQLite database populated by the
real HTTPS Agent workflow, browser interaction verified:
- Generated diagnostic client lists four persisted jobs and opens a real HTTP
  measurement with component timings, TLS evidence and HTTP 204.
- Saved pair comparison selects both recorded job IDs and returns comparable=true,
  with DNS delta withheld and explicit HTTP-total-versus-ICMP limitations.
- With no authorized origins, new diagnostic/pair/monitor controls are disabled.
- Pause changes the active count from 1 to 0 and collection state to paused.
- Resume without an origin policy is rejected with "No target policy configured".
  After configuring only the fixture origin, resume returns the count to 1 and
  collection state to stale, correctly avoiding a healthy-target assertion.
- History shows the real 503 then 204 observations with separate timing values.

The API was restarted between the denied and successful resume, also demonstrating
that paused state persists. No worker was running during UI checks; no new probe
was dispatched. Pair submission and Agent-management mutations were not covered
by this browser pass. Screenshot: netguardian-monitor-resume-qa.png in the local
verification output directory (not a repository release artifact).


## Pair submission and revoked selection regression (2026-11-06)

In the isolated workflow workspace with no worker/Agent executor running, the UI
queued one cloud/local pair: job count increased by two and the saved pair retained
both IDs. Comparing before measurement availability produced "Measurement not
available", not a comparative conclusion. Revoking the fixture Agent displayed
Revoked, disabled its Revoke action and stopped its associated monitor.

This exposed a stale selection bug: after revocation, the selected ID remained in
React state while its option disappeared, leaving the pair submission button enabled.
The backend still rejected unauthorized work. The UI now retains an explicit
unavailable option, disables diagnostic/monitor/pair submission and guards submit
handlers. It never silently changes local-vantage intent to cloud execution.

The production build/TypeScript check passed. A fresh isolated test Agent reproduced
the revocation sequence in the rebuilt browser: the unavailable option remained
selected and both pair and diagnostic buttons were disabled. Screenshot:
netguardian-revoked-agent-qa.png in the local verification output directory.
Enrollment-token creation in the browser and broad responsive QA remain unverified.


## Narrow viewport and measurement identity (2026-11-06)

The production build was inspected at 390x844 and 320x740 using an isolated existing
workflow database, no target authorization and no worker. Login was submitted with
Tab/Enter. A recorded real fixture observation was opened with Enter; its expandable
Measurement identity summary also responded to Enter and showed a visible focus
outline. Probe version 0.2.1, attempt 1, schema 1, UTC observation time, policy
version and configuration hash were visible. No synthetic measurements were added.

At both widths the document stayed within the viewport (the scrollbar reduced the
content width by 15 px). The diagnostic table scrolls inside its wrapper. At 320 px,
the populated monitor-history SVG measured 219 px and exposed its metric/unit and
observation-count accessible label; the data table remained available. The viewport
override was reset after checks. Screenshot: netguardian-narrow-evidence-qa.png in
the local verification output directory.

This is targeted reflow and keyboard smoke coverage, not a WCAG audit, screen-reader
certification, exhaustive tab-order check or validation of every panel/device.
Error-category rendering was type-checked previously but no failed measurement with
an error payload was opened in this particular browser pass.


## Creation workflows and receipt-time rendering (2026-11-06)

A new isolated workspace verified the remaining creation operations through the
production Web UI. Enrollment-token creation showed single-use/10-minute guidance;
Hide token removed it. The token was not redeemed and no value was retained in
screenshots or this record. A DNS job for an approved IP-literal target was queued
from the form. Before execution, the queue was inspected to ensure only this DNS
literal task existed; one actual shared worker iteration completed it without any
DNS query or connection to the returned address. The UI showed succeeded, explicit
no-DNS-query semantics, no connected IP, probe version, and distinct observed and
server-received UTC timestamps with the clock/latency caveat.

Monitor creation produced one active record with awaiting-first-run telemetry;
pause changed it to paused and the active count to zero. No scheduler was running,
so no monitor probe executed. Disconnect returned to a blank token input and cleared
visible records. Screenshot: netguardian-create-workflow-qa.png in the local output
directory, after hiding the enrollment token. Test API/Web services were stopped.
This complements earlier real DNS/TLS/Agent and scheduler integration, rather than
claiming that the DNS literal experiment measured an external network.
