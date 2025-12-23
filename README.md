# 🚀 NetGuardian Pro

**NetGuardian Pro** is a comprehensive, cloud-native network diagnostic toolkit built with Python and Streamlit. It provides real-time visualization of network performance and deep-dive diagnostic tools for network engineers and IT enthusiasts.



## 🌐 Live Demo
Check out the live application here: [https://netguardian-felixtong.streamlit.app/](https://netguardian-felixtong.streamlit.app/)

---

## ✨ Key Features

### 1. 📊 Real-time Network Monitor
- **Multi-target Tracking**: Monitor latency for multiple websites (Baidu, GitHub, Steam, etc.) simultaneously.
- **Dynamic Charting**: Real-time line charts visualize latency fluctuations and stability trends.
- **Auto-Refresh**: Configurable intervals and history retention points.

### 2. 🔍 Advanced Diagnostics
- **Intelligent Traceroute**: Discover the exact path data packets take across the globe with integrated IP Geolocation and ISP identification.
- **DNS Lookup**: Resolve hostnames to multiple IP addresses and identify CDN usage.
- **HTTP Status Checker**: Verify L7 application health beyond simple connectivity.

### 3. 🛡️ Engineer's Toolbox
- **TCP Port Scanner**: Audit common service ports (80, 443, 22, etc.) for availability.
- **Public Identity Card**: Instant view of your Public IP, Location, and ISP.
- **Local Info**: Quick access to local Hostname and Internal IP.

### 4. 💾 Data Management
- **One-click Export**: Download all captured monitoring data into a professional CSV report for post-incident analysis.

---

## 🛠️ Technical Architecture

- **Frontend/UI**: Streamlit (Python-based Web Framework)
- **Networking**: 
    - `ICMP/TCP` for latency probing.
    - `Socket` for DNS and Port Scanning.
    - `Requests` for HTTP status and API integrations.
- **Data Handling**: Pandas for real-time data frame manipulation.
- **APIs**: IP-API for geolocation services.



---

## 🚀 Installation & Local Setup

To run this project locally, follow these steps:

1. **Clone the repository**:
   ```bash
   git clone [https://github.com/TYF009/NetGuardian-Pro.git](https://github.com/TYF009/NetGuardian-Pro.git)
   cd NetGuardian-Pro

2.Install dependencies:

pip install -r requirements.txt

3.Run the application:

streamlit run app.py


     🧑‍💻 Developer
        Name: Felix
        GitHub: @TYF009

                                      Developed with ❤️ for the Network Engineering Community.
