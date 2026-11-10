"""Opt-in legacy UI client for the authenticated V2 execution/persistence boundary."""

import asyncio
import ipaddress
import json
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import TypeAdapter

from probe_core.policy import parse_target
from service.api import CreateJob, JobAccepted, JobDetail, JobSummary


class V2Client:
    def __init__(self, origin, token, *, transport=None):
        parsed = urlsplit(origin)
        try:
            loopback = ipaddress.ip_address(parsed.hostname or "").is_loopback
        except ValueError:
            loopback = False
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
            or parsed.port == 0
            or (parsed.scheme == "http" and not loopback)
        ):
            raise ValueError("Control API must be an HTTPS origin or literal-loopback HTTP origin")
        if not token.isascii() or not 32 <= len(token) <= 512:
            raise ValueError("Enter a valid workspace token")
        self.origin, self.token, self.transport = origin.rstrip("/"), token, transport

    def request(self, method, path, body=None):
        async def exchange():
            async with (
                asyncio.timeout(10),
                httpx.AsyncClient(
                    base_url=self.origin,
                    transport=self.transport,
                    trust_env=False,
                    follow_redirects=False,
                    timeout=3,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept-Encoding": "identity",
                    },
                ) as client,
                client.stream(method, path, json=body) as response,
            ):
                if not response.is_success:
                    raise ValueError(f"Control API rejected request ({response.status_code})")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ValueError("Compressed control responses are not accepted")
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > 262144:
                        raise ValueError("Control response exceeds 256 KiB")
                    content.extend(chunk)
                return json.loads(content)

        return asyncio.run(exchange())

    def targets(self):
        data = self.request("GET", "/api/targets")
        origins = TypeAdapter(list[tuple[str, int, Literal["http", "https"]]]).validate_python(
            data["origins"]
        )
        values = []
        for host, port, scheme in origins:
            value = f"{scheme}://{'[' + host + ']' if ':' in host else host}:{port}"
            parse_target(value)
            values.append(value)
        return values

    def submit(self, target, kind):
        job = CreateJob(target=target, kind=kind)
        return JobAccepted.model_validate(
            self.request("POST", "/api/jobs", job.model_dump(mode="json"))
        )

    def jobs(self):
        return TypeAdapter(list[JobSummary]).validate_python(self.request("GET", "/api/jobs"))

    def detail(self, job_id):
        return JobDetail.model_validate(self.request("GET", f"/api/jobs/{UUID(job_id)}"))


def render(origin):
    import streamlit as st

    st.subheader("V2 diagnostics")
    st.caption(
        "Uses the authenticated V2 API and shared worker probes. "
        "This page never probes targets directly."
    )

    def disconnect():
        for key in list(st.session_state):
            if key.startswith("v2_"):
                del st.session_state[key]

    if not st.session_state.get("v2_connected"):
        with st.form("v2_login"):
            token = st.text_input("Workspace token", type="password", key="v2_token")
            connected = st.form_submit_button("Connect to V2")
        if connected:
            try:
                st.session_state.v2_origins = V2Client(origin, token).targets()
                st.session_state.v2_credential = token
                st.session_state.v2_connected = True
                st.rerun()
            except (ValueError, KeyError, httpx.HTTPError, TimeoutError):
                st.error("Cannot connect: check the configured API and workspace token.")
        return
    st.button("Disconnect V2", on_click=disconnect)
    try:
        client = V2Client(origin, st.session_state.v2_credential)
        origins = client.targets()  # Recheck policy on each interaction.
        with st.form("v2_probe"):
            target = st.selectbox("Approved V2 origin", origins, index=None)
            kind = st.selectbox(
                "V2 probe kind", ["dns", "tcp", "tls", "http", "icmp", "traceroute"]
            )
            submitted = st.form_submit_button("Queue V2 diagnostic", disabled=not origins)
        if not origins:
            st.info("No authorized targets. An administrator must configure the API origin policy.")
        if submitted and target in origins:
            accepted = client.submit(target, kind)
            st.success(f"Queued job {accepted.id}. The V2 worker executes it independently.")
        jobs = client.jobs()
        selected = st.selectbox(
            "Recorded V2 job",
            [job.id for job in jobs],
            index=None,
            format_func=lambda value: next(
                f"{job.kind.upper()} · {job.id}" for job in jobs if job.id == value
            ),
        )
        if st.button("Inspect / refresh V2 result", disabled=selected is None):
            detail = client.detail(selected)
            st.write(f"Task state: {detail.state}")
            if detail.result:
                result = detail.result
                st.write(
                    f"Observed: {result.observed_at.isoformat()} · Vantage: {result.vantage_id}"
                )
                st.caption("HTTP duration is not ICMP RTT. Missing values are unknown, not zero.")
                st.json(result.model_dump(mode="json"))
            else:
                st.info(
                    "No measurement recorded. Task state alone does not establish target health."
                )
    except (ValueError, KeyError, httpx.HTTPError, TimeoutError):
        st.error(
            "V2 request failed. Check authorization and service availability; "
            "no result is inferred."
        )
