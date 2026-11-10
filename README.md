# NetGuardian V2

**Network diagnostics and monitoring for approved targets.** Run a probe, compare
results from two network locations, and review the evidence behind an incident.

[Get started](#local-development-setup) · [Windows launcher](#windows-local-launcher) · [System design](docs/architecture/SYSTEM_DESIGN.md) · [Delivery status](docs/product/DELIVERY_STATUS.md)

## What you can do

- **Diagnose connectivity** with DNS, TCP, TLS and HTTP HEAD probes. View individual
  timing measurements and TLS certificate details. Enable bounded ICMP and
  traceroute checks when needed.
- **Monitor over time** with scheduled checks, collection freshness, and incident
  and recovery history.
- **Compare network locations** by pairing a server-side check with a check from an
  outbound-only Windows Agent that enforces its own target policy.
- **Review incident evidence** in redacted reports with checksums. Optional Ollama
  investigations cite recorded evidence and can be reopened alongside the report.

## How it fits together

| Component | Role |
| --- | --- |
| [Next.js dashboard](web/) | Submit diagnostics and review monitoring, comparisons and reports. |
| [FastAPI service and worker](service/) | Authorize requests, schedule and run server-side jobs, and store results with SQLAlchemy. |
| [Probe engine](probe_core/) | Validate targets and collect protocol-specific measurements. |
| [Windows Agent](agent/) | Run approved checks from a local network location and return results over an outbound connection. |

V2 is currently scoped to local Windows evaluation. See the
[Windows delivery record](docs/product/WINDOWS_DELIVERY.md) for verified scenarios
and the [delivery checklist](docs/product/DELIVERY_STATUS.md) for remaining
production and Linux deployment work.

## Local development setup

Prerequisites: Python 3.11, uv 0.13.7, Node.js 24 or later, pnpm 11.25.0.
The lockfiles are `uv.lock` and `web/pnpm-lock.yaml`.

```sh
git clone https://github.com/TYF009/NetGuardian.git
cd NetGuardian
python -m pip install uv==0.13.7
uv sync --locked
```

Configure the following environment in the API, worker and migration shells:

| Variable | Meaning |
|---|---|
| `NETGUARDIAN_TOKENS` | JSON object mapping random ASCII bearer tokens (32–512 characters) to workspace IDs; required by API/worker |
| `NETGUARDIAN_ORIGINS` | JSON object mapping workspace IDs to exact approved HTTP(S) origins; defaults to no targets |
| `NETGUARDIAN_DATABASE_URL` | SQLAlchemy URL; defaults to `sqlite:///netguardian.db` for local development |
| `NETGUARDIAN_VANTAGE_ID` | Required by the worker: stable non-nil UUID identifying its network location |
| `NETGUARDIAN_ENABLE_SYSTEM_PROBES` | Set to `true` on the worker/agent to enable fixed ICMP/traceroute tools |

Generate a token locally with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Keep it out of source control and shell history. A token mapping has the shape
`{"<generated-token>":"local"}`. An origin mapping has the shape
`{"local":["https://<authorized-host>:443"]}`. These are placeholders, not usable
credentials or authorization to probe third-party services. Start with `{}` origins
until you have approved a target you own or are authorized to diagnose.
Configuration files named `.env` are **not loaded automatically** by the Python CLI.

From the repository root, migrate before starting either service:

```sh
uv run --locked alembic upgrade head
uv run --locked uvicorn service.api:app_factory --factory --host 127.0.0.1 --port 8000
```

Generate a probe-location UUID once with `python -c "import uuid; print(uuid.uuid4())"`
and set `NETGUARDIAN_VANTAGE_ID` in the worker environment. Preserve it across restarts.
Workers sharing one network location may share it; distinct locations must use distinct
IDs. This is an operator assertion, not automatic location attestation. Old records
retain the legacy shared ID and cannot distinguish historical worker deployments.

In another shell with the same configuration and repository working directory:

```sh
uv run --locked python -m service.worker
```

In a third shell:

```sh
cd web
pnpm install --frozen-lockfile
pnpm dev
```

Open [the local interface](http://127.0.0.1:3000) and enter the workspace token.
The Web proxy uses `http://127.0.0.1:8000` by default. Override `NETGUARDIAN_API_URL`
only with a trusted API origin. Browser users cannot select the proxy destination.
The API buffers at most 64 KiB per request before JSON parsing, with a 10-second
body-receive deadline (including chunked uploads). This does not replace deployment
connection limits or general request throttling.
Tokens stay in React memory; disconnect remounts the workspace and cancels requests.
A browser abort does not roll back an operation already committed by the API.

For a local production build, run `pnpm build` then `pnpm start` inside `web/`.
Keep the development services on loopback. Non-loopback operation needs verified
TLS and the unfinished production controls listed in the delivery checklist.

## Windows local launcher

After installing the locked Python dependencies, installing Web dependencies and
running `pnpm build` in `web/`, configure the environment variables described above
(including a stable vantage ID). From the repository root:

```powershell
uv run --locked python -m scripts.run_windows --migrate
```

`--migrate` explicitly upgrades the configured database before startup; back up an
existing database first. Omit it on later starts. The launcher requires an existing
production Web build and starts API, worker and Web on fixed loopback ports 8000
and 3000. It refuses occupied ports, missing configuration or outdated schemas.
It does not install dependencies, generate credentials, approve targets, start an
Agent or configure Ollama. Browser access still requires your workspace token.
The worker uses the configured target policy; use empty origins for a no-probe trial.

`--check` validates prerequisites without starting services or migrating. For a
bounded smoke run, use `--run-seconds 5`; the timer starts after API and Web are ready.
The worker process is supervised, but this is not a worker health/throughput check.
Ctrl+C or a child-process exit stops the process trees created by this launcher.
Shutdown is forced: in-flight work relies on existing leases and retry rules.
The launcher joins an unnamed Windows Job Object before spawning children; its
termination also terminates owned descendants, including after force-kill. It
refuses startup if the host prevents this containment. This is not a Windows
Service manager or a signed installer.

Per-run logs remain under ignored `.netguardian-local/`; review and protect them as
local operational data. Credentials are not printed or written by the launcher;
the Web child does not inherit NetGuardian backend configuration or credentials.
Rebuild Web after source changes. This launcher has been smoke-tested on Windows;
it does not change the deferred Linux support scope.

## Target policy and measurement semantics

Cloud policy defaults to deny. Only administrator-configured exact origins are
accepted; mixed public/private DNS answers, special addresses, credentials in URLs,
ambiguous hosts and unsupported schemes are rejected. Connections use validated
numeric addresses while retaining the original hostname for Host/SNI and certificate
verification. HTTP uses HEAD, downloads no body, caps headers at 16 KiB and does not
follow redirects. Ambient proxies are not used. The overall probe deadline is at most
10 seconds; only the first approved address is attempted.

| Measurement | Meaning |
|---|---|
| `dns_lookup_ms` | Resolution and address-policy planning duration |
| `tcp_connect_ms` | TCP connection establishment duration |
| `tls_handshake_ms` | TLS stream setup/handshake duration |
| `http_ttfb_ms` | Time from sending HEAD until the first response byte |
| `http_total_ms` | Total probe time through complete HTTP response headers, including setup |
| `icmp_rtt_ms` | Exact ICMP echo RTT when the OS reports one; less-than bounds remain separate samples |

HTTP duration is not ICMP RTT. A cloud result describes the worker's network, not the
browser's. TLS evidence does not prove service ownership or certificate revocation
checking. Agent observations are self-reported.

System probes use canonical numeric addresses and fixed executable/argument lists,
never arbitrary shell commands. ICMP sends one echo; traceroute uses at most 15 hops.
The process runner caps execution at nine seconds and output at 64 KiB. Missing tools
or recognized permission failures are explicit. No automatic privilege elevation is
performed. Locale variations can cause parse failures. Production cloud policy still
rejects loopback; integration tests use an isolated test-only policy.

## Monitoring and comparisons

Create a monitor with an approved target, probe kind and cloud/agent vantage.
Intervals are at least 60 seconds. Schedules run independently of browser sessions;
at most one unfinished run exists per monitor. Each workspace currently permits
20 monitors, 20 pending jobs and 60 newly created jobs per rolling 60 seconds.
Manual submissions, diagnostic pairs and schedules share the rate budget, including
completed jobs. Pairs consume two slots. API rejection returns 429/Retry-After; schedules
wait without a catch-up burst. This is not a complete HTTP request-rate limiter.

Pause prevents new scheduled jobs; queued/running jobs may finish. Resume rechecks
authorization, resets consecutive counters and starts a current cycle without replaying
missed intervals. HTTP 4xx/5xx is unhealthy; policy denial and unsupported capability
are not network outages. Missing results break consecutive counters without recovering
open incidents. Collection freshness is distinct from target health.

New incidents include the failures that triggered their threshold and subsequent
observations through recovery. Missing measurements are listed explicitly. Links retain
at most the latest 1000 observations; older incidents are not automatically backfilled.

Compare can queue matching cloud/agent jobs atomically, consuming two pending slots.
Execution is asynchronous. Numeric deltas require compatible target, kind, configuration,
probe version and destination, distinct vantages, successful observations and at most
30 seconds of skew. DNS results record A/AAAA addresses, observed TTL, canonical name and resolver endpoint.
DNS timing deltas remain withheld for every probe kind: an endpoint does not
establish equivalent cache state. Other comparable timings include an explicit
reminder that HTTP total duration includes resolution and connection setup.
IP literal targets skip DNS and leave `dns_lookup_ms` absent.
Differences do not establish causality.

Monitor **View history** retrieves the latest 100 runs in chronological order via
`GET /api/monitors/{id}/runs`. Choose one timing metric for a scatter plot and an
accessible evidence table. Missing timings are not zero and points are not joined
across gaps. The time axis is server job creation time, not claimed agent observation
time. History is an explicit snapshot; reopen it to refresh. Timing alone does not
establish target health. The initial chart uses a small SVG component rather than a
charting dependency; richer zoom/aggregation is still future work.

## Optional local agent

Copy `agent/config.example.json` to an ignored local configuration and set its HTTPS
control API origin. Explicitly list allowed probe origins. Private addresses require
explicit RFC1918/IPv6 ULA `private_cidrs`; loopback, link-local and metadata addresses
remain prohibited. Server jobs cannot expand local policy. The server policy must also
authorize the origin.

Issue a ten-minute single-use enrollment token from Agents, then run:

```sh
uv run --locked python -m agent.client --config agent/config.local.json --enroll
uv run --locked python -m agent.client --config agent/config.local.json
```

Enter the enrollment token at the hidden prompt. The agent credential is stored in
Windows Credential Manager or Linux Secret Service/KWallet, not the JSON file. The
agent fails closed without a supported store, uses outbound verified HTTPS, and opens
no listener. Revocation stops access, pauses its monitors and terminates pending jobs
without fabricating results. Uploads must match the job, attempt, configuration digest
and lease; identical duplicate uploads are accepted.

Control responses have a 64 KiB limit and 20-second total deadline; compressed or
malformed responses are rejected. One result is retried in memory, or in an opt-in bounded local spool; see the runbook.
Credential rotation is available through `--rotate-credential`; see the runbook.
Signed distribution and service installers remain unfinished.
Without a configured spool, restarting the agent can lose its pending result. Do not claim offline durability.

## Reports, AI and audit

The Reports view reopens the latest 100 saved snapshots without regenerating them.
Readable reports show incident times, recorded findings with in-page evidence citations,
missing observations, limitations and per-observation timings. Raw JSON remains available
for inspection and download.
Reports store redacted snapshots with SHA-256 checksums. Query strings and free-form
errors are removed; paths and addresses remain operational data to review before sharing.
Reads and AI submission recompute the checksum; mismatch returns HTTP 409. The checksum
is not a signature or protection against changing both content and digest.

Optional AI requires administrator-set `NETGUARDIAN_OLLAMA_URL` and
`NETGUARDIAN_OLLAMA_MODEL`. Remote endpoints require HTTPS; loopback HTTP is allowed.
No model is downloaded automatically. The adapter uses Ollama
[structured output](https://docs.ollama.com/capabilities/structured-outputs) via
[chat](https://docs.ollama.com/api/chat), with a 30-second deadline and 64 KiB response cap.
Only the latest 30 selected evidence records are submitted, excluding URLs, IPs and
endpoint free text. Facts must match recorded values; hypotheses require citations and
remain unverified. Model tools are prohibited. Missing/rejected model output remains
explicit; deterministic reports still work. Real inference quality is not yet evaluated.

Investigations reopens saved output and source reports without calling the model again.
Audit shows the latest 100 covered operator events. Logs identify roles, not individual
humans, and are not tamper-proof. See the [runbook](docs/operations/RUNBOOK.md) for scope.

## Checks and operations

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m compileall -q app.py diagnostics.py probe_core service agent migrations tests integration
uv run --locked pytest -q
uv run --locked pytest integration/test_tls.py integration/test_process_cleanup.py -q
```

The default unit suite blocks network and process execution. Integration tests are
separate: TLS uses loopback fixtures; process tests launch fixed local Python fixtures.
Windows system-tool tests require `NETGUARDIAN_TEST_SYSTEM_PROBES=true`.
PostgreSQL tests require a disposable `netguardian_test` database and
`NETGUARDIAN_TEST_POSTGRES_URL`; absent configuration produces skips, not verification.
GitHub Actions runs Python checks on Windows and Ubuntu, Web checks on Ubuntu, and PostgreSQL integration tests. See the [CI workflow](.github/workflows/ci.yml) for the test matrix.

Back up existing databases before migration. Do not blindly stamp schemas from old
unversioned development snapshots. Docker Compose configuration is provided but remains
unverified locally. See the [operations runbook](docs/operations/RUNBOOK.md).

## Legacy Streamlit and project documents

The repaired legacy UI remains available with
`uv run --locked streamlit run app.py --server.address 127.0.0.1`.
Its probe entry points are intentionally disabled; use the V2 API/Web path for approved
probes. Streamlit keeps default CORS/XSRF protections. Historical HTTP timing must never
be relabeled as ICMP or component timings.

- [Product requirements](docs/product/PRD.md)
- [System design](docs/architecture/SYSTEM_DESIGN.md)
- [Data model](docs/architecture/DATA_MODEL.md)
- [Threat model](docs/security/THREAT_MODEL.md)
- [Implementation plan and original audit](docs/product/IMPLEMENTATION_PLAN.md)
- [Current delivery gates](docs/product/DELIVERY_STATUS.md)
- [Browser QA scope](docs/product/BROWSER_QA.md)

See [NOTICE.md](NOTICE.md) for licensing scope and the legacy asset redistribution review.

The Web API proxy bounds POST/PATCH bodies to 8 KiB of raw UTF-8 bytes and a
10-second read deadline, including chunked requests. Encoded/compressed bodies
are rejected. Run its focused regression checks with `cd web` and `pnpm test`.

Agent jobs have a 120-second delivery window from creation. The scheduler (or an
agent poll) marks overdue unclaimed work and exhausted retries as failed without
a measurement, records an audit event, and releases monitor queue capacity.
A live 30-second lease is allowed to finish. Missing delivery breaks consecutive
incident evidence; it never establishes target failure or recovery.


The opt-in local transport integration suite includes
`uv run --locked pytest integration/test_agent_workflow.py -q`. It starts an ephemeral
loopback HTTPS API and HTTP HEAD fixture, enrolls an agent, executes two real probes
(503 then 204), reloads a pending upload from disk, verifies duplicate acceptance,
and checks incident recovery and report evidence. It also executes an atomic cloud/agent
diagnostic pair through both real transports and compares their recorded measurements. Test-only DNS mapping, loopback
address authorization and a private test CA are scoped to the test; production
policies and system certificate trust are unchanged. This is not evidence of a
cross-machine agent installation, all crash boundaries, Linux keyring behavior
or PostgreSQL operation. No public target is contacted.

Probe version 0.2.1 measures durations with Python `perf_counter`, a high-resolution
monotonic clock. This avoids the coarse Windows Python 3.11 `monotonic` timer.
Historical measurements are preserved; different probe versions are not compared.

Diagnostic pairs now have persistent IDs and a workspace-scoped history in the
Compare page. Reloading the page does not lose pair membership. Existing jobs are
not retroactively grouped. Generic retention preserves paired evidence; automated
pair expiration is not yet implemented. Apply database migrations before startup.

TLS certificate/hostname validation failures use `tls_verification_failed`, distinct
from generic transport errors. When available, `error.tls_verify_code` preserves the
TLS runtime verification code; its interpretation is runtime-specific. Failed
verification does not yield verified TLS certificate metadata or an HTTP status.

Control API admission is process-local: 32 concurrent API requests, a 120-request
burst replenished at 60/second, plus a 60-mutation workspace burst replenished at
1/second. Agent poll/result traffic uses only the global budget. Health endpoints
remain accessible. These are protective defaults, not benchmarked capacity or
aggregate limits across replicas; 429 responses carry `Retry-After`.


Windows PostgreSQL 17.11 has now passed local schema, concurrent-worker,
concurrent-startup and tenant-constraint tests, plus the real HTTPS Agent/report/
comparison workflow. A local dump/restore comparison matched all 12 public tables.
See `docs/operations/RUNBOOK.md` for exact scope and limitations; Docker and Linux
execution are not inferred from these results. The HTTPS integration test now runs
on SQLite and, when the explicitly named disposable PostgreSQL database is configured,
on PostgreSQL as well; otherwise its PostgreSQL case is skipped.


Setting `NETGUARDIAN_TEST_KEYRING=true` also opts the HTTPS workflow into a real OS
credential-store rotation check. It creates a randomly named test service, commits
a server credential rotation while retaining the old local credential and pending
rotation entry, then runs normal recovery. It verifies old-token rejection,
new-token access, revocation, and cleanup of both temporary credential entries.
This passed with Windows Credential Manager. It reproduces lost-acknowledgement
state; it does not inject an actual dropped socket or terminate an agent process.

The model adapter requests identity encoding and rejects compressed responses
before consuming their bodies. Its 64 KiB response cap applies to raw streamed
bytes before JSON decoding. Model transport tests do not establish model quality.


The Agent CLI holds an OS file lock for its control origin and agent ID before
opening the keyring or processing jobs. Duplicate instances fail instead of racing
spool writes or credential rotation. Lock files live under `~/.netguardian/locks`;
they remain after exit, but ownership is released by the OS when the process dies.
Do not delete lock files while an agent is running. This coordinates processes
under the same OS user; separate users/machines must not share one enrollment.


### Long incident history

Run `uv run alembic upgrade head` before starting this version. Incident links are
now stored independently of the latest-1000 summary. Authenticated control API
clients can read `/api/incidents/{id}/evidence?after=0&limit=100`, following
`next_after` until it is null. Earlier links already discarded by older versions
cannot be reconstructed. Reports remain bounded snapshots. In the Incidents tab, choose **Browse retained
history** to navigate pages of 100 links and inspect individual observations. Linked jobs are protected from generic retention;
plan storage accordingly. Downgrading populated incident history is refused.


### Local Ollama GPU compatibility fallback (Windows)

The local validation machine could not load Ollama 0.40.14's CUDA runner
(`device kernel image is invalid`). CPU inference worked without driver changes.
To run a separate loopback-only CPU instance, use a PowerShell terminal:

```powershell
$env:CUDA_VISIBLE_DEVICES = "-1"
$env:OLLAMA_VULKAN = "0"
$env:OLLAMA_HOST = "127.0.0.1:11435"
& "$env:LOCALAPPDATA/Programs/Ollama/ollama.exe" serve
```

In the API terminal, configure `NETGUARDIAN_OLLAMA_URL=http://127.0.0.1:11435`
and the installed model name in `NETGUARDIAN_OLLAMA_MODEL`. These are process-local
settings; the default Ollama tray service may still use its original GPU settings.
The official [hardware guide](https://docs.ollama.com/gpu) documents these GPU
selection controls. Stop the CPU server with Ctrl+C when no longer needed.

Real-model acceptance can be explicitly enabled using an existing verified report:

```powershell
$env:NETGUARDIAN_TEST_MODEL_REPORT = "C:/path/to/exported-report.json"
$env:NETGUARDIAN_TEST_MODEL_URL = "http://127.0.0.1:11435"
$env:NETGUARDIAN_TEST_MODEL = "qwen2.5:1.5b"
uv run pytest integration/test_model_workflow.py -q
```

This opt-in test calls the real model and checks persisted investigation access.
It does not certify diagnosis quality. Qwen2.5 0.5B produced unsupported causal
hypotheses in local testing and is not recommended as the default investigator.

Qwen2.5 1.5B passed the local CPU integration check against the recorded 503/204
HTTPS workflow: both facts were correctly cited and no hypothesis was invented.
This single scenario does not establish general diagnostic reliability.

## License

Project code and documentation use the [MIT License](LICENSE). See [NOTICE.md](NOTICE.md)
for third-party components and the unresolved legacy portrait asset scope.

Current delivery target: **Windows local use**. Linux runtime support and release
validation for deployment are deferred. CI covers selected Linux test scenarios.


### Missing cloud-worker results

Cloud jobs have a 120-second delivery-age limit, separate from the probe's
10-second execution deadline. Old queued jobs and expired leases become failed
without a measurement on the next job read, submission, worker claim or scheduler
tick. Active leases are not interrupted. An offline worker therefore does not
leave observed jobs queued forever, and restarting it will not execute stale work.
Expiry is evaluated when a service handles work; no clock runs while every service
is stopped. Missing measurements do not establish target failure or recovery.
The audit action is `cloud_job.delivery_expired`; each cleanup batch is bounded.


### Diagnostic API contract

Task submission, history and details use generated OpenAPI types and an
`openapi-fetch` client. FastAPI validates their response models, including the
shared measurement envelope. After changing API schemas, run from the root:

```sh
uv run python -m scripts.export_openapi
cd web
pnpm generate:api
pnpm typecheck
```

Commit both `web/openapi.json` and `web/lib/api-schema.d.ts` with the change.
CI checks the server export and regenerated types for drift. Schema export creates
an isolated temporary database, reads no operator environment and starts no server.
Other UI workflows still have manual TypeScript response types. Web tests use
Node.js 24's native TypeScript support; no new Python production dependency is added.


### Local source archive

For a reviewed Windows source-only ZIP with a file checksum manifest, see
[packaging/README.md](packaging/README.md). This excludes dependencies, builds,
tests, test keys and local data. It is not a signed installer or a public release.


### Opt-in Streamlit V2 diagnostics

The original direct probe tools remain disabled. To use the legacy page as a thin
client of the same V2 API/shared worker, start API/worker first, then in PowerShell:

```powershell
$env:NETGUARDIAN_STREAMLIT_V2 = 'true'
$env:NETGUARDIAN_API_URL = 'http://127.0.0.1:8000'
uv run --locked streamlit run app.py --server.address 127.0.0.1
```

Connect in the V2 diagnostics section with your workspace token. Select an approved
origin and probe, queue a durable job, then select its record and inspect/refresh.
Credentials remain in that Streamlit session and Disconnect V2 clears them. Do not
share browser sessions. The administrator controls the API origin; only HTTPS or
literal-loopback HTTP is accepted. Requests have a total deadline, byte cap, no
redirects and no ambient proxies. Targets are rechecked by the existing API/worker.
This adapter supplies on-demand cloud diagnostics/history, not the full monitoring,
Agent or investigation management UI; use Next.js for those. Unset the flag to
restore the default disabled legacy interface.

Source archives r1/r2 omitted `.streamlit/config.toml`; when using either old archive,
always pass `--server.address 127.0.0.1` explicitly. The r3 source archive includes
the loopback/security configuration and this adapter. Prefer r3 or a later snapshot.
