# NetGuardian V2 Data Model

Status: implemented SQLAlchemy model with Alembic head d91a04ef620b,
verified on Windows SQLite and PostgreSQL 17.11. The entity table below is the
original design proposal; it must not be read as an inventory of existing tables.

## Current storage mapping

`service/database.py` defines 12 application tables: workspaces, jobs, monitors,
monitor_runs, incidents, agents, enrollments, reports, investigations, audit_events,
diagnostic_pairs and incident_evidence. Alembic adds its version table. IDs are
string-backed UUIDs except configured workspace keys and other documented composite
keys. UTCDateTime enforces aware writes and normalizes reads on both backends.

- Jobs store target/kind/policy version, attempt count, lease token/deadline and one
  JSON Measurement result. Current task states are queued/running/succeeded/failed/
  cancelled; delivery expiry is represented as failed without a fabricated result.
- There are no separate attempt, measurement, target, target_policy, membership,
  role or vantage tables. Origins and operator token mappings are environment
  configuration; cloud vantage is a stable operator-configured UUID. Configuration
  hashes do not reconstruct old authorization policies.
- Measurement.received_at is stamped by the cloud worker or Agent ingestion
  handler before the first accepted persistence. The Agent-supplied value is ignored;
  duplicate identity excludes this server field and never updates its initial value.
  Historical records remain null; no backfill invents receipt times. observed_at
  remains the probe clock. Their difference includes clock skew and processing,
  not a measured network-only or upload-only delay. Successful
  schemas validate known versions rather than negotiating Agent capabilities.
- Reports and investigations store immutable JSON snapshots/validated output and
  integrity metadata. Citation links within these payloads are application-checked,
  not individual claim_evidence rows. Reports are not digital signatures.
- Incident transitions and consecutive counters live in incidents/monitors; runs
  link jobs and processed state. There is no separate incident_event table or
  scheduled-occurrence key. Admission locks plus one unfinished run prevent a
  catch-up burst; no full missed-interval ledger is claimed.
- Retained incident links and immutable diagnostic pairs have tenant-consistent
  relationships as described below. Referenced jobs are protected from retention;
  report/incident/pair archival is not an implemented automatic expiry policy.

The richer proposed model remains a roadmap. Adding its entities/fields requires
explicit migrations and acceptance tests, not a documentation-only schema claim.

## Proposed entities
| Entity | Main fields and relationships |
|---|---|
| workspace / membership | workspace ID; user identity; role viewer/operator/admin; unique workspace/user |
| target | workspace FK, canonical host, scheme, port, authorization status, policy FK; no embedded credentials |
| target_policy | workspace FK, version, allowed names/CIDRs/ports/kinds, budgets, revoked_at; immutable revisions |
| vantage | workspace FK, cloud/agent kind, label, region or agent FK |
| agent | workspace FK, identity, OS, version, capabilities, last_seen_at, revoked_at |
| enrollment_token / credential | workspace and agent binding, token hash, expiry, consumed/revoked timestamps; no plaintext secrets |
| monitor | target and vantage FKs, probe configuration, interval, next_due_at, enabled, incident thresholds |
| job | workspace, target, vantage, optional monitor/comparison FKs, schema version, config snapshot/hash, policy revision, scheduled_at, deadline, state, lease owner/expiry |
| attempt | job FK, attempt number, start/end, outcome, structured error; unique job/attempt |
| measurement | job/attempt FKs, schema version, observed/received times, probe version, metric payload, evidence hash; unique attempt/result ordinal |
| comparison | workspace FK, logical target, config hash, requested time window, allowable skew |
| incident | workspace/monitor FKs, open/recovered times, state, rule version, summary |
| incident_event | incident FK, event time/type, measurement FK, immutable transition detail |
| investigation | incident FK, model and prompt versions, input evidence snapshot, output, validation status |
| claim_evidence | investigation/claim key, measurement FK, evidence fragment path; many-to-many |
| report | workspace/incident FKs, generated time, immutable redacted evidence snapshot, content hash, retention deadline |
| audit_event | workspace, actor, action, object, timestamp, sanitized detail |

Enforce tenant-consistent foreign keys using `(workspace_id, id)` keys, not just application filters. Index measurements by workspace/target/observed time and job ID; jobs by state/next eligible time; agents by workspace/last_seen; incidents by workspace/state/opened time. Add partitions only when retention volume warrants them. JSONB supports versioned protocol detail, while frequently queried status and dimensions remain typed columns.

## Proposed measurement envelope and semantics
Required: `schema_version`, `job_id`, `attempt`, `kind`, `vantage_id`, `observed_at`, `received_at`, `probe_version`, canonical target, resolved/connected IP, configuration hash, policy version, `status`, and structured `error` or protocol result. Status is success/error/timeout/denied/unsupported/cancelled; HTTP status is a separate field, so a completed HTTP 503 remains an observed HTTP response and can fail a monitor rule.

Durations use nonnegative floating-point milliseconds, never magic sentinel numbers. Missing timing is null with a reason, not zero. Record total deadline and whether timing includes retries, redirects, cached resolution or connection reuse.

| Kind | Protocol details |
|---|---|
| DNS | query name/type, resolver identity, answer records/TTL when available, response code, lookup_ms; system resolver limitations explicit |
| TCP | selected address/family, port, connect_ms, OS error classification |
| TLS | SNI, verification outcome, negotiated version/cipher, certificate validity and fingerprint, handshake_ms; never private keys |
| HTTP | sanitized URL, method, status, bounded redirect chain, ttfb_ms, total_ms, bytes read, truncation; DNS/TCP/TLS timings only when actually instrumented |
| ICMP | sent/received counts, loss ratio, individual RTT samples and summary; capability/error reason |
| traceroute | method, max hops, ordered hops and per-attempt response/RTT, explicit missing replies, destination reached flag |

Job transitions: queued → leased → running → succeeded/failed/cancelled/expired; lease loss can create a new bounded attempt. Terminal updates require matching lease/attempt to prevent stale workers overwriting newer results. Upload deduplication uses agent/job/attempt/result ordinal and rejects conflicting payloads for the same key.

## Retention and integrity
Propose 30 days raw measurements and 90 days incidents, configurable by operator. Preserve redacted cited evidence in report snapshots until report expiry; show when underlying source expires. Deletions must not leave apparently valid citations to missing data. Hashes help detect accidental changes but do not prove an agent reported truthfully. Agent results are attributed observations, not trusted attestation. Avoid response-body storage, authorization headers and sensitive query strings. Audit exports, policy edits, enrollment and revocation.

## Compatibility
Probe-core owns Pydantic request/result schemas; API and agent use the same package and fixtures. Negotiate supported schema versions at enrollment/polling; reject unsupported major versions explicitly. Add optional fields compatibly, and use explicit migrations for semantic changes. Clock skew is recorded for comparisons; received_at cannot substitute for observed_at.

## Envelope clarification

Resolved and connected IP fields must be nullable: denied jobs, DNS failures and
unsupported operations may never resolve or connect. Record why a field is absent;
do not invent an address. Likewise a DNS-only result has no connected endpoint.


## Relational isolation implementation

Migration `b81d245fa690` adds workspace foreign keys to every tenant-owned table,
and composite `(workspace, referenced_id)` foreign keys for agent assignments,
monitor runs, incident monitors, report incidents and investigation reports.
Monitor runs now store workspace explicitly; migration backfills it from their job.
Referenced tables have unique `(workspace, id)` keys. Constraints are deferred until
transaction commit so a complete graph can be inserted atomically; deletion does
not cascade. SQLite application connections explicitly enable foreign keys.

The migration rejects orphan workspaces or inconsistent existing links before DDL.
It never deletes or reassigns historical evidence to make an upgrade pass. Incident
JSON evidence lists and immutable report JSON remain application-validated rather
than relational foreign keys; report retrieval still checks workspace ownership.
SQLite migration and direct database rejection tests exist. Windows PostgreSQL 17.11 migration, cross-tenant rejection and concurrent worker
execution have since passed; Linux and deployment verification remain separate.


## Persistent diagnostic pairs

`diagnostic_pairs` stores an immutable pair ID, workspace, cloud job ID, agent job
ID and creation timestamp. It is inserted in the same transaction as both jobs;
composite foreign keys prevent cross-tenant links. GET `/api/diagnostic-pairs`
returns the workspace's latest 100 pairs. Old pre-migration jobs are not guessed
into pairs. Retention preserves paired jobs until a pair-retention policy exists;
this is conservative and may grow storage. Pair membership never bypasses evidence
compatibility checks or imply synchronized execution.


## UTC timestamp handling

ORM timestamp writes require an explicit timezone and are normalized to UTC.
Reads return timezone-aware UTC values on both backends; SQLite's existing
application-generated offset-free values are interpreted as UTC. The column types
are unchanged, so this adapter requires no schema/data rewrite. Web timestamps
are rendered with an explicit UTC suffix. Offset-free browser input is rejected
rather than interpreted in the viewer's local timezone. Original measurement
instants and snapshot hashes remain unchanged.


## Complete incident links (revision d91a04ef620b)

`incident_evidence` stores `(incident_id, position)` as its ordered primary key,
workspace and job ID. A composite incident/workspace foreign key prevents tenant
mismatch; each incident/job pair is unique. Job IDs intentionally remain logical
references so historical missing evidence is preserved instead of discarded.
Monitoring appends links under the monitor write lock in the same transaction as
incident transitions. The existing JSON list remains a latest-1000 summary for
compatible list responses and bounded report generation. Retention protects all
normalized links, including those no longer in that summary.

The migration backfills available JSON links in order, retaining missing job IDs;
it cannot reconstruct links already discarded by older versions. Downgrade is
refused while the table contains history. GET `/api/incidents/{id}/evidence`
returns at most 100 ordered links with `after`/`next_after` positional pagination.
Reports disclose their latest-1000 scope and stored link count. The Web incident history panel uses this endpoint through a proxy that accepts
only numeric pagination parameters; each page holds at most 100 links. Incident-linked jobs grow with history and require an explicit archival
policy before deletion, rather than silent truncation.
