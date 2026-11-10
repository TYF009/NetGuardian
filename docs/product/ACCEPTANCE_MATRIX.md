# Requirement-to-evidence acceptance matrix

Date: 2026-11-06. Scope: local Windows delivery. This is not a declaration that
all original implementation-plan release gates are complete. Evidence is the actual
runs in VERIFICATION.md, BROWSER_QA.md and WINDOWS_DELIVERY.md, not the presence of
source files or CI definitions alone. Linux is deferred by the owner. No push,
remote PR or deployment has been performed.

## Product requirements

| Requirement | Current implementation and observed evidence | Boundary |
|---|---|---|
| Controlled server diagnostics | Shared DNS/TCP/TLS/HTTP core, typed authenticated jobs and exact-origin policy; real UDP DNS and IPv4/IPv6 TLS fixtures, persisted workflow | Controlled local server vantage verified; no hosted deployment |
| Optional local Agent | Outbound HTTPS, enrollment/rotation/revocation, independent policy, OS-keyring, spool and instance lock; real HTTPS workflow and post-save process restart passed | Windows verified; Linux deferred; cross-machine installation and other crash boundaries unverified |
| Continuous monitoring/history | Worker-driven schedules, thresholds, telemetry freshness, append-only incident links, retention; SQLite/PG lifecycle tests and browser history/pause/resume | No sustained-load capacity claim or automatic incident archive policy |
| Cloud/local comparison | Atomic pair record, compatibility/skew/IP checks and metric-specific caveats; actual loopback paired execution and browser submission/comparison passed | DNS cache equivalence is unknown, so DNS deltas withheld; no causal conclusions |
| Explainable AI investigation | Redacted bounded report evidence, exact fact/citation validation, unverified hypotheses, persistence/failure fallback; real CPU Qwen2.5 1.5B API/browser case passed | One controlled incident is not broad diagnostic-quality certification |
| Evidence reports | Immutable redacted snapshots, retained IDs, integrity checks and raw-byte download; actual downloaded file verified offline | Latest 1000-link report scope disclosed; full history separately paged; no digital signature |
| ICMP/traceroute | Opt-in bounded fixed executables, no shell, IPv4/IPv6 and locale/missing-hop fixtures; Windows loopback/runtime cleanup passed | Locale/permission environments beyond the tested fixtures unverified |
| Measurement semantics | Separate timings/UTC/vantage/version, explicit unknowns; latest receipt time is server-owned and replay-stable | Cross-clock observed/received difference is not network latency; old receipt times stay unknown |
| Safe resource boundaries | SSRF negative tests/pinning, typed commands, tenant constraints, bounded body/jobs/processes; real HTTP 32-slot saturation/recovery passed | Process-local controls are not ingress-wide protection; egress firewall not provisioned |
| Reproducible local operation | Locked dependencies, explicit migrations, Windows launcher/forced-exit cleanup, source allowlist/checksums; independent extracted install/build/start passed | Unsigned source distribution requires dependencies and a build; not a service installer |
| Collaboration/artifacts | Root AGENTS.md language rules; all five baseline documents; English formal docs/UI; MIT LICENSE/NOTICE | Portrait excluded from package pending provenance; no remote action authorized |

## Original implementation-plan acceptance clauses

| Step | Assessment against its original clauses |
|---|---|
| 1 | Local syntax/startup, dependencies, empty selection, honest HTTP names, disabled unsafe paths, defaults and tests verified. CI definition exists; remote execution unverified. |
| 2 | Shared schema and special-address/rebinding/redirect/port-policy negative tests passed. No arbitrary command fields. |
| 3 | Shared adapters and local protocol/deadline/TLS evidence verified. Streamlit now has an opt-in API adapter that consumes the same worker/core and Measurement contract; legacy direct stubs remain disabled. |
| 4 | Authenticated durable jobs, tenant keys, migrations, bounded lease/retry/idempotency and PostgreSQL backup/restore verified. **Unverified:** Docker Compose runtime. |
| 5 | V2 submission/history/detail, generated diagnostic OpenAPI client, empty states and targeted keyboard/reflow verified. Broader accessibility coverage remains incomplete; legacy direct tools remain disabled; opt-in V2 diagnostics is available. |
| 6 | Independent scheduler, deduplication, missing-data semantics, thresholds/history and retention verified. No full ledger of every missed interval. |
| 7 | Windows outbound Agent lifecycle, local ceiling, schema rejection and bounded spool verified; source-only package/install verification recorded. Linux deferred; signed installer not implemented. |
| 8 | Bounded system probes and Windows fixtures/runtime verified. Linux and broader privilege/locale conditions unverified. |
| 9 | Persistent group membership and conservative compatibility verified; resolver/IP differences have recorded evidence, unknown cache equivalence disclosed. |
| 10 | Deterministic reports, retained references, scoped validated AI and outage paths verified within stated cases. Broad model-quality assessment unverified. |
| 11 | Local saturation budget, security regressions, runbooks and MIT selected. **Incomplete for public release:** ingress-wide abuse controls, egress enforcement, sustained load/SLO decisions and distribution hardening. |

## Outstanding work without expanding claims

1. The shared-core Streamlit migration clause is now implemented through an opt-in
   authenticated API adapter, with AppTest/API/worker/SQLite lifecycle verification.
   It is not full UI parity with Next.js and does not restore unrestricted tools.
2. Focused UI creation checks now include enrollment-token issuance/hiding,
   diagnostic queue-to-result and monitor creation. Broader accessibility remains
   an explicit validation limit, not a claimed certification.
3. Preserve Windows-first scope. Linux/Compose, cross-machine environments and
   public-hosting controls must not be inferred from the local checks.
4. Keep model quality, automatic archival, identity-provider roles and signed
   distribution clearly separated from the implemented local product. Any decision
   to make them release requirements needs concrete implementation/validation.

No status in this matrix substitutes for measurement evidence or owner authorization.


## Local delivery conclusion

The owner-scoped Windows local product objective is accepted: all seven core
capability groups above have implementations and concrete local verification,
shared security/measurement invariants are tested, the five design artifacts and
collaboration rules exist, and the r3 source package contains the runtime sources,
locks and loopback configuration. The source package installation/build/start was
verified at its earlier checkpoint; subsequent runtime changes have their targeted
API/worker/AppTest/browser evidence recorded separately. Package manifests match
their source snapshots. No remote publication, PR or deployment was performed.

This conclusion does not close every proposed public-release gate. Linux was
explicitly deferred; Compose/remote CI/cross-machine deployment, broad model-quality
or accessibility certification, ingress-wide isolation/abuse operations, automated
archival, roles/identity-provider integration and signed installation remain the
stated limitations or future design items. No throughput, availability, complete
crash coverage, physical topology or causal diagnosis guarantee is made. The
Windows product is delivered as configurable local software, not an operated cloud
service. Use README.md and packaging/README.md for setup; configure only targets
that the operator is authorized to diagnose.
