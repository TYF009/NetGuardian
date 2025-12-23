import streamlit as st
import subprocess
import re
import pandas as pd
import time
import requests
import socket
from datetime import datetime

def get_local_info():
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        return hostname, local_ip
    except:
        return "Unknown", "127.0.0.1"

def get_ping_latency(host):
    try:
        output = subprocess.check_output(
            f"ping -n 1 -w 800 {host}", 
            shell=True, stderr=subprocess.STDOUT
        ).decode('gbk')
        match = re.search(r"time[=<](\d+)ms", output) or re.search(r"时间[=<](\d+)ms", output)
        return int(match.group(1)) if match else None
    except:
        return None

def get_ip_info(ip):
    if ip in ["*", "127.0.0.1"] or ip.startswith("192.168.") or ip.startswith("10."):
        return "LAN/Internal"
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?lang=en", timeout=2)
        data = response.json()
        if data['status'] == 'success':
            return f"{data['country']} {data['regionName']} {data['city']} ({data['isp']})"
    except:
        pass
    return "Unknown Location"

def run_traceroute(host):
    try:
        output = subprocess.check_output(
            f"tracert -d -h 15 -w 500 {host}", 
            shell=True, stderr=subprocess.STDOUT
        ).decode('gbk')
        lines = output.split('\n')
        route_data = []
        for line in lines:
            match = re.search(r"^\s*(\d+)\s+.*?\s+(\d+\.\d+\.\d+\.\d+)", line)
            if match:
                hop_num, ip_addr = match.group(1), match.group(2)
                location = get_ip_info(ip_addr)
                route_data.append({"Hop": hop_num, "IP Address": ip_addr, "Location": location})
        return pd.DataFrame(route_data)
    except Exception as e:
        return f"Diagnostics Failed: {e}"

def check_port(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        result = s.connect_ex((ip, port))
        return "Open" if result == 0 else "Closed/Filtered"
    except:
        return "Error"
    finally:
        s.close()

def get_public_ip():
    try:
        response = requests.get('http://ip-api.com/json/?lang=en', timeout=3)
        return response.json()
    except:
        return None

def check_http_status(url):
    if not url.startswith('http'):
        url = 'https://' + url
    try:
        res = requests.get(url, timeout=3)
        return res.status_code
    except:
        return "Failed"

def get_dns_info(domain):
    try:
        result = socket.getaddrinfo(domain, None)
        ips = list(set([item[4][0] for item in result]))
        return ips
    except:
        return []

st.set_page_config(page_title="NetGuardian Pro", layout="wide")

st.sidebar.image("Felix.jpg", caption="Developer: Felix")
st.sidebar.title("🚀 NetGuardian Pro")

with st.sidebar.expander("👤 Network Identity", expanded=True):
    pub_info = get_public_ip()
    if pub_info:
        st.write(f"🌐 **Public IP**: `{pub_info['query']}`")
        st.write(f"🏢 **ISP**: {pub_info['isp']}")
        st.write(f"📍 **Location**: {pub_info['country']}, {pub_info['regionName']}")
    else:
        st.write("Public info unavailable")
    
    st.divider()
    hostname, local_ip = get_local_info()
    st.write(f"💻 **Local IP**: `{local_ip}`")

st.sidebar.header("⚙️ Configuration")
default_sites = {
    "Baidu": "www.baidu.com",
    "Bilibili": "www.bilibili.com",
    "GitHub": "www.github.com",
    "Steam": "store.steampowered.com",
    "Gateway": "192.168.1.1"
}
selected_sites = st.sidebar.multiselect("Targets", options=list(default_sites.keys()), default=list(default_sites.keys()))
update_interval = st.sidebar.slider("Interval (sec)", 1, 10, 2)
max_points = st.sidebar.slider("History Points", 10, 100, 30)

st.sidebar.markdown("---")
if 'multi_history' in st.session_state and not st.session_state.multi_history.empty:
    csv_data = st.session_state.multi_history.to_csv(index=False).encode('utf-8-sig')
    st.sidebar.download_button("📥 Export Report", data=csv_data, file_name="network_report.csv", mime="text/csv")

st.title("🌐 Network Engineering Toolkit")

tab1, tab2, tab3 = st.tabs(["📊 Real-time Monitor", "🔍 Route Diagnosis", "🛠️ Toolbox"])

with tab1:
    st.subheader("📍 Real-time Latency")
    cols = st.columns(len(selected_sites))
    metric_placeholders = {site: cols[i].empty() for i, site in enumerate(selected_sites)}
    
    st.subheader("📈 Latency Trends")
    chart_placeholder = st.empty()

with tab2:
    st.subheader("🔍 Traceroute Analysis")
    diag_col1, diag_col2 = st.columns([1, 2])
    with diag_col1:
        target_name = st.selectbox("Select Target", options=selected_sites)
        if st.button("Start Trace"):
            with st.spinner("Tracing path..."):
                df_route = run_traceroute(default_sites[target_name])
                with diag_col2:
                    st.dataframe(df_route, use_container_width=True)

with tab3:
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("🛡️ Port Scanner")
        scan_host = st.text_input("Target IP/Domain", value="www.baidu.com", key="port_host")
        scan_port = st.number_input("Port", value=80)
        if st.button("Scan Port"):
            status = check_port(scan_host, scan_port)
            st.info(f"Port {scan_port}: **{status}**")
        st.divider()
        st.subheader("🌐 HTTP Status")
        http_host = st.text_input("URL", value="www.github.com")
        if st.button("Check HTTP"):
            code = check_http_status(http_host)
            st.info(f"Status Code: **{code}**")

    with col_right:
        st.subheader("🔍 DNS Lookup")
        dns_domain = st.text_input("Enter Domain", value="www.bilibili.com")
        if st.button("Resolve DNS"):
            ips = get_dns_info(dns_domain)
            if ips:
                st.write(f"Resolved IPs for **{dns_domain}**:")
                for ip in ips:
                    loc = get_ip_info(ip)
                    st.code(f"{ip} -> {loc}")
            else:
                st.error("Resolution failed")

if 'multi_history' not in st.session_state:
    st.session_state.multi_history = pd.DataFrame(columns=['Time'] + selected_sites)

while True:
    now = datetime.now().strftime("%H:%M:%S")
    current_latencies = {'Time': now}
    for site in selected_sites:
        latency = get_ping_latency(default_sites[site])
        current_latencies[site] = latency
        with metric_placeholders[site]:
            if latency:
                st.metric(site, f"{latency} ms", delta_color="normal" if latency < 100 else "inverse")
            else:
                st.metric(site, "Timeout", delta_color="inverse")
    
    new_row = pd.DataFrame([current_latencies])
    st.session_state.multi_history = pd.concat([st.session_state.multi_history, new_row], ignore_index=True).iloc[-max_points:]
    with chart_placeholder:
        st.line_chart(st.session_state.multi_history.set_index('Time'))
    time.sleep(update_interval)