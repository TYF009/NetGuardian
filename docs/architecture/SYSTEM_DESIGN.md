# NetGuardian V2 System Design

Status: Windows local implementation, 2026-11-06; no remote deployment.
The sections below retain the original design target. The current implementation
boundary here takes precedence over historical phase notes.

## Current implementation and deliberate differences

- Next.js UI, FastAPI control plane, SQLAlchemy/Alembic, SQLite local mode and
  PostgreSQL are implemented. A separate single-concurrency worker also ticks
  monitoring. Redis is not needed for the tested local workload.
- Cloud/Agent use the same Python request/measurement schema and executor. HTTP
  uses fresh HEAD connections, bounded headers and zero redirects/body downloads.
  DNS cache equivalence is unknown; no DNS timing delta is claimed.
- Job claims use 30-second leases and at most three attempts. Probe execution is
  bounded at 10 seconds, so no lease renewal protocol is implemented. One accepted
  result is retained per job, not a full table of all attempt outcomes. Old queued
  work expires on service activity; no timer runs while all services are stopped.
- Exact-origin policy is administrator environment configuration; jobs record its
  version/hash. There is no durable full policy-revision snapshot/admin editor.
  Rechecking current policy can deny formerly authorized jobs.
- Browser authentication uses a workspace bearer token in memory, not cookie
  sessions, user accounts or a managed identity provider. Agent credentials use
  OS-backed storage and per-agent server hashes. Enrollment tokens expire; normal
  Agent credentials require explicit rotation/revocation, not automatic expiry.
- Agent spool saves one pending measurement. Post-save process termination and
  restart/upload passed real HTTPS verification. Receipt time is stamped by server-side ingestion on first persistence; the
  Agent cannot supply it. Old records remain unknown. Clock differences mean
  observed-to-received duration must not be reported as network latency.
- Diagnostics use generated OpenAPI request/response types; other UI operations
  retain manual types. Monitoring uses accessible SVG plus a table, avoiding a
  chart dependency for the current small history view. ECharts/React Flow remain
  recommendations, not claims of installed features.
- Streamlit defaults to disabled direct legacy tools. An explicit opt-in V2 adapter
  submits authenticated durable jobs and reads shared Measurement results from the
  same API/worker as Next.js. It never executes legacy target/network functions.
  Full monitoring/Agent/investigation management remains in the Next.js UI.
- The Windows launcher, unsigned source bundle and local backup/restore workflow
  are verified. Linux/Compose runtime and signed installers are deferred/unverified.
  OS egress firewall isolation and public-hosting operations are not provisioned.

These differences are explicit implementation limits, not evidence that every
original release-hardening criterion is met. See WINDOWS_DELIVERY.md and
VERIFICATION.md under docs/product for actual runs.

## Components and boundaries
Browser → Next.js/TypeScript UI → FastAPI control API → PostgreSQL.
Scheduler → durable job records → isolated cloud worker → approved destinations.
Windows/Linux agent → outbound HTTPS enrollment, job polling and result submission → control API.
Investigation service → redacted retained evidence → optional model provider.

Use a modular monolith for the API with Pydantic contracts and SQLAlchemy persistence. Share a versioned Python probe-core package between workers and agents, independent of UI and persistence. Generate TypeScript API types from OpenAPI. ECharts serves measurement charts; defer React Flow until there is meaningful route evidence, and never imply a discovered physical topology.

## Execution flow
API authenticates principal, checks workspace ownership, validates target authorization and creates a job with an immutable configuration and policy snapshot. Worker claims a lease, rechecks current revocation/policy, resolves and validates destinations, executes within a total deadline and persists structured results. API returns a job ID immediately; UI polls initially. Authorization is checked again on reads and exports.

Start with a separate worker process and PostgreSQL-backed leases, not long-running API request handlers. Claim jobs transactionally, renew leases, bound retries and reclaim expired leases. Delivery is at least once; unique result keys and attempt records provide deduplication. Probe execution itself cannot be guaranteed exactly once after a crash. Scheduled occurrences have unique `(monitor_id, scheduled_at)` keys and explicit missed-run state; avoid catch-up storms. Add Redis and a queue only when measured contention or throughput warrants the operational cost; PostgreSQL remains authoritative.

## Probe contract
Inputs specify kind, canonical target, port, resolver profile, timeouts, limits and policy version, never command strings. Outputs follow [data model](DATA_MODEL.md). Use monotonic clocks for durations and UTC for correlation. DNS timing describes the selected resolver operation, including declared cache behavior. TCP excludes DNS; TLS excludes TCP; HTTP explicitly records fresh versus reused connections, redirect timings, TTFB boundary and total timing. Preserve null for unavailable measurements.

DNS must not be resolved a second time by an uncontrolled HTTP client: validate all returned IPv4/IPv6 addresses and connect to an approved pinned address while retaining hostname for Host/SNI and certificate verification. Validate every redirect as a new target, with a strict hop budget. Disable ambient proxy configuration unless an administrator explicitly configures an equally constrained proxy. Enforce egress firewall rules as a second layer.

## Agent protocol
Administrator issues a short-lived, single-use enrollment token bound to workspace and expected agent. Store token hashes; exchange it for a per-agent scoped credential over verified HTTPS. Store credentials using OS-protected storage, rotate and revoke them, and never log them. Agent polls for expiring jobs with bounded backoff/jitter, validates typed schema, capability and locally approved policy, and submits idempotent results. No inbound connectivity is required. Revoked agents cannot fetch jobs or submit results. Offline spool is bounded and records original observation and upload times; expired jobs do not execute after reconnect. Credential/session expiry bounds the delay of revocation during disconnection.

ICMP and traceroute use fixed argument arrays or restricted native libraries, never a shell. Keep the service unprivileged; any privileged helper exposes only bounded probe operations and is isolated from the API. OS and locale differences require fixtures and real supported-platform checks.

## Monitoring, incidents and AI
Monitor rules operate on comparable metrics and explicit success/error states. Configure consecutive-failure opening and consecutive-success recovery thresholds; late or missing samples have separate handling. Store state transitions transactionally. Comparative jobs share a group ID and configuration hash, but disclose time skew, resolved addresses, resolver and vantage differences. Do not infer causality from a latency difference alone.

AI is optional and read-only. Retrieve evidence by workspace, construct a bounded redacted context, and require structured claims with existing evidence IDs. Treat endpoint text as untrusted data. Validate citations and mark insufficiency; citation presence alone does not prove a causal claim. Retain model/prompt version, source snapshot and output for review. Model failures must leave deterministic diagnostics usable.

## Deployment and operations
Docker Compose should provide UI, API, worker and PostgreSQL; keep database private and probe workers on restricted egress. Add health/readiness checks, migrations as a controlled deployment step, secret injection and tested backup restoration. GitHub Actions should run syntax/type checks, unit/contract tests, migration tests, policy tests and dependency review with least-privilege tokens. Record job queue age, execution errors, policy denials and agent freshness without sensitive URLs. Start with bounded concurrency and tune using measured workload.

## Migration and trade-offs
Keep Streamlit as a temporary adapter to probe-core after safety repairs. Introduce the API and durable results behind a feature flag, then a thin Next.js diagnostics page, then monitoring, agent, comparison and AI. Avoid two independent probe implementations. There is no persisted legacy database to migrate; session CSVs lack metric semantics and vantage, so any later import must mark them legacy/unverified and exclude them from typed comparisons. Preserve rollback to the last safe deployment; never roll back security controls. Use additive database migrations and postpone destructive schema cleanup until rollback windows close.

Python sharing reduces measurement drift but creates an agent packaging/update burden. PostgreSQL leases reduce infrastructure count but need careful concurrency tests. Managed authentication reduces security implementation work but adds a dependency; provider choice is unresolved. Version numbers and performance claims must be selected and tested during implementation.

## Historical phase 1 boundary

The retained Streamlit interface currently calls disabled legacy adapters only.
No worker, API, database or shared V2 probe-core has been introduced. Re-enabling even
fixed-host HTTP monitoring requires connection-time target enforcement first.


### Scheduler/retention lock ordering

Result processing commits before scheduler admission acquires workspace locks.
Within the result phase, monitor runs are ordered by monitor ID. Retention takes
workspace locks before sorted monitor locks; holding result-phase monitor locks
while later requesting a workspace lock would create a deadlock cycle. Splitting
these phases allows a crash between result application and scheduling; the next
tick resumes scheduling, and processed flags prevent duplicate incident updates.
This trades one atomic tick for bounded, recoverable phases without losing results.
A PostgreSQL concurrency test deliberately overlaps the monitor and workspace
locks and verifies both transactions finish with the evidence link retained.
