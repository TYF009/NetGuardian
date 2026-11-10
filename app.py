"""Safe legacy UI with an optional authenticated V2 diagnostic adapter."""

import os
from pathlib import Path

import streamlit as st

from diagnostics import DISABLED_REASON, format_http_duration, get_http_request_duration

st.set_page_config(page_title="NetGuardian", layout="wide")
portrait = Path(__file__).with_name("Felix.jpg")
if portrait.is_file():
    st.sidebar.image(str(portrait), caption="Developer: Felix")
else:
    st.sidebar.caption("Developer: Felix")
st.sidebar.title("NetGuardian")
st.sidebar.caption("Vantage: the probe server, not the browser user's network.")
st.sidebar.info("Network identity and third-party geolocation lookups are temporarily disabled.")

default_sites = {
    "Google": "www.google.com",
    "YouTube": "www.youtube.com",
    "Amazon": "www.amazon.com",
    "GitHub": "www.github.com",
    "Cloudflare": "1.1.1.1",
}
selected_sites = st.sidebar.multiselect("Targets", options=list(default_sites), default=[])
st.title("Network Engineering Toolkit")
st.warning("Legacy direct tools: " + DISABLED_REASON)
monitor, route, toolbox = st.tabs(["HTTP Monitor", "Route Diagnosis", "Toolbox"])
with monitor:
    st.subheader("HTTP request duration")
    st.caption(
        "HTTP request duration is not ICMP round-trip time (RTT). "
        "No measurements are collected in this safety baseline."
    )
    if not selected_sites:
        st.info("Select targets to view their availability. No probe will be executed.")
    else:
        for column, site in zip(st.columns(len(selected_sites)), selected_sites, strict=True):
            column.metric(
                site, format_http_duration(get_http_request_duration(default_sites[site]))
            )
    st.button("Start monitoring", disabled=True)
    st.info(
        "Charts and CSV export will return when real, policy-approved measurements are available."
    )
with route:
    st.subheader("Traceroute")
    st.info("Temporarily disabled until bounded, shell-free platform adapters are available.")
    st.button("Start trace", disabled=True)
with toolbox:
    for title in ("TCP port check", "HTTP status", "DNS lookup", "ICMP RTT"):
        st.subheader(title)
        st.button(f"Run {title}", disabled=True)
    st.caption("These capabilities remain planned; no arbitrary targets are executed.")


if os.environ.get("NETGUARDIAN_STREAMLIT_V2") == "true":
    from legacy_v2 import render

    render(os.environ.get("NETGUARDIAN_API_URL", "http://127.0.0.1:8000"))
