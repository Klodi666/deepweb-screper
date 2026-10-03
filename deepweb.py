#!/usr/bin/env python3
"""
multi_source_darkweb.py
-----------------------
Search 12+ dark web search engines simultaneously.

Engines: Ahmia, Torch, DuckDuckGo, TorDex, Not Evil, Tor66,
         DarkSearch, OnionLand, Just Onion, Excavator,
         DeepSearch, The Hidden Wiki

Features:
  * Auto Tor install/start
  * Multi-engine parallel search
  * Description extraction
  * Unified CSV output
  * Y/N startup prompt
"""

import csv
import os
import re
import sys
import time
import shutil
import platform
import logging
import argparse
import subprocess
from collections import deque
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from colorama import Fore, Style, init
    init(autoreset=True)
    COLOR = True
except ImportError:
    COLOR = False
    class Fore: RED=GREEN=YELLOW=CYAN=MAGENTA=WHITE=RESET=""
    class Style: RESET_ALL=""

# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("darkweb")

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
DEFAULT_TIMEOUT = 30
RETRY_ATTEMPTS = 2
BACKOFF_FACTOR = 2

TOR_SOCKS = "socks5h://127.0.0.1:9050"
TOR_PROXIES = {"http": TOR_SOCKS, "https": TOR_SOCKS}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

CSV_FIELDS = ["source", "query", "title", "url", "description"]

# ------------------------------------------------------------------
# ALL SEARCH ENGINES (12 engines)
# ------------------------------------------------------------------
SEARCH_ENGINES = {
    # ============ CLEARNET (accessible without Tor) ============
    "ahmia": {
        "url": "https://ahmia.fi/search/?q={q}",
        "type": "clearnet",
        "selector": "a[href*='.onion']",
        "block": ["li.result", "div.result", "article.result"],
    },
    "duckduckgo": {
        "url": "https://html.duckduckgo.com/html/?q={q}+site%3Aonion",
        "type": "clearnet",
        "selector": "a[href*='.onion']",
        "block": [".result", ".web-result"],
    },
    "onionland_clear": {
        "url": "https://onionlandsearchengine.com/search?q={q}",
        "type": "clearnet",
        "selector": "a[href*='.onion']",
        "block": [".result", "article", "li"],
    },
    "hiddenwiki_clear": {
        "url": "https://thehiddenwiki2024.com/search?q={q}",
        "type": "clearnet",
        "selector": "a[href*='.onion']",
        "block": [".result", "article", "li", "tr"],
    },

    # ============ ONION SERVICES (require Tor) ============
    "torch": {
        "url": "http://xmh57jrknzkhv6y3ls3ubitzfqnkrwxhopf5aygthi7d6rplyvk3noyd.onion/search?q={q}",
        "type": "onion",
        "selector": "a[href*='.onion']",
        "block": ["li", "tr", ".result"],
    },
    "tordex": {
        "url": "http://tordexu73joywapk2txdr54jed4imqledpcvcuf75qsas2gwdgksvnyd.onion/search?q={q}",
        "type": "onion",
        "selector": "a[href*='.onion']",
        "block": [".result", "li", "article"],
    },
    "not_evil": {
        "url": "http://notevilmtxf25uw7tskqxj6njlpebyrmlrerfv5hc4tuq7c7hilbyiqd.onion/search?q={q}",
        "type": "onion",
        "selector": "a[href*='.onion']",
        "block": ["li", "tr", ".result"],
    },
    "tor66": {
        "url": "http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search?q={q}",
        "type": "onion",
        "selector": "a[href*='.onion']",
        "block": [".result", "li", "article"],
    },
    "onionland_onion": {
        "url": "http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion/search?q={q}",
        "type": "onion",
        "selector": "a[href*='.onion']",
        "block": [".result", "li", "article"],
    },
    "deepsearch": {
        "url": "http://search7tdrcvri22rieiwgi5g46qnwsesvnubqav2xakhezv4hjzkkad.onion/search?q={q}",
        "type": "onion",
        "selector": "a[href*='.onion']",
        "block": [".result", "li", "article"],
    },
    "excavator": {
        "url": "http://2fd6cem2eipr5lfhpv52hub7gai2fks4ddubj5of36ris7lswhpntpad.onion/search?q={q}",
        "type": "onion",
        "selector": "a[href*='.onion']",
        "block": [".result", "li", "article"],
    },
    "just_onion": {
        "url": "http://justdirs5iebdkegiwbp3k6vwgwyr5mce7pztld23hlluy22ox4r3iad.onion/search?q={q}",
        "type": "onion",
        "selector": "a[href*='.onion']",
        "block": ["li", "tr", ".result", "td"],
    },

    # ============ API-BASED ============
    "darksearch": {
        "url": "https://darksearch.io/api/search?query={q}&page=1",
        "type": "api",
        "json": True,
    },
}

# ------------------------------------------------------------------
# Tor Auto-Install & Check
# ------------------------------------------------------------------
def is_tor_installed():
    return shutil.which("tor") is not None

def is_tor_running():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(("127.0.0.1", 9050))
        s.close()
        return True
    except Exception:
        return False

def install_tor():
    system = platform.system().lower()
    print(Fore.CYAN + f"[*] Installing Tor on {platform.system()} ...")
    try:
        if system == "linux":
            if shutil.which("apt"):
                subprocess.run(["sudo", "apt", "update", "-y"], check=True)
                subprocess.run(["sudo", "apt", "install", "-y", "tor"], check=True)
            elif shutil.which("dnf"):
                subprocess.run(["sudo", "dnf", "install", "-y", "tor"], check=True)
            elif shutil.which("pacman"):
                subprocess.run(["sudo", "pacman", "-Sy", "--noconfirm", "tor"], check=True)
            else:
                print(Fore.RED + "[-] Unsupported distro.")
                return False
        elif system == "darwin":
            if not shutil.which("brew"):
                print(Fore.RED + "[-] Install Homebrew first.")
                return False
            subprocess.run(["brew", "install", "tor"], check=True)
        elif system == "windows":
            if shutil.which("winget"):
                subprocess.run(["winget", "install", "-e", "--id", "TorProject.TorBrowser"], check=True)
            else:
                print(Fore.RED + "[-] Install Tor Browser manually.")
                return False
        print(Fore.GREEN + "\n[+] Tor successfully installed ✅\n")
        return True
    except Exception as e:
        print(Fore.RED + f"[-] Install failed: {e}")
        return False

def start_tor_service():
    system = platform.system().lower()
    try:
        if system == "linux":
            if shutil.which("systemctl"):
                subprocess.run(["sudo", "systemctl", "enable", "--now", "tor"], check=False)
            else:
                subprocess.Popen(["tor"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "darwin":
            subprocess.Popen(["brew", "services", "start", "tor"], check=False)
        elif system == "windows":
            subprocess.Popen(["tor"], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
        return is_tor_running()
    except Exception:
        return False

def ensure_tor():
    print(Fore.CYAN + "=" * 55)
    print(Fore.CYAN + "           TOR SETUP")
    print(Fore.CYAN + "=" * 55)

    if not is_tor_installed():
        print(Fore.YELLOW + "[!] Tor not found.")
        if not install_tor():
            return False
    else:
        print(Fore.GREEN + "[+] Tor already installed.")

    if not is_tor_running():
        print(Fore.CYAN + "[*] Starting Tor ...")
        if not start_tor_service():
            print(Fore.YELLOW + "[!] Start Tor manually: sudo systemctl start tor")
            return False

    try:
        r = requests.get("https://check.torproject.org/api/ip",
                         proxies=TOR_PROXIES, timeout=25)
        data = r.json()
        if data.get("IsTor"):
            print(Fore.GREEN + f"[+] Tor working ✅  Exit IP: {data.get('IP')}\n")
            return True
        print(Fore.RED + f"[-] Not through Tor (IP: {data.get('IP')})")
    except Exception as e:
        print(Fore.RED + f"[-] Check failed: {e}")
    return False

# ------------------------------------------------------------------
# HTTP
# ------------------------------------------------------------------
def http_get(url, use_tor=False, timeout=DEFAULT_TIMEOUT, retries=RETRY_ATTEMPTS):
    proxies = TOR_PROXIES if use_tor else None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, proxies=proxies,
                             timeout=timeout, allow_redirects=True)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            log.debug(f"GET fail ({attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(BACKOFF_FACTOR ** attempt)
    return None

# ------------------------------------------------------------------
# Search one engine
# ------------------------------------------------------------------
def search_engine(name, engine, query, tor_ok=False):
    """Search a single engine. Returns list of result dicts."""
    if engine["type"] == "onion" and not tor_ok:
        return []

    url = engine["url"].format(q=quote(query))
    use_tor = engine["type"] in ("onion", "clearnet")  # use Tor for all if available

    r = http_get(url, use_tor=use_tor)
    if not r:
        return []

    results = []
    seen = set()

    # JSON API handling
    if engine.get("json"):
        try:
            data = r.json()
            items = data.get("data", data.get("results", []))
            for item in items:
                link = item.get("link", item.get("url", ""))
                if not link or link in seen:
                    continue
                seen.add(link)
                results.append({
                    "source": name,
                    "query": query,
                    "title": item.get("title", urlparse(link).netloc),
                    "url": link,
                    "description": item.get("description", "")[:300],
                })
        except Exception as e:
            log.warning(f"JSON parse fail for {name}: {e}")
        return results

    # HTML parsing
    soup = BeautifulSoup(r.text, "html.parser")

    # Try structured blocks
    blocks = []
    for sel in engine.get("block", []):
        blocks = soup.select(sel)
        if blocks:
            break

    if blocks:
        for item in blocks:
            a = item.select_one(engine["selector"])
            if not a:
                continue
            link = a.get("href", "").strip()
            if not link or link in seen or ".onion" not in link:
                continue

            title = a.get_text(" ", strip=True) or urlparse(link).netloc
            # Try multiple description selectors
            desc = ""
            for dsel in ["p", ".description", ".result-description", ".snippet", "td"]:
                d = item.select_one(dsel)
                if d and d.get_text(strip=True):
                    desc = d.get_text(" ", strip=True)
                    break

            seen.add(link)
            results.append({
                "source": name,
                "query": query,
                "title": title,
                "url": link,
                "description": desc[:300],
            })

    # Fallback: any onion anchor
    if not results:
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if ".onion" in href and href not in seen:
                seen.add(href)
                results.append({
                    "source": name,
                    "query": query,
                    "title": a.get_text(" ", strip=True) or urlparse(href).netloc,
                    "url": href,
                    "description": "",
                })

    return results

# ------------------------------------------------------------------
# Multi-engine search
# ------------------------------------------------------------------
def multi_search(query, tor_ok=False):
    """Search ALL engines with one query."""
    all_results = []
    print(Fore.CYAN + f"\n{'='*60}")
    print(Fore.CYAN + f"  Searching ALL engines for: \"{query}\"")
    print(Fore.CYAN + f"{'='*60}\n")

    for name, engine in SEARCH_ENGINES.items():
        tag = f"{name:<20}"
        if engine["type"] == "onion" and not tor_ok:
            print(f"  {tag} SKIP (needs Tor)")
            continue

        results = search_engine(name, engine, query, tor_ok)
        print(f"  {tag} -> {len(results)} results")
        all_results.extend(results)

        # Small delay between engines
        time.sleep(0.5)

    print(Fore.GREEN + f"\n[+] Total raw results: {len(all_results)}")
    return all_results

# ------------------------------------------------------------------
# Save / View CSV
# ------------------------------------------------------------------
def save_csv(rows, filename):
    if not rows:
        print(Fore.YELLOW + "[!] No results to save.")
        return

    # Deduplicate by URL
    unique = {}
    for r in rows:
        if r["url"] not in unique:
            unique[r["url"]] = r
        else:
            # Append source if duplicate
            if r["source"] not in unique[r["url"]]["source"]:
                unique[r["url"]]["source"] += f", {r['source']}"

    rows = list(unique.values())

    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_FIELDS})

    print(Fore.GREEN + f"\n[+] Saved {len(rows)} unique results -> {filename}")

def view_csv(filename):
    if not os.path.exists(filename):
        print(Fore.RED + f"[-] {filename} not found.")
        return
    with open(filename, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(Fore.CYAN + f"\n=== {filename} ({len(rows)} rows) ===\n")
    for i, r in enumerate(rows, 1):
        print(Fore.YELLOW + f"[{i}] {r['title'][:70]}")
        print(f"    src : {r['source']}")
        print(f"    URL : {r['url']}")
        print(f"    DESC: {r['description'][:140]}")
        print()

# ------------------------------------------------------------------
# Banner / Help
# ------------------------------------------------------------------
BANNER = r"""
   ____             _     __        __   _
  |  _ \  ___  __ _| | __ \ \      / /__| |__
  | | | |/ _ \/ _` | |/ /  \ \ /\ / / _ \ '_ \
  | |_| |  __/ (_| |   <    \ V  V /  __/ |_) |
  |____/ \___|\__,_|_|\_\    \_/\_/ \___|_.__/

   MULTI-SOURCE DARK WEB SEARCH (12 ENGINES)
"""

def banner():
    print(Fore.MAGENTA + BANNER + Style.RESET_ALL)

def show_engines():
    print(Fore.CYAN + "\nLoaded Search Engines:\n")
    for i, (name, e) in enumerate(SEARCH_ENGINES.items(), 1):
        typ = e["type"].upper()
        print(f"  {i:2}. {name:<22} [{typ}]")
    print()

def help_menu():
    banner()
    show_engines()
    print(Fore.CYAN + "================= MENU =================")
    print(Fore.YELLOW + "[1]" + Fore.WHITE + " Search ALL 12 engines")
    print(Fore.YELLOW + "[2]" + Fore.WHITE + " Search selected engines")
    print(Fore.YELLOW + "[3]" + Fore.WHITE + " View last results CSV")
    print(Fore.YELLOW + "[4]" + Fore.WHITE + " Check / install Tor")
    print(Fore.YELLOW + "[0]" + Fore.WHITE + " Exit")
    print(Fore.CYAN + "========================================\n")

# ------------------------------------------------------------------
# Interactive
# ------------------------------------------------------------------
def interactive():
    banner()
    tor_ready = False

    # Auto Tor setup
    print(Fore.CYAN + "[*] Checking Tor ...")
    if is_tor_installed() and is_tor_running():
        print(Fore.GREEN + "[+] Tor ready ✅")
        tor_ready = True
    else:
        ans = input(Fore.YELLOW + "[?] Auto-install / start Tor? (Y/N): ").strip().lower()
        if ans == "y":
            tor_ready = ensure_tor()
        else:
            print(Fore.YELLOW + "[!] Clearnet-only mode (onion engines skipped).")

    # Y/N to start
    print()
    if input(Fore.CYAN + "[?] Start dark web search now? (Y/N): ").strip().lower() != "y":
        print("Exiting.")
        return

    last_csv = "darkweb_results.csv"

    while True:
        help_menu()
        choice = input(Fore.CYAN + "Select > " + Style.RESET_ALL).strip()

        if choice == "0":
            print("Bye.")
            return

        elif choice == "1":
            q = input("Search query: ").strip()
            if not q:
                continue
            out = input(f"Output CSV [{last_csv}]: ").strip() or last_csv
            last_csv = out
            rows = multi_search(q, tor_ok=tor_ready)
            save_csv(rows, out)

        elif choice == "2":
            # Engine selection
            names = list(SEARCH_ENGINES.keys())
            print("\nEnter engine numbers (comma-separated), or 'all':")
            for i, n in enumerate(names, 1):
                print(f"  {i}. {n}")
            sel = input("> ").strip()
            if sel.lower() == "all":
                chosen = names
            else:
                try:
                    idxs = [int(x.strip()) - 1 for x in sel.split(",")]
                    chosen = [names[i] for i in idxs if 0 <= i < len(names)]
                except Exception:
                    print(Fore.RED + "Invalid selection.")
                    continue

            q = input("Search query: ").strip()
            if not q:
                continue

            all_rows = []
            print(Fore.CYAN + f"\nSearching {len(chosen)} engines ...\n")
            for name in chosen:
                engine = SEARCH_ENGINES[name]
                if engine["type"] == "onion" and not tor_ready:
                    print(f"  {name:<20} SKIP (needs Tor)")
                    continue
                rows = search_engine(name, engine, q, tor_ready)
                print(f"  {name:<20} -> {len(rows)}")
                all_rows.extend(rows)
                time.sleep(0.3)

            out = input(f"Output CSV [{last_csv}]: ").strip() or last_csv
            last_csv = out
            save_csv(all_rows, out)

        elif choice == "3":
            view_csv(last_csv)

        elif choice == "4":
            tor_ready = ensure_tor()

        else:
            print(Fore.RED + "Invalid option.")

        input(Fore.CYAN + "\nPress Enter..." + Style.RESET_ALL)

# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Multi-source dark web search")
    p.add_argument("--search", "-s", help="Query to search")
    p.add_argument("--output", "-o", default="darkweb_results.csv")
    p.add_argument("--check-tor", action="store_true")
    p.add_argument("--install-tor", action="store_true")
    p.add_argument("--interactive", "-i", action="store_true")
    p.add_argument("--engines", help="Comma-separated engine names (default: all)")
    args = p.parse_args()

    if len(sys.argv) == 1 or args.interactive:
        interactive()
        return

    if args.install_tor or args.check_tor:
        ensure_tor()
        return

    if not args.search:
        print("Need --search QUERY")
        return

    tor_ok = ensure_tor()

    # Engine selection
    if args.engines:
        chosen = [e.strip() for e in args.engines.split(",")]
        engines = {k: v for k, v in SEARCH_ENGINES.items() if k in chosen}
    else:
        engines = SEARCH_ENGINES

    all_rows = []
    print(Fore.CYAN + f"\nSearching for: \"{args.search}\"\n")

    for name, engine in engines.items():
        if engine["type"] == "onion" and not tor_ok:
            print(f"  {name:<20} SKIP (needs Tor)")
            continue
        rows = search_engine(name, engine, args.search, tor_ok)
        print(f"  {name:<20} -> {len(rows)}")
        all_rows.extend(rows)

    save_csv(all_rows, args.output)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)