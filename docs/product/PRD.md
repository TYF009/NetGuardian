# NetGuardian V2 Product Requirements

Status: Windows local implementation and acceptance in progress, 2026-11-06.
The baseline audit below is historical; current evidence is in DELIVERY_STATUS.md.

## Purpose and users
Help operators, developers and small infrastructure teams determine which network layer failed, from which vantage point, and with what evidence. Engineering utility takes priority over appearance. Support self-hosting first; a hosted public service requires additional abuse operations and capacity decisions.

## Historical baseline (before implementation)
Reviewed every tracked file at commit `b0ce286802db07d02a912de2bcc577de3f2a6deb`: `app.py`, `README.md`, `.devcontainer/devcontainer.json`, and `Felix.jpg` (visually inspected portrait asset). No tests, dependency manifest, database, agent, AI integration, CI or license file exist. See [implementation plan](IMPLEMENTATION_PLAN.md) for the audit. Public repository visibility does not resolve the license choice; the owner must select a license before an open-source release.

## Product scope
1. Controlled cloud probes: authenticated users select approved targets and DNS, TCP, TLS or HTTP tests; receive durable typed results and explicit vantage information.
2. Optional Windows/Linux agent: operator enrolls a machine, approves its local target policy, and runs bounded typed probes over outbound HTTPS. No inbound listener or remote shell.
3. Monitoring: schedules survive browser closure, retain results and incident transitions, and distinguish failed measurements from missing telemetry.
4. Comparison: pair cloud and agent results for the same logical target and configuration within a stated time window; show resolver and resolved-IP differences rather than hiding them.
5. Investigation: deterministic evidence views first, optional AI hypotheses later. Every factual AI claim cites recorded measurements; unsupported causes remain hypotheses.
6. Reports: export incident timeline, measurements, vantage, configuration, limitations, and evidence references. Exclude credentials and response bodies by default.
7. ICMP/traceroute: capability-gated additions with explicit permission errors, bounded packets/hops and platform adapters. A missing response is not proof of an outage.

## Required behavior
Expose DNS lookup duration, TCP connect duration, TLS handshake duration, HTTP time to first byte and total duration, and ICMP round-trip time as distinct measurements. Never label HTTP timing as ping. Show UTC timestamps, units, error categories, collection location, probe version and freshness. A cloud probe describes the cloud host's path, not the browser user's network.

Targets require administrator authorization, allowed protocols/ports and quotas. Hosted cloud execution must reject private/special destinations and unauthorized public scanning. Local private targets require explicit operator opt-in, bounded CIDRs and ports; cloud policy cannot silently expand agent policy.

## Success and release gates
- Each diagnostic produces a persisted result or explicit terminal failure within its configured deadline.
- Forbidden destinations cause zero network connections in adversarial policy tests.
- Browser closure does not stop scheduled checks; duplicate delivery does not duplicate results.
- Cross-tenant access is denied for targets, jobs, agents, incidents and exports.
- Every report claim links to retained evidence or is labeled an unverified hypothesis.
- Windows and Linux contract fixtures pass before agent release.

Proposed initial limits: 10-second job deadline, 1 MiB HTTP body ceiling, 3 redirects, 15 traceroute hops, minimum 60-second monitor interval, 30-day raw-result retention. These are design defaults to validate through load and usability tests, not measured capacity promises. Initial deployment sizing and availability SLO remain undecided.

## Non-goals
Arbitrary commands, exploit checks, port-range scanning, packet capture, automated remediation, unrestricted crawling, and AI-generated executable jobs. Defer multi-region orchestration and elaborate topology graphics until measurements justify them.

## Open decisions
MIT licensing and Windows-first local delivery are selected (see current scope below). A future authentication provider, retention/privacy requirements, supported OS versions, agent signing/distribution, cloud regions and hosted operating budget remain open decisions. Development can begin with policy contracts without assuming these are settled.

## Historical phase 1 status

The legacy UI is now a fail-closed safety baseline. All network execution is temporarily
disabled pending policy and safe transport adapters; no V2 architecture is deployed.


## Current delivery scope (owner decision, 2026-11-06)

Deliver and validate the Windows version first. Linux support is deferred to a
later stage; keep reusable platform adapters and Linux CI configuration, but do
not claim a Linux release or block local Windows delivery on Linux validation.
The owner selected MIT for project code/documentation; see LICENSE and NOTICE.md.
No remote publication or deployment is authorized.

The repaired Streamlit baseline remains available. The local V2 API, worker,
Web UI, Windows Agent, persisted monitoring, comparisons, evidence reports and
optional CPU Ollama investigation are implemented; consult verification records
for tested paths and remaining gaps. Historical phase notes do not describe the
current capability set. Current HTTP probes use HEAD, read bounded headers and
follow no redirects; earlier body/redirect limits were proposals, not implemented
behavior. Execution deadlines and delivery waiting are separate. Cloud work older than
120 seconds is expired on subsequent service reads/submissions/ticks, except for
active leases. Missing measurements are not target-failure evidence. No lifecycle
clock runs when every service is stopped.
