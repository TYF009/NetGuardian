# Hospitality IT operations UI

Open /demo to explore Aster Quay Hotel without a token. Every asset, connection,
incident and observation on that route is simulated. The route uses a checked-in
fixture and has no API client, credential state, or control actions. The root
route is the authenticated workspace. Credentials stay in its component memory,
and navigating away aborts its in-flight requests.

## Data and display

- The workspace overview uses the existing monitor and incident list endpoints.
  Trends use the selected monitor's existing runs endpoint on request. A probe
  outcome is current only if its run matches the latest job ID in a current
  collection snapshot. An earlier point remains historical evidence.
- Device online status is unknown because there is no device uptime telemetry.
  Probe completion, endpoint response and collection freshness are independent.
  HEAD 2xx–3xx describes endpoint response, while business workflow availability
  remains unknown without a representative transaction check. A received 503 can
  coexist with a successful transport probe and current collection.
- The charts use server job creation time in the workspace and sample timestamps
  in the demo. No observation is plotted as a gap. A 0% sample is an observed
  HTTP response outside the configured success range. The samples do not estimate
  full-period uptime. HTTP duration and ICMP RTT have separate metric labels.
- The demo's React Flow map depicts configured logical links. A keyboard asset
  selector provides access to the same details as pointer selection.
- Layered diagnostics read the existing Measurement contract. The existing
  monitor history, investigation and evidence report views remain available.
  Generic errors are not assigned to a particular network layer. Raw evidence
  stays available alongside hypotheses and next checks.

## Connecting an authorized property

Start with an operator-approved list of targets and probe types. Configure exact
allowed origins for the workspace and enroll an Agent only if the target can
also be authorized by the Agent's local policy. Keep credentials out of UI code
and public data. Verify collection from the intended vantage before creating
schedules. Current target restrictions still apply, including restrictions on
private and special addresses. Do not widen them to make private hotel targets
work. A future private-network design should define isolated and explicitly
scoped Agent policy, audit and egress controls before enabling such targets.

For real topology, add a private, authenticated asset configuration tied to the
workspace, with explicit monitor-to-asset mappings and reviewed logical links.
Keep the public scenario separate. Device uptime and business transaction checks
need their own contracts, sampling policies and permission reviews. Avoid
sending guest data, payment records or real infrastructure identifiers to the
demo or model.
