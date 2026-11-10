# Product completion checklist

Current scope: Windows local delivery first, per owner decision on 2026-11-06.
Linux support and validation are deferred, not prerequisites for this Windows milestone.
This checklist records remaining work, not a release claim.
See ACCEPTANCE_MATRIX.md for the original requirement-by-requirement assessment.
The latest consolidated local regression is recorded in VERIFICATION.md.

| Area | Current evidence | Remaining release gate |
|---|---|---|
| Core policy | Negative-input tests; pinned-transport doubles; Windows IPv4/IPv6 loopback real TLS trust/hostname/fingerprint tests | Remaining protocol fields, Linux TLS/IPv6 platform checks |
| API and jobs | Auth, persistence and tenant tests; concurrent workspace initialization tested on SQLite; Windows PostgreSQL 17.11 migration/concurrency/tenant and real HTTPS workflow tests passed; remote CI not run | Remaining audit coverage, aggregate multi-replica admission controls and broader concurrent-load verification (controlled PostgreSQL retention/scheduler overlap passed) |
| Monitoring | Schedule/threshold/recovery and authenticated pause/resume tests | Broader concurrent-load verification (controlled retention/scheduler overlap passed) and cross-machine agent schedule verification (real loopback HTTPS scheduling/incident recovery passed) |
| Web | TypeScript/build; local browser login, navigation, empty states and disconnect (BROWSER_QA.md) | Broader responsive/accessibility QA beyond the tested 320/390 px and keyboard flows (creation, pair submission, Agent revocation, saved-pair comparison, freshness, pause/resume, history, report and disconnect inspected) |
| Agent | Enrollment/replay/revoke and local policy tests; Windows real HTTPS enrollment-to-report loopback workflow with spool reload/duplicate replay passed | Linux OS-keyring checks (Windows write/read/cleanup passed), real process-crash and cross-machine recovery verification (Windows OS-keyring plus HTTPS lost-acknowledgement-state recovery and revocation passed), signed distribution |
| ICMP/traceroute | Bounded fixed-command adapters and platform fixture tests | Linux/denied-permission checks, broader locale coverage, Linux process cleanup verification (Windows real timeout/cancel/output-limit cleanup and IPv4/IPv6 loopback ping/tracert passed) |
| Reports | Immutable snapshot/redaction/citation tests | Broader export-size/archival policy (retained history pagination and actual download checksum verified) |
| Comparison | Conservative evidence comparison tests; real HTTPS cloud-worker/agent paired execution and comparison passed on Windows loopback | Cross-machine paired cloud/agent runtime and resolver cache comparability (endpoint/TTL recorded; atomic enqueue tested) |
| AI investigation | Real Windows CPU Ollama/Qwen2.5 1.5B evidence validation and API persistence/isolation passed; failure fallback unit tests | Broader diagnosis-quality evaluation (persisted history/source-report browser QA passed) |
| Operations | Compose and runbook written | Docker Compose and Linux/remote CI verification (portable Windows PostgreSQL startup and backup/restore content comparison passed) |
| Open source release | Repository public | MIT selected; legacy portrait excluded pending redistribution-rights confirmation |

Do not mark the product complete while required gates lack evidence. Do not infer Linux,
PostgreSQL, deployment or performance results from Windows/SQLite tests.

## Agent single-instance checkpoint

The Agent now holds an OS-owned file lock for its server/identity while running.
Concurrent instances under the same OS user are rejected before credential rotation
or result-spool access. A real Windows child-process test verifies exclusion and
lock release after terminating the lock owner; this is not a crash-recovery test
for measurement delivery. Lock files contain no credentials and remain on disk.
Different OS users or machines must not share one enrollment. Linux execution and
Windows directory ACL enforcement remain unverified.

## PostgreSQL retention checkpoint

An isolated Windows PostgreSQL 17.11 run passed seven integration tests, including
retention preview/apply, preservation of incident evidence, the latest 100 monitor
runs, both paired jobs, queued work and another workspace's rows. Expired eligible
jobs and their monitor links were removed; repeated apply selected nothing.
The same run verified UTC-aware timestamp retrieval and completed the real HTTPS
Agent/report workflow. Backup and restore matched row counts and content digests
across all 12 public tables. This does not verify concurrent retention versus
scheduling, Linux, Docker or a production database. Only disposable fixtures were
modified. An initial run exposed shared-test queue pollution; the fixture now
closes its queued job after assertions, and the complete integration group passed.

## Report wording checkpoint

New report claims distinguish probe execution status from HTTP response status.
A completed HTTP 503 probe now explicitly cites 503 and states that successful
execution does not imply application health. Existing immutable snapshots are
not rewritten. Five targeted evidence tests passed, including redaction,
isolation, snapshot integrity and the HTTP/non-HTTP claim wording. The latest
1000-observation limit remains; complete long-incident history is not implemented.

## Web build checkpoint

The current Next.js production build passed, including TypeScript compilation.
The incident detail action now disables inspection when no evidence is linked,
preventing requests for an undefined job ID, and respects the in-flight action
state. Report JSON download and remaining mutation flows still need browser QA;
a successful build does not prove those behaviors. The parent-directory pnpm
workspace warning did not prevent the build.


## Long-incident history checkpoint

New monitoring transitions preserve every incident/job link in a separate table;
list responses and individual report snapshots remain bounded at 1000 links.
SQLite tests verified a 1002-observation incident, ordered API pagination, tenant
isolation, retention protection and migration of existing missing measurements.
The earlier 1000-link limitation now applies to summaries, not newly stored
history. Previously discarded links cannot be recovered. Full-history browser
navigation and archival lifecycle remain pending. Run `uv run alembic upgrade
head` before starting this version; do not downgrade a populated history table.

The new schema also passed the seven-test Windows PostgreSQL integration group;
backup/restore content matched across 13 tables, including `incident_evidence`.
The run exposed and fixed a previous enrollment-audit resource length issue:
issuance uses a separate UUID rather than the potentially 128-character workspace
name. The UUID identifies the issuance audit resource and contains no token data.
All temporary PostgreSQL processes were stopped after verification.


## Incident history Web integration

The Incidents tab now offers retained-history browsing, previous/next pages and
individual job inspection. Each response/page is limited to 100 links. The proxy
forwards only numeric `after`/`limit` parameters for this endpoint and rejects
unknown or repeated pagination fields. Missing measurements remain explicit; old
history limitations are shown. The production build and TypeScript passed after
integration. Browser interaction verification for this new panel is still pending.

Retained-history browser verification now passed for 100/101 pagination, missing
measurement inspection, return navigation and disconnect; see BROWSER_QA.md.


## Scheduler/retention concurrency checkpoint

Fixed an inverse lock-order path by committing result processing before workspace
admission. A controlled PostgreSQL test overlaps result processing and retention;
both finish and preserve the newly linked evidence. The eight-test PostgreSQL
integration group passed, and backup/restore digests matched all 13 tables. This
covers that specific lock cycle, not arbitrary concurrency/load performance.


## Real local model checkpoint (2026-11-06)

Ollama 0.40.14 and Qwen2.5 0.5B were installed with user authorization. Installer
SHA-256 matched the winget manifest; model pull completed its own digest check.
The default GPU runner failed with `CUDA error: device kernel image is invalid`.
An isolated loopback CPU server on port 11435 successfully ran inference without
changing drivers. Prompt v2 restricts citation IDs to provided evidence through
JSON-schema enums and explicitly requires original JSON scalar types.

An existing report from the real loopback HTTPS workflow (two observations,
HTTP 503 then 204) was used. Initial invented citations were rejected. A later
response copied both status facts correctly but supplied contradictory DNS/TCP/TLS
failure hypotheses; this does not pass diagnosis-quality acceptance. The full
real-model API workflow also returned rejected_or_unavailable and failed its
acceptance test. Seven existing output/transport unit tests passed. Qwen2.5 0.5B
is therefore not a recommended default; a 1.5B model download was started for
further evaluation. Installation success is not product AI acceptance.


## Real local model integration passed (2026-11-06)

Qwen2.5 1.5B finished downloading and verifying. On Ollama 0.40.14's CPU runner,
the unchanged real HTTPS report produced two correctly cited integer HTTP facts
(503 and 204) and no unsupported hypotheses. The standalone evidence verifier
passed. The opt-in real API workflow test passed: creation, nonempty validated
facts, saved evidence hash, cross-workspace denial, listing and restart retrieval.
This is evidence of local model integration, not a general diagnosis-quality
benchmark. The 0.5B failures above remain valid historical findings. The GPU
runner issue remains unresolved; the separate CPU endpoint is 127.0.0.1:11435.


## Readable investigations and export integrity

The Web now separates evidence-checked facts, unverified hypotheses and limitations,
with model/prompt identity and source-report access. Creation and retrieval return
consistent investigation metadata. Eight targeted unit tests, one updated real
model API test and the production Web build passed. Browser inspection confirmed
the saved real-model findings and source report. The real download test found and
fixed JSON number reserialization invalidating the snapshot digest; raw-server
JSON downloads now pass offline verification. See BROWSER_QA.md for evidence and
scope. No broader model-quality or cross-platform claim follows from this test.


## Windows scope and license decision

The owner selected Windows-first delivery and deferred Linux; no new OS components
will be installed for this milestone. MIT licensing is now recorded in LICENSE
and project metadata. NOTICE.md preserves the unresolved legacy portrait scope.
Docker build context excludes local verification caches/downloads and the portrait.
These changes do not claim Docker or Linux runtime validation. The consolidated
Windows Python regression passed 153 tests, with static/format checks passing.


## Offline cloud-worker delivery expiry

Cloud jobs now share bounded, audited delivery expiry with the Agent lifecycle.
A 120-second age limit is enforced on API job reads/submission and worker/scheduler
activity, preserving active leases and avoiding fabricated measurement results.
A restarted worker cannot claim old work. Ten targeted lifecycle/API/monitoring
and worker tests passed, including tenant-scoped observation with no worker,
no duplicate audit and active-lease protection. This is demand-evaluated expiry,
not a background timer running when all services are stopped. No database schema
change is required.


## Generated diagnostic contract

FastAPI declares job acceptance, summary and detail response models, reusing the
shared Measurement model. An isolated deterministic schema exporter and pinned
OpenAPI TypeScript generator supply the diagnostic client's request/response types.
The UI uses the client for submission, listing and evidence detail lookup, retaining
abort-on-disconnect and active-session checks. CI checks schema/type drift. Nine
Web tests, three relevant backend tests, schema check and production build passed.
Compile-only checks reject arbitrary probe kinds and omitted required parameters.
The generated contract exposed optional timing fields; missing values are skipped,
not displayed as zero. Other page response types remain manual. Node.js 24 is now
the documented/tested Web toolchain and CI version. Remote CI has not run.


## Agent delivery loop restart branches

Ten offline tests now run the actual run_locked loop against a streaming mock HTTP
transport and a test credential store. A pre-existing spool must be delivered
before any poll or probe. Valid first/duplicate acknowledgements clear the spool;
malformed acknowledgements and HTTP 503 retain it; HTTP 401/403 retain it and stop
the Agent; terminal HTTP 404/409/422 clear it without rerunning the probe. All ten
passed on Windows with targeted Ruff checks. The initial fixture used an already
consumed response stream; correcting the fixture resolved four test failures.
No application behavior was changed for these checks. These tests complement the
real HTTPS/spool-owner termination test; they do not establish complete CLI crash,
OS-keyring, cross-machine or power-loss recovery.


## Real HTTP admission saturation

A bounded Windows loopback test occupied all 32 default active API slots, verified
8 excess requests receive 429/Retry-After, checked health/readiness while saturated,
and confirmed authenticated requests succeed after release. The single test and
Ruff checks passed; it is included in CI. See RUNBOOK.md for explicit experiment
budgets and limits. No sustained-load, memory, throughput or multi-replica claim is
made. This narrows the concurrency-verification gap but does not close those gates.


## Actual Agent loop process restart

The real HTTPS workflow now also starts the production Agent run function in a
child, kills it after saved measurement, then starts another child which uploads
that exact evidence and clears the spool. A fixture request count excludes repeated
probing. Windows SQLite and targeted Ruff passed. Credential lookup is a test store;
CA/DNS/private-target overrides remain confined to the test bootstrap. This closes
the previously missing post-save main-loop restart case, not every crash point or
OS-keyring/installer lifecycle. See WINDOWS_DELIVERY.md for the precise boundary.
