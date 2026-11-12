# Local operation and verification

## Compose deployment on a developer machine

Install Docker with Compose. Create an ignored `.env` containing a random alphanumeric
`POSTGRES_PASSWORD`, `NETGUARDIAN_TOKENS` (JSON token-to-workspace map), and
`NETGUARDIAN_ORIGINS` (JSON workspace-to-approved-origin-array map). Never use examples
as real credentials. Generate tokens with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Only list targets you are authorized to probe. For Compose interpolation, use an alphanumeric
PostgreSQL password or percent-encode URL-reserved characters in the connection URL.

Run `docker compose config --quiet`, then `docker compose up --build -d`.
The migration service completes before API startup; worker and web wait for API health.
Open http://127.0.0.1:3000/workspace and enter a configured workspace token. PostgreSQL has no host
port. `docker compose down` stops services while retaining the database volume.
Do not use `down -v` unless intentionally deleting all stored data.

The worker has Internet egress and database access. Application target policy protects
probe connections, but the Compose network is not a complete network-level egress firewall.
Public hosting requires an independently reviewed egress firewall, TLS gateway, operational
rate controls and secret provisioning. The UI and API are bound to host loopback by default.

## Backup and restore

For a running Compose environment, use `docker compose exec -T db pg_dump -U netguardian
-Fc netguardian` and redirect binary output using a binary-safe shell/tool. Avoid legacy
PowerShell text redirection for custom-format backups. Restore first into a separate database
with `pg_restore --no-owner --no-acl`, verify migration revision and record counts, and run
read-only API checks before switching the application. Never test restoration over the only
copy of production data. Automated restore verification remains a release gate.

## Verification status

Windows local tests currently exercise SQLite migrations, API isolation, scheduling, agent
protocol, policy and controlled transport doubles. Next.js production build and loopback HTTP
serving have passed. Docker/PostgreSQL runtime and cross-machine Agent operation have not
been verified in this environment. Container definitions are supplied for that verification;
their presence is not a claim that containers have been executed.

## PostgreSQL integration checks

Use a fresh disposable PostgreSQL database named `netguardian_test` on loopback.
Set `NETGUARDIAN_TEST_POSTGRES_URL` to its SQLAlchemy `postgresql+psycopg` URL,
then run `uv run --locked pytest integration -q`. The suite applies migrations
and inserts test jobs; it must never target a production database. It intentionally
leaves records for inspection. Use a fresh database/container for a clean run.
The default unit suite does not run these tests. Without the environment variable,
explicit integration execution reports skips, not successful database verification.

The PostgreSQL CI job uses a disposable PostgreSQL 17 service and checks schema
compatibility and concurrent worker claim uniqueness with synthetic, network-free
probe results. No remote CI run has been performed by the local development agent.

## Local TLS integration checks

Run `uv run --locked pytest integration/test_tls.py -q`. These tests create an
ephemeral loopback-only TLS listener and use the public test certificate/key under
`tests/fixtures/tls`. They exercise the real probe TCP/TLS/HTTP transport while
substituting only DNS, an explicitly loopback-only test policy, and the in-process
CA context. No production policy or system trust store is changed. Windows local
execution passed trusted-name, wrong-name and untrusted-certificate cases. Linux
execution is configured in CI but has not been observed locally.

### Windows system-tool integration

Set `NETGUARDIAN_TEST_SYSTEM_PROBES=true` and run
`uv run --locked pytest integration/test_system_local.py -q` for explicit
loopback-only ping/tracert tests. Four Windows cases passed (both tools over IPv4
and IPv6). The TLS integration suite also passed all six IPv4/IPv6 scenarios.
Testing exposed and fixed the Windows IPv6 connector's requirement for a complete
four-element address tuple. These results do not prove external reachability,
Linux capabilities, every locale, or denied-permission behavior.

### Subprocess cleanup integration

`uv run --locked pytest integration/test_process_cleanup.py -q` launches fixed,
local Python fixtures through the same bounded process runner used by system
probes. Windows execution passed all three cases: deadline expiry (9 seconds),
task cancellation and output exceeding 64 KiB. Each assertion verifies the child
has terminated and been reaped. No shell or network is used. CI includes the suite
on Windows and Linux; Linux results have not yet been observed.

## Operator audit events

Apply migrations before startup. `GET /api/audit-events` returns the latest 100
workspace-scoped events for job submission, monitor creation/pause/resume and
agent revocation, successful agent enrollment, report creation and investigation creation. Events are committed in the same transaction as the operation.
They store action, resource ID, server time and actor kind; never bearer tokens,
target URLs or endpoint response content. Current workspace tokens do not identify
individual humans: `workspace_operator` is a role, not a personal attribution.
This is an initial audit scope, not a complete security log or tamper-proof ledger;
enrollment token issuance, rejected authentication and policy changes still
need dedicated audit coverage and retention/export controls.

The Audit view displays the same workspace-scoped latest 100 events. Enrollment
redemption is attributed to `enrollment_token_holder`, not an identified human or
operator. Successful registration and generated evidence audit records contain
resource IDs only; enrollment tokens and agent credentials are excluded.

### OS credential-store integration

Explicitly set `NETGUARDIAN_TEST_KEYRING=true` and run
`uv run --locked pytest integration/test_keyring.py -q`. The test creates a random
`NetGuardian-integration-*` item, verifies the credential round trip and deletes
that same item in cleanup. It never reads existing account credentials. Windows
execution passed including the final absence check. Linux Secret Service/KWallet
integration remains unverified; unsupported/plaintext backends fail closed.

## Job retention

Preview with `uv run --locked python -m service.retention --workspace <id> --days 30`.
Only explicit `--apply` removes records. Each invocation handles at most 500 eligible
jobs. It preserves all incident-linked jobs, nonterminal/unprocessed jobs and each
monitor's latest 100 runs. Reports, investigations, incidents and audit events are
not deleted. Deletions and audit records commit together. Back up first; review the
preview and run during a maintenance window. Repeat for additional batches.
This tool is opt-in, not an automatic background retention schedule. Current validation
uses temporary SQLite data; PostgreSQL locking/retention execution is not yet verified.

## Optional Agent pending-result spool

Set `spool_path` in the agent JSON to an absolute file path in a dedicated private
local directory. Unix directories must have mode 0700; on Windows use a directory
under the agent account's LocalAppData with ACL access restricted to that account
and administrators. Do not use shared/network folders. The file contains measurement
data and a short-lived lease token, not the long-term credential; it is not encrypted.
Only one upload (up to 64 KiB) is stored, with atomic replacement and file flush.
Use one running agent instance per configuration/spool. Restart reloads the upload,
not the probe. Successful/duplicate acknowledgment or terminal 404/409/422 clears it.
Expired leases are not extended, so this is crash recovery, not offline execution.
Missing configuration retains the previous memory-only behavior. Corrupt or mismatched
files fail closed and require operator review. Power-loss directory durability and
concurrent-instance coordination are not guaranteed.

## Agent credential rotation

Stop the polling instance, then run `uv run --locked python -m agent.client --config
<path> --rotate-credential` and restart polling. A pending replacement is written to
the OS keyring before the HTTPS request. The API atomically invalidates the old hash
and records an agent-attributed audit event. If the response is lost, the next start
recovers using the pending credential; it never prints credentials or writes them
to configuration. Keep a single instance per agent during rotation. Revoked agents
cannot rotate. Real cross-machine failure recovery is not yet verified.

## Health endpoints

`GET /health` is process liveness only. `GET /ready` checks database connectivity and
the migration revision, returning 503 for unavailable/stale databases without
exposing connection details. Compose API healthchecks use `/ready`. Neither endpoint
proves worker/agent availability or target health; use collection freshness for those
observations. Database health checks remain subject to driver connection timeouts.


### Tenant constraint upgrade

Before applying migration `b81d245fa690`, stop API and worker writers and back up
with the database procedure above. SQLite rebuilds tables while installing the
constraints; do not run this upgrade against a live service. The migration checks
legacy ownership links before its first schema change. If validation fails, retain
the backup and investigate the named table; do not delete evidence or disable the
constraints to force startup. Run the normal schema upgrade command, then readiness
checks before reopening writes. SQLite legacy-data migration and fresh Windows PostgreSQL schema migration have
been exercised. PostgreSQL legacy-data upgrade/rollback and other deployment
environments still require validation; see the later runtime record below.


## Observed PostgreSQL validation (2026-11-05)

Portable EDB PostgreSQL 17.11 for Windows, linked from PostgreSQL's official Windows
page, was run without registering a service. The archive SHA-256 observed locally
was `80379b2c04d51c30225532e0ae04509899141e9957ed096fe749d7fd9df8f82f`.
This digest identifies the downloaded artifact; it is not an independent signature.
The binary could not initialize under this machine's non-ASCII repository path;
an isolated ASCII directory under the system temporary folder worked. The server
listened only on 127.0.0.1 at a randomly selected port, with SCRAM authentication
and a generated test-only password. No system database or service was changed.

The executed command was `python -m pytest integration/test_postgres.py
integration/test_agent_workflow.py -q --tb=short` with the disposable database URL
supplied in `NETGUARDIAN_TEST_POSTGRES_URL`. Six tests passed: four PostgreSQL
schema/concurrency/isolation tests, plus the real HTTPS workflow once on SQLite
and once on PostgreSQL. The latter exercised enrollment, monitored HTTP 503/204,
spool replay, incident recovery, evidence report and cloud/agent paired comparison.

A custom-format pg_dump was restored with pg_restore --exit-on-error into a second
empty database in the same temporary cluster. All 12 public tables matched in row
count and SHA-256 of canonicalized complete row content. The fixture included 16
jobs, 2 agents, 1 recovered incident, 1 report and 1 diagnostic pair. Investigations
were empty; this does not validate AI output preservation. Both databases were
then stopped with the cluster. This is local functional evidence, not a load test,
cross-version restore guarantee, Docker verification or Linux result.

Windows orchestration should redirect pg_ctl output to files rather than captured
pipes: inherited pipe handles can leave a parent waiting after the server starts.
Always check the process and server log before deciding to restart a test instance.


### Reproduce isolated PostgreSQL validation

With PostgreSQL server/client binaries already available and project dependencies
installed, run as a normal user from the repository:

```sh
uv run --locked python scripts/verify_postgres.py --bin-dir /path/to/postgresql/bin
```

On Windows, pass an ASCII path such as `C:/Tools/pgsql/bin`; the script rejects
non-ASCII binary paths because the observed initdb restricted-token launch failed
there. No software is downloaded or system service installed. The script creates a
new temporary cluster with SCRAM authentication, a generated password and loopback
listener, runs the PostgreSQL/HTTPS suite, restores a custom-format dump into a
second database and compares every public table. It stops the cluster in `finally`
and removes its initial password file. A unique temporary directory retains logs,
the stopped cluster, dump and `validation.json` for inspection. Existing clusters
are not used. Do not point other programs at this transient instance.

The repository script itself was executed on Windows PostgreSQL 17.11: six tests
passed, 12 table comparisons matched, and shutdown completed. Linux execution of
this helper remains unverified. A machine-level crash can bypass Python cleanup;
inspect the printed artifact directory and its postmaster.pid before any recovery.


### Real-model evidence validation

Export a real recorded report from the Web UI. With an explicitly approved Ollama
endpoint/model, run from the repository root:

```sh
uv run --locked python -m scripts.verify_model --report report.json --endpoint http://127.0.0.1:11434 --model YOUR_MODEL --output evaluation.json
```

The script verifies the stored report checksum before sending anything, caps input
at 4 MiB, and uses the same sanitized latest-30-observation context and bounded model
adapter as the API. URLs, paths, addresses and free-form endpoint errors are excluded.
Choose the endpoint deliberately: supplied observation fields are transmitted there.
The output must be a new file; existing reports/evaluations are never overwritten.

The artifact separates transport completion, evidence validation and diagnosis
quality. Exit 0 requires validated, nonempty recorded facts; even that does not
establish root-cause accuracy. Empty findings, rejected output and provider failures
produce a nonzero exit and an inspectable result. Hypotheses remain unverified.
This harness is implemented; no actual model result is claimed until a configured
model has been run and its output reviewed.


### Verify a downloaded report offline

```sh
uv run --locked python -m scripts.verify_report report.json
```

This command does not connect to the API, database or model. It recomputes the
canonical snapshot SHA-256, ignoring any exported claim that integrity was already
verified. Exit 0 means the snapshot matches the accompanying checksum; exit 1 means
loading or verification failed. Only the snapshot is covered, not outer export
metadata. An attacker able to replace both snapshot and hash can still forge a
matching pair: this is neither a digital signature nor proof of measurement accuracy.
The same bounded loader is used by the model evaluation tool.


### Local admission verification budget

Run `uv run --locked pytest integration/test_admission_runtime.py -q` for a bounded
real-HTTP check of the default single-process concurrency policy. It starts one
loopback server with isolated SQLite and no authorized probe targets. A test-only
held-response route occupies 32 API slots, then 8 authenticated requests must return
429 with Retry-After. Health/readiness must remain reachable. Releasing all held
requests must restore normal authenticated API access. Maximum client concurrency
is 64, individual HTTP timeout 10 seconds, and server cleanup is bounded. The held
route exists only in this integration test, never in the shipped application.

Windows execution passed on 2026-11-06. CI includes the same check; remote execution
is unverified. This is a deterministic saturation/recovery experiment, not sustained
load, throughput, memory profiling, distributed admission, or a production capacity
claim. Defaults remain 32 active API requests, a global burst of 120/refill 60 per
second, and per-workspace mutation burst 60/refill 1 per second. Database job quotas
are separate. Restart resets in-memory limits; replicas multiply available budgets.
Before public hosting, measure representative workloads and enforce ingress-wide
limits, connection budgets and monitoring outside these process-local controls.
