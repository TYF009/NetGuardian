# Local verification record

Date: 2026-11-06. Scope: local working tree, Windows, Python 3.11.2,
Next.js 16.4.4. No remote CI, deployment, push or remote PR is represented here.

## Consolidated regression

| Command | Observed result |
|---|---|
| `.venv/Scripts/ruff check .` | Passed |
| `.venv/Scripts/ruff format --check .` | 99 files already formatted |
| `.venv/Scripts/python -m pytest tests -q --tb=short` | 153 passed; one Starlette TestClient/httpx deprecation warning |
| `node --test tests/*.test.mjs` from `web` | 6 passed |
| `node node_modules/next/dist/bin/next build` from `web` | Production compilation, TypeScript, static generation and API route build passed |

Next.js reported that the parent directory's pnpm workspace file was ignored
because it is outside this repository. The build succeeded. The Python warning is
a test-client deprecation, not a failed production startup or test.

## Additional runtime evidence

- Real Windows IPv4/IPv6 TLS trust and hostname tests passed (six cases).
- Real Windows process timeout/cancellation/output-limit cleanup passed.
- Explicit Windows loopback ping/traceroute and OS-keyring checks passed.
- HTTPS enrollment, agent HTTP measurements, spool reload/duplicate upload,
  incident recovery, reports and paired cloud/agent execution passed.
- Windows Credential Manager plus HTTPS rotation recovery from an unconfirmed
  server rotation passed; temporary entries were removed. No real crash or dropped
  connection was injected by that test.
- Portable Windows PostgreSQL 17.11 migration, concurrent worker claims,
  concurrent initialization and cross-workspace rejection passed. The same HTTPS
  workflow passed with PostgreSQL. A dump/restore matched all 12 public tables in
  row counts and canonicalized row-content digests. See the operations runbook.
- Populated monitor history and report display were inspected in the browser;
  disconnect cleared the visible records and token input. See BROWSER_QA.md.

## Limits

These observations are functional checks, not capacity measurements. They do not
establish Linux support, Docker Compose startup, remote CI results, real model
investigation quality, signed distribution, cross-machine agent setup, power-loss
recovery or comprehensive browser accessibility/responsiveness. Consult
DELIVERY_STATUS.md for the remaining release gates. Test fixtures remain explicitly
separate from user measurements. No test result is presented as a network benchmark.


The latest Python consolidation follows the incident-history migration, scheduler
lock-order correction, real-model schema changes and investigation response
unification. Prior runtime checks below remain dated checkpoints; they are not
claims that every integration test was rerun during this consolidation. The current
PostgreSQL checkpoint passed eight tests and compared 13 tables. Real Qwen2.5 1.5B
CPU API and browser findings/report-download checks passed separately; see
DELIVERY_STATUS.md and BROWSER_QA.md. Linux/Compose validation is deferred by the owner; Windows is the current delivery target.


## Consolidated Windows regression, 2026-11-06 (after local launcher)

- Python unit/regression suite: 164 passed, one upstream Starlette/httpx
  deprecation warning; no application failure.
- Ruff lint passed; format check passed for 106 Python files.
- Exported OpenAPI matches the current server.
- Web: 9 tests passed; production build and TypeScript compilation passed.
- Node reported module-type inference for the TypeScript test import; Next reported
  an ignored ancestor pnpm workspace outside this checkout. Neither failed checks.

This checkpoint follows cloud expiry, generated diagnostic contracts, Agent delivery
loop cases, Windows launcher and revoked-Agent selection correction. The Web now
also displays recorded probe/schema version, attempt, error category and optional
TLS verification code, with policy/configuration identity expandable. These values
come directly from Measurement; no inferred measurements are added. The additional
metadata display passed type checking/build; subsequent narrow-viewport browser
verification displayed the real probe version and expandable identity (BROWSER_QA.md). Existing integration results remain their dated runs; PostgreSQL,
model, system-tool and Linux checks were not rerun in this consolidation.


## Real DNS wire verification

integration/test_dns_runtime.py passed three Windows scenarios using a real local
UDP DNS responder and the production dnspython resolution/executor path. Only the
resolver endpoint is configured for the fixture; transport and DNS responses are
not mocked. A/AAAA, CNAME canonical name, answer TTL, resolver IP/port and nonzero
lookup timing are checked. NXDOMAIN produces resolution_failed. A public/private
mixed answer is rejected by the unchanged cloud target policy. The DNS-only probe
never connects to returned public addresses. Ruff passed, and CI includes this test.
The first success-case assertion compared typed IP objects with strings; the test
was corrected to compare their canonical text. No runtime change was needed.
This does not test every DNS failure mode or establish resolver-cache equivalence.


## PostgreSQL follow-up after Agent process restart tests

The isolated PostgreSQL 17.11 verifier passed 8 tests on Windows, including the
updated real HTTPS workflow with actual Agent run-loop termination and restart,
concurrent worker/tenant checks and retention/scheduler lock ordering. Dump/restore
matched counts and content digests for all 13 public tables. The disposable cluster
was stopped; no system service was installed. Artifacts: NetGuardian-pg-validation-
ycgtlgun under the local temporary directory. This was not the SQLite-only HTTP
admission saturation fixture, a sustained-load test, Linux or remote deployment.
