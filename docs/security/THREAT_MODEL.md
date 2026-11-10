# NetGuardian V2 Threat Model

Status: design threat baseline with implemented Windows controls and explicit residual gaps. Assets include internal network reachability, agent credentials, target configurations, measurements, incident evidence and infrastructure capacity.

## Current controls versus design requirements

The original mitigation matrix below defines the security target, not a blanket
claim that all deployment protections exist. Current source implements exact-origin
allowlisting, full-answer address policy, numeric connection pinning, verified TLS,
no redirects/proxies/shell, bounded protocol/process work, workspace-scoped bearer
access, tenant-consistent foreign keys, hashed Agent credentials, OS-keyring,
rotation/revocation, bounded spool, request/body/job quotas and evidence validation.
Actual Windows protocol, restart, database and UI checks are recorded in
../product/WINDOWS_DELIVERY.md and VERIFICATION.md.

Cookie sessions and human-role accounts are not implemented: the browser sends an
explicit in-memory bearer token. Cookie-auth CSRF requirements in the matrix apply
if that authentication design is later introduced. The current system does not
provision egress firewalls, distributed abuse limits, signed installers, automatic
credential expiry, identity-provider integration or public target ownership checks.
Agent-reported evidence is not attested. Source archive checksums are not signatures.
A process-local resource ceiling cannot prevent all denial of service. Hosted/public
release still requires the deployment controls and operational ownership below.

## Trust boundaries
Untrusted browser → authenticated API; API → database/job queue; worker → hostile network; cloud → locally administered agent; collected evidence → external model. A compromised agent may lie about its own observations and must not gain access to other agents or workspaces.

| Threat | Required mitigation | Verification |
|---|---|---|
| SSRF into metadata/internal services | Approve target names and ports; reject private, loopback, link-local, multicast, unspecified and reserved IPv4/IPv6 and mapped equivalents; validate every DNS answer and redirect; pin connection address; egress filtering | Mock DNS rebinding, mixed answers, encoded addresses, redirects and alternate address families; assert zero forbidden connections |
| Public scanning/resource exhaustion | Authentication, administrator-approved targets, per-user/workspace/global concurrency and rate limits; bounded DNS, packets, redirects, bodies, jobs and retries | Quota and load tests; cancellation/deadline enforcement |
| Shell/argument injection | Typed operations only, strict hostname/IP validation, fixed argument arrays and no shell; no user-provided executable or flags | Metacharacter/option injection fixtures and process-call assertions |
| Local agent used as pivot | Local immutable-by-cloud authorization ceiling, explicit private CIDR/port approval, no remote shell; block metadata/link-local even under broad private policy | Malicious cloud job rejected by agent; policy revocation tests |
| Enrollment theft/replay | Short expiry, single use, hashed tokens, atomic consumption, rate limit, verified TLS | Concurrent replay test, expired token and workspace mismatch tests |
| Credential compromise | Scoped per-agent credentials, OS protection, rotation/revocation, least privilege | Revoked credential denied on poll/upload; no cross-agent jobs |
| Tenant data leakage | Authorization on every object and export, tenant-consistent keys, scoped queries | Negative tests across all resource types |
| CSRF/XSS | Same-origin deployment, secure HttpOnly session cookies, CSRF protection on cookie-auth mutations, escaped text, constrained CORS | Cross-origin mutation and hostile evidence rendering tests |
| Malicious endpoint response | Total deadline, byte/decompression limits, certificate validation, bounded parsing; no ambient credentials/proxies | Slow streams, oversized compressed payloads, bad TLS and redirect-loop fixtures |
| AI prompt injection/fabrication | Evidence treated as data, read-only model, redaction, citation validation, hypothesis labels and human review | Inject instructions in endpoint text; reject unknown evidence IDs; unavailable-model fallback |
| Supply-chain or privileged worker compromise | Locked dependencies, reviewed updates, minimal containers, isolated helper, signed agent releases | CI checks, release verification, non-root execution and restricted-egress checks |

Target ownership verification alone does not prevent SSRF: an authorized hostname can change its addresses. Revalidate at execution and connection time. Prefer rejecting a hostname with any prohibited answer rather than silently selecting a safe-looking subset. HTTP redirects to a different hostname require independent target authorization. DNS probes also require bounded approved query names to avoid using the resolver as an abuse channel.

## Historical pre-repair exposure
`app.py` accepts arbitrary targets for `check_http_status` and `check_port`, without authentication or policy. HTTP GET follows redirects and reads the response without an application-level body cap. `run_traceroute` interpolates a host into `shell=True`; the current UI supplies fixed dictionary targets, so direct user-controlled command injection is not established, but future reuse is hazardous. IP geolocation uses plaintext HTTP and incomplete private-address classification. The devcontainer explicitly disables CORS and XSRF protection. The syntax error currently prevents normal startup; it does not make these paths safe once repaired.

## Residual risks and release blockers
Cloud probes cannot establish the user's local path; agent compromise cannot be solved by result signing alone. Geolocation is approximate and must remain optional; disable legacy third-party enrichment until privacy and HTTPS support are reviewed. Internet probes can trigger target defenses even within quotas. Hosted launch requires abuse response ownership, target authorization policy, tested egress isolation and capacity limits. Secret storage, identity provider and signed update mechanism remain implementation decisions. No exploit or live scan was performed for this review.

## Historical phase 1 containment

The historical exposure section describes the pre-repair revision. The current
safety baseline disables every probe and third-party enrichment entry point before
any network or subprocess operation. This is temporary containment, not an implemented
SSRF policy or authorization system. Do not re-enable probes based only on fixed hosts.

## Historical policy-foundation checkpoint

The pure cloud HTTP(S) origin policy rejects prohibited answers as a group and emits
numeric-address connection plans. Synthetic DNS rebinding tests verify changed answers
are rejected; they do not prove a future client avoids re-resolution. Transport integration,
egress isolation, quotas and identity-backed policy administration remain release blockers.
The public-address filter conservatively excludes transition/translation IPv6 prefixes
and selected special-purpose ranges beyond Python 3.11's built-in registry classification.
Registry updates require review; an application filter cannot replace restricted egress.


## Control API admission limits

Before reading an API request body, each API process admits at most 32 concurrent
requests and uses a token bucket of 120 requests replenished at 60/second. Mutations
also share a workspace bucket of 60 requests replenished at 1/second; multiple
administrator tokens for one workspace share that budget. Unknown credentials share
one bucket and cannot create unbounded limiter state. Agent polls/uploads use the
global budget but not the mutation bucket. Health/readiness endpoints bypass this
admission layer. Rejection returns 429 and Retry-After; Web preserves that header.

These are process-local defensive defaults, not measured capacity claims or a
cross-replica quota. Limits reset on restart; load-balanced replicas multiply them.
A hostile caller can still deny service by consuming the shared global budget.
A production reverse proxy must enforce connection/header limits and aggregate
abuse controls. The database-backed job budget remains independently enforced.
