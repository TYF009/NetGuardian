# Hospitality demo walkthrough

Use the [frontend quick start](../../README.md#demo-quick-start) and open the
local home page. Aster Quay Hotel is fictional, and the page marks its
observations as **DEMO / SIMULATED**. The fixture never connects to the control
API or dispatches jobs.

1. In **Overview**, inspect an endpoint trend bar to see its recorded status.
   A gap means no data. An HTTP 503 is an observed response.
2. In **Services**, compare the POS probe outcome, HTTP endpoint health and
   collection freshness. A HEAD result cannot measure an entire POS transaction.
3. In **Topology**, select **POS terminals** to view the simulated incident link.
   Edges represent configured logical links.
4. Open **Incidents**, then **Inspect evidence**. The troubleshooting view shows
   observed DNS, TCP, TLS and HTTP layers, possible explanations, suggested
   checks, and raw simulated evidence.

## Screenshot gallery

The first four images were captured from the running frontend with the demo
fixture. The last two come from the authenticated frontend with a disposable
SQLite database from the loopback HTTPS integration test. The database
contains test-only records for `netguardian.test`. The report reflects actual
test fixture responses (HTTP 503 and 204). All captures exclude credentials
and hotel operational data.

| Capture | Environment |
| --- | --- |
| [Dashboard and Business Service Health](../assets/screenshots/hotel-dashboard.jpg) | Simulated demo, desktop |
| [Topology and incident timeline](../assets/screenshots/hotel-topology.jpg) | Simulated demo, desktop |
| [POS troubleshooting](../assets/screenshots/hotel-diagnostics.jpg) | Simulated demo, desktop |
| [Mobile overview](../assets/screenshots/hotel-mobile.jpg) | Simulated demo, dark theme |
| [Authenticated engineer workspace](../assets/screenshots/test-workspace.jpg) | Local HTTPS test records |
| [Evidence report](../assets/screenshots/test-evidence-report.jpg) | Local HTTPS test records, verified snapshot checksum |

The workspace requires the [full local services](../operations/LOCAL_DEVELOPMENT.md).
Generate a separate local token, start with no allowed origins, and access
`/workspace`. The empty state is expected for a new workspace.
