# NetGuardian — Hospitality IT Infrastructure Monitoring & Network Diagnostics Platform

[![Baseline checks](https://github.com/TYF009/NetGuardian/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/TYF009/NetGuardian/actions/workflows/ci.yml) [![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**English** · [简体中文](README.zh-CN.md)
[Demo quick start](#demo-quick-start) · [First diagnostic](#first-diagnostic-walkthrough) · [Full local deployment](#full-local-deployment) · [Documentation](docs/README.md)

NetGuardian is an open-source network monitoring and evidence-based troubleshooting platform developed to support hotel IT operations. I designed and built it independently using FastAPI, Next.js, a background worker, SQLite/PostgreSQL and a Windows Agent.

- **Hotel operations:** Approved for use and deployed in IT operations at Hengze Hotel.
- **Portfolio demo:** A token-free walkthrough of a fictional property, served locally from the frontend.
- **Open-source implementation:** The authenticated workspace, scheduler, Agent and evidence pipeline are available under the MIT license.

![Simulated hotel dashboard with endpoint trends and service health](docs/assets/screenshots/hotel-dashboard.jpg)

*Aster Quay Hotel is fictional. Dashboard data is simulated.*

## Why I Built This

Supporting hotel LAN/WLAN, Windows workstations, front desk systems and POS connectivity exposed a recurring problem: DNS, TCP, TLS and HTTP checks were spread across tools, repeated manually, and difficult to hand off with consistent evidence. I built NetGuardian to bring authorized checks, scheduled observations, incident history and evidence reports into one workflow. It grew from a Streamlit prototype into a FastAPI control plane, a Next.js workspace, a durable worker and an outbound Windows Agent.

## Hengze Hotel IT Operations

NetGuardian has been approved for use and deployed in IT operations at Hengze Hotel, where I worked as an IT Infrastructure & Network Engineer. My responsibilities included LAN/WLAN support, TCP/IP, DNS and DHCP troubleshooting, Windows support, front desk and POS connectivity, and Python automation. Production network data, deployment scope and the modules used at the hotel are private. Device counts, availability, MTTR and efficiency gains are not published. CI and integration tests do not validate hotel production performance. The public demo is isolated and uses Aster Quay Hotel, a fictional property.

## Screenshots

The images here and in the opening section are real browser captures of the simulated Aster Quay Hotel demo.

![Simulated topology with a selected POS node and incident timeline](docs/assets/screenshots/hotel-topology.jpg)

![Simulated POS HTTP 503 in the DNS, TCP, TLS and HTTP diagnostic view](docs/assets/screenshots/hotel-diagnostics.jpg)

[More screenshots, including the authenticated workspace and evidence report](docs/product/DEMO_GUIDE.md)

## End-to-End IT Operations Workflow

```mermaid
flowchart LR
    A["Configure and authorize · operator"] --> B["Monitor · scheduler and probe"]
    B --> C["Detect · threshold and incident"]
    C --> D["Investigate · operator reviews evidence"]
    D --> E["Report · operator requests snapshot"]
    E --> F["Review · operator verifies and hands off"]
```

In the demo, a POS endpoint returns HTTP 503 while the probe completes and collection remains current. The operator can inspect recorded layer evidence and review possible explanations. A separate local HTTPS integration scenario exercises incident creation, HTTP 204 recovery and an evidence snapshot. In the workspace the scheduler runs checks and applies incident thresholds automatically. An operator authorizes targets, assesses probable causes, requests reports and decides what action to take. Recovery records a measured change; it does not identify a root cause.

## Core Features

| Capability | Implementation and verification |
| --- | --- |
| Network diagnostics | DNS, TCP, TLS and HTTP HEAD. ICMP and traceroute are opt-in system probes with bounded commands and explicit capability failures. HTTP duration and ICMP RTT are separate. |
| Scheduled monitoring and incidents | Durable schedules, freshness, failure and recovery thresholds, retained incident evidence and explicit gaps. Covered by worker and local integration checks. |
| Windows Agent and comparison | Enrollment and outbound HTTPS, independent local policy, and cloud-to-Agent comparison when the observations meet compatibility requirements. Verified in controlled integration. |
| Hospitality dashboard and topology | Live workspace trends use authorized API data. The interactive React Flow topology uses configured logical links in the simulated demo. |
| Evidence reports | Immutable snapshots and SHA-256 integrity verification. The digest can detect modified content; it does not authenticate the author or the observation. |
| Optional Ollama investigation | Evidence-checked recorded facts and separately labeled hypotheses. Experimental interpretation, with limited real-model validation. |
| Security | Default-deny origin policies, DNS/address validation and IP pinning, tenant-scoped data access and independent Agent policy. |

## Architecture

```mermaid
flowchart LR
    subgraph Browser
      D["Public demo · synthetic fixture"]
      U["Authenticated workspace"]
    end
    subgraph Control["Trusted control plane"]
      W["Next.js authenticated proxy"] --> API["FastAPI · workspace and target policy"]
      API --> DB[("SQLite / PostgreSQL · jobs and evidence")]
      R["Worker · schedules and leases"] <--> DB
    end
    U -->|"Bearer token"| W
    AG["Windows Agent · local policy"] -->|"Outbound HTTPS · poll and submit"| API
    R -->|"Approved cloud targets"| T["Network targets"]
    AG -->|"Locally approved targets"| T
```

The API stores jobs; the worker or an enrolled Agent executes them asynchronously. Measurements share a versioned schema, and the database links incident evidence to source jobs. The authenticated workspace calls an allowlisted Next.js proxy. The demo has its own static fixture and no control API connection. [System design](docs/architecture/SYSTEM_DESIGN.md) · [Data model](docs/architecture/DATA_MODEL.md)

## Demo Quick Start

Use Node.js 24 and pnpm 11.25.0. Run these commands in PowerShell from a directory where you can create a checkout:

```powershell
git clone https://github.com/TYF009/NetGuardian.git
Set-Location NetGuardian
npm install -g pnpm@11.25.0
pnpm --dir web install --frozen-lockfile
pnpm --dir web build
pnpm --dir web start
```

Open [the local demo](http://127.0.0.1:3000/). `/demo` is an alias. The demo requires no Python, database, Agent, backend or token, and sends no real probes. [Demo walkthrough](docs/product/DEMO_GUIDE.md)

## Full Local Deployment

Use Windows, Python 3.11, uv 0.13.7, Node.js 24 and pnpm 11.25.0. Install and build the Web app as above, then stop the demo process with Ctrl+C so the full launcher can use port 3000. From the repository root, install Python dependencies and run the one-time setup. Copy the displayed local administrator token to a password manager. The ID file is under the ignored local runtime directory:

```powershell
python -m pip install uv==0.13.7
uv sync --locked
$workspaceToken = (uv run --locked python -c "import secrets; print(secrets.token_urlsafe(32))").Trim()
$workspaceToken
New-Item -ItemType Directory -Path .netguardian-local -Force | Out-Null
$vantageFile = '.netguardian-local/workspace-vantage-id.txt'
if (-not (Test-Path -LiteralPath $vantageFile)) {
    [guid]::NewGuid().ToString() | Set-Content -LiteralPath $vantageFile -Encoding ascii
}
```

On first startup and in each new PowerShell session, load the same local token and saved Worker vantage ID. Use an empty allowlist for a no-probe trial. Back up any existing database before using `--migrate`:

```powershell
$workspaceToken = [pscredential]::new(
    'local', (Read-Host 'Local workspace token' -AsSecureString)
).GetNetworkCredential().Password
$env:NETGUARDIAN_TOKENS = @{ $workspaceToken = 'local' } | ConvertTo-Json -Compress
$env:NETGUARDIAN_ORIGINS = '{}'
$env:NETGUARDIAN_VANTAGE_ID = (Get-Content -LiteralPath '.netguardian-local/workspace-vantage-id.txt' -Raw).Trim()
uv run --locked python -m scripts.run_windows --migrate
```

Open [the authenticated workspace](http://127.0.0.1:3000/workspace) and use the generated local token. Keep the saved ID across restarts. The ID labels observations from this Worker location. It grants no access. Keep production location IDs out of demos and test environments. When started with `--migrate`, the launcher applies Alembic migrations before starting the services. Routine restarts can omit this flag when the database schema is current. The launcher starts the API, Worker and Web on loopback. [Separate service commands, database settings, Agent enrollment and troubleshooting](docs/operations/LOCAL_DEVELOPMENT.md) · [Operator runbook](docs/operations/RUNBOOK.md)

## First Diagnostic Walkthrough

### Public Demo

1. Install and start the frontend using [Demo Quick Start](#demo-quick-start). Open the Aster Quay Hotel dashboard and confirm the **DEMO / SIMULATED** banner.
2. Open **Services** and compare the POS probe outcome, endpoint response and collection freshness. The simulated probe completed and recorded HTTP 503.
3. Open **Topology**, select **POS terminals**, then follow **DEMO-104 · Open** to the incident. Choose **Inspect evidence**.
4. Read the DNS, TCP, TLS and HTTP cards. Expand **Raw probe evidence (JSON)** to see the simulated record. Possible explanations and next checks are separate from observations.

### Authenticated Workspace

1. Use [Full Local Deployment](#full-local-deployment) to install the services and generate a local administrator token. Use a separate local or test workspace, away from production data.
2. Choose an exact HTTPS origin that you own or have explicit permission to monitor and that the cloud Worker can reach under its address policy. The value below is a placeholder. Replace it before running the example. Stop the launcher, set the allowlist in its PowerShell session, then restart without migration if the schema is current.

   ```powershell
   $approvedOrigin = 'https://authorized-host.example:443'
   $env:NETGUARDIAN_ORIGINS = @{ local = @($approvedOrigin) } | ConvertTo-Json -Compress
   uv run --locked python -m scripts.run_windows
   ```

3. Open `/workspace`, enter the local token, and choose **Connect**. In **Diagnostics**, select the approved target, a probe such as **HTTP**, and **Cloud worker**. Click **Run diagnostic**. In **Diagnostic history**, wait for the job to finish and use **Inspect** to see its recorded result. If no measurement was returned, check the Worker and task state. An HTTP error response can still come from a completed probe.
4. In **Monitors**, select the approved target, probe and **Cloud worker**, give the monitor a name and an interval of at least 60 seconds, then choose **Create monitor**. Open **View history** after scheduled runs have been recorded.
5. Open **Incidents** if the monitor has enough qualifying observations. The UI uses the default thresholds of three consecutive failures to open an incident and two consecutive successes to recover it. If an incident exists, choose **Create evidence report** and find the saved snapshot in **Reports**. A healthy, new or missing-data monitor may have no report to create.

## Testing & Verification

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked pytest -q
uv run --locked pytest integration/test_tls.py integration/test_dns_runtime.py integration/test_agent_workflow.py -q
pnpm --dir web test
pnpm --dir web typecheck
pnpm --dir web build
```

[GitHub Actions](https://github.com/TYF009/NetGuardian/actions/workflows/ci.yml) runs Windows and Ubuntu checks, PostgreSQL integration, OpenAPI drift checks and the Web build. Some integration cases require a disposable PostgreSQL database, real model or OS credential store. [Verification record](docs/product/VERIFICATION.md) · [Browser QA](docs/product/BROWSER_QA.md) · [Windows delivery and limits](docs/product/WINDOWS_DELIVERY.md)

CI and test fixtures document behavior in controlled environments. The approved hotel use is a separate operational fact. Current local delivery targets Windows; the Compose configuration does not establish a supported public or cross-machine deployment.

## Security & Privacy

Probe only targets you are authorized to monitor. The control plane enforces exact origin allowlists and scope boundaries. Cloud address validation rejects private and special addresses; an Agent independently enforces its approved origins and explicit private CIDRs where supported. Workspace bearer tokens stay in browser memory and Agent credentials use the OS credential store. Keep production topology, addresses, logs and credentials private. The public demo uses only synthetic data. [Threat model](docs/security/THREAT_MODEL.md) · [Licensing and third-party assets](NOTICE.md)

## Roadmap & Author

Next priorities are private asset and zone configuration, device telemetry, monitor-to-topology mapping, stronger evidence analysis, and broader deployment and operational validation.

**TYF009** · Communication Engineering background · HCIP Datacom · Hotel IT infrastructure and technical support · Network automation.
