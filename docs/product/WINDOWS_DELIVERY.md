# Windows local delivery record

Date: 2026-11-06. Scope: the local working tree, not a published release.
Owner decisions: Windows first; Linux later; MIT project licensing; no push,
remote PR or deployment. This record consolidates evidence, not new test runs.

## Implemented local product

| Requirement | Implementation and evidence |
|---|---|
| Safe legacy startup | Repaired Streamlit syntax/security defaults, denied unsafe legacy paths, automated smoke and boundary tests |
| Shared diagnostics | DNS/TCP/TLS/HTTP HEAD plus opt-in ICMP/traceroute; typed measurement contracts; exact-origin policies, address checks and numeric pinning |
| Measurement correctness | Separate component timings and ICMP RTT, explicit UTC/vantage, TLS certificate evidence; Windows high-resolution timing fix; real IPv4/IPv6 TLS fixtures |
| Persistence and isolation | FastAPI authentication, SQLAlchemy, versioned migrations, tenant constraints; local SQLite and real PostgreSQL 17.11 tests |
| Durable monitoring | Worker leases, threshold incidents, missing telemetry, pause/resume, bounded queue expiry and retention; controlled PostgreSQL lock-order test |
| Windows Agent | Outbound HTTPS, single-use enrollment, revocation/rotation, independent local policy, OS-keyring, bounded spool and OS-owned instance lock |
| Comparisons | Atomic cloud/agent pair records and conservative compatibility checks; real loopback cloud-worker/Agent comparison; DNS deltas withheld when cache equivalence is unknown |
| Reports and history | Append-only retained incident links, migration backfill, paginated Web browsing; immutable redacted reports; real downloaded JSON passes offline digest verification |
| Optional AI | Local Ollama 0.40.14 with Qwen2.5 1.5B CPU; real report produced correctly cited 503/204 facts; saved/restarted/scoped API and browser views verified |
| Reproducibility | Python and pnpm lockfiles, Windows/Linux CI definitions, explicit migrations and operational commands; MIT LICENSE and asset scope NOTICE |

## Evidence locations

- VERIFICATION.md: latest consolidated Windows regression (164 Python tests, 9 Web
  tests), static checks, API schema check and production build. Earlier targeted
  counts are separate checkpoints; do not add them together.
- BROWSER_QA.md: actual UI interactions, report export defect and verified fix.
- DELIVERY_STATUS.md: implementation checkpoints and unresolved release gates.
- integration/: real TLS, process cleanup, Agent workflow, PostgreSQL and opt-in
  real-model checks. A test file or CI definition alone is not a passing result.
- README.md: dependency installation, API/worker/Web commands, target policy,
  Agent enrollment, report verification and CPU model startup instructions.

## Material limits and remaining work

- This is a local development product, not a public hosted scanning service.
  Defaults authorize no targets; administrator approval is required for each origin.
- Linux, Docker Compose, remote CI and cross-machine deployment are not verified.
  Linux is explicitly deferred by the owner. No remote service is deployed.
- Saved-pair comparison, diagnostic inspection, and monitor pause/resume/history
  passed browser verification. Enrollment-token creation/hiding, diagnostic submission,
  monitor creation, pair submission and revocation also passed, including a corrected
  stale selection regression. Targeted 320/390 px reflow and keyboard
  checks passed; broader responsive/accessibility coverage is incomplete.
- The diagnostic submission/list/detail client is generated from OpenAPI with CI
  drift checks. Other UI operations retain manual response types. Signed Agent
  distribution is not implemented; installation uses the source checkout and
  locked Python environment.
- Single-process admission controls are not a distributed abuse-control service.
  No load capacity, availability SLO or public-hosting readiness is claimed.
- Existing report snapshots include at most 1000 links; retained history is paged
  separately. Earlier links discarded by old versions cannot be reconstructed.
  Incident/pair-linked evidence needs an explicit archival policy before deletion.
- Model checks cover one real controlled incident, not general diagnosis quality.
  Qwen2.5 0.5B produced unsupported hypotheses and is not recommended. GPU inference
  failed locally; CPU on loopback port 11435 worked without driver modifications.
- Crash/replay cases are partially tested. OS lock release after process death and
  saved credential-rotation recovery passed. Real HTTPS measurements also survive
  forced termination of a separate spool-writing process and replay with server
  duplicate detection. The actual Agent main loop also passed a two-process
  save/terminate/restart/upload check with real HTTPS and no repeated probe.
  Other crash boundaries, power loss and upgrade/installer verification remain incomplete.
- The legacy portrait remains outside the MIT declaration pending provenance
  confirmation; it is excluded from the API/worker Docker build context.

No missing validation is inferred from other green checks. This record does not
mark all original release-hardening acceptance criteria complete.

## Windows workflow follow-up

After the generated diagnostic response contracts and cloud delivery expiry changes,
the real HTTPS Agent workflow was rerun on Windows with isolated SQLite storage:
`python -m pytest integration/test_agent_workflow.py -k sqlite -q`.
Result: 1 passed, 1 deselected. This exercises the controlled loopback workflow;
it is not Linux, PostgreSQL, browser, or public-network validation. Existing
remaining browser and process-crash delivery gaps above still apply.


## Forced spool-owner termination

The HTTPS workflow now sends each real 503/204 measurement to an independent
Python process running ResultSpool.save, waits for durable-save acknowledgement,
forcibly terminates that process, restores the exact payload from disk and submits
it to the real HTTPS API. The API accepts it once and identifies replay as a
duplicate; incident recovery and the evidence report still complete. Windows:
1 passed, 1 PostgreSQL parameter deselected; targeted Ruff checks passed.
This checks process termination after atomic replacement, not power loss, a crash
during replacement, or the complete Agent polling/keyring/main-loop lifecycle.


## Local source launcher

scripts/run_windows.py now checks configuration, schema, the production Web build
and fixed loopback ports, optionally migrates explicitly, and supervises API,
worker and Web. A real Windows isolated SQLite smoke run reached API/Web readiness,
ran briefly, stopped its owned process trees and passed a subsequent prerequisite
check proving both ports were released. No origins were authorized. The first run
exposed redirected-console encoding of the Chinese checkout path; this was fixed.
Worker liveness is checked, not worker readiness. A subsequent Windows Job Object change also cleans up descendants when the
launcher is forcibly terminated; there is no service manager or installer guarantee.


## Agent main-loop interruption and restart

The Windows HTTPS integration now invokes agent.client.run in separate child
processes, including its instance lock and persistent spool. The first child polls
and performs a real fixture probe, then is forcibly terminated after atomic spool
save. A new child reads that spool, sends the original upload to the real API and
clears it after acknowledgement. The server result exactly matches the saved
measurement; the target request count proves the restarted child did not re-probe.
Windows SQLite: 1 passed, 1 PostgreSQL parameter deselected; targeted Ruff passed.

The test bootstrap overrides credential lookup, fixture DNS/loopback authorization,
CA trust and lock directory and inserts blocking lifecycle checkpoints. It does
not weaken shipped Agent policy or replace HTTP transport/measurement/persistence.
Real Windows credential-store checks remain a separate earlier result. This does
not cover power loss, kill during file replacement, process death during enrollment
or rotation, expired-lease replay in the same process test, or installer upgrades.


## Windows launcher force-exit cleanup

The launcher now places itself in an unnamed non-inheritable Job Object with
KILL_ON_JOB_CLOSE before creating children. OS teardown closes its handle and
terminates descendants. Failure to create/configure/join the job aborts startup.
A Windows integration test retains process handles and verifies both child and
grandchild exit after owner termination (1 passed). A separate full-service smoke
run verified API/Web readiness, forced launcher termination and release of ports
8000/3000; normal timed shutdown and prerequisite checks also passed. No probe
targets were authorized. Targeted Ruff passed. Remote CI remains unverified.
The first fixture run failed while attempting to kill an already terminated owner
again during cleanup; the fixture was corrected, without changing Job Object logic.
This is lifecycle management of trusted local services, not hostile-code isolation.
See https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects for the
Windows lifetime/inheritance contract used by scripts/windows_job.py.


## Source-only delivery artifact

Created a local unsigned Windows source snapshot with 94 allowlisted runtime/doc
files plus BUNDLE_MANIFEST.json. Archive: netguardian-windows-source-20261106.zip;
SHA-256: 6dcce21f2a325a4146a695d00626bf52005b1fa0d1a5c36e781e4bc1e391d858.
Every manifest size/hash and ZIP entry was verified; a repeated build from the same
sources/tool runtime was byte-identical. Private keys, tests, CI, databases, logs,
installed dependencies, models and the unresolved portrait are excluded. Initial
approval review rejected including public TLS test keys; the final artifact excludes
the entire Python test/integration trees and rejects private-key paths/content.

An independent extraction installed locked Python runtime dependencies into a fresh
venv (offline attempt lacked cached wheels; normal locked download succeeded).
Migration, authenticated API/readiness and portrait-free Streamlit startup passed.
Fresh pnpm frozen/offline install, production build and TypeScript passed. The
extracted package's Windows launcher started API/worker/Web, stopped them and passed
its post-shutdown prerequisite/port check. No origins were authorized in this check.
The existing Streamlit portrait is now optional so this permitted distribution runs.

This is not an installer, signed distribution or offline dependency bundle. Full
regression and TLS fixture tests require the original repository. This archive is
a fixed checkpoint; later documentation/source changes are not retroactively inside
it. See packaging/README.md for building and using a new snapshot.


## DNS transport checkpoint

Three actual UDP DNS exchange scenarios passed on Windows: dual-stack/CNAME/TTL
metadata, NXDOMAIN classification, and mixed private-address policy rejection.
No public DNS resolver or returned public address was contacted. The existing
source ZIP remains the earlier immutable checkpoint; this later integration test
is repository-only and is intentionally outside the source-only archive.


## Server-owned receipt time

New cloud and Agent results now receive received_at at server-side persistence.
Agent-supplied timestamps in that field are overwritten, while observed_at remains
unchanged. Duplicate uploads exclude received_at when comparing original evidence
and preserve the first accepted value, including unknown values on old records.
Conflicting probe evidence still returns 409. No relational migration or historical
snapshot rewriting is required. The UI labels server receipt separately and warns
against interpreting a cross-clock difference as network latency.

Ten targeted Agent/worker/evidence tests passed, including forged receipt time,
duplicate stability, legacy unknown receipt and conflicting evidence. The actual
SQLite HTTPS Agent kill/restart/upload workflow passed (1 passed, 1 PostgreSQL
parameter deselected). Ruff and Web build/TypeScript passed. The source ZIP is the
previous checkpoint and does not include this subsequent change. PostgreSQL was not rerun in this checkpoint. A subsequent creation-workflow
browser check displayed the server receipt field and its clock/latency caveat.


## Streamlit shared-core adapter and archive configuration fix

An opt-in Streamlit V2 section now authenticates to the configured API, lists only
approved origins, queues persistent jobs and displays validated shared Measurement
results. It reuses CreateJob/JobAccepted/JobSummary/JobDetail instead of duplicating
probe transport or schemas. Default flag-off behavior and legacy direct paths stay
disabled. Control URLs reject non-loopback plaintext, userinfo/path/query/fragment;
responses have a 10-second overall deadline, 256 KiB ceiling and no redirects/proxies.

Twenty targeted tests passed: origin/response boundaries, legacy safety defaults,
and AppTest login/queue/read/disconnect through the real in-process API and SQLite.
The actual shared executor completed an IP-literal DNS task (no resolver/network
traffic) and UI rendered its persisted result. Tests found and fixed Streamlit
widget-state cleanup losing the token and changing status labels clearing job
selection. This is not a browser/remote HTTPS deployment test for the adapter.

The source allowlist also now includes .streamlit/config.toml, previously omitted
from r1/r2. Older archives require an explicit --server.address 127.0.0.1 for
Streamlit; r3 carries the safe default. API/Web launcher binding was already loopback.
