#!/usr/bin/env python3

import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from collections import deque
from colorama import Fore, Style, init
import argparse
import time
import sys

init(autoreset=True)

# =========================================
# TOR PROXY
# =========================================
TOR_PROXIES = {
    "http": "socks5h://127.0.0.1:9050",
    "https": "socks5h://127.0.0.1:9050"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

visited = set()
found_links = set()

# =========================================
# BANNER
# =========================================
def banner():
    print(Fore.RED + r"""
   ____                  _       __     __
  / __ \___  ___  ____  | |     / /__  / /_
 / / / / _ \/ _ \/ __ \ | | /| / / _ \/ __/
/ /_/ /  __/  __/ /_/ / | |/ |/ /  __/ /_
\____/\___/\___/ .___/  |__/|__/\___/\__/
              /_/

        TOR ONION SCRAPER
    """)

# =========================================
# HELP MENU (NUMBERED)
# =========================================
def help_menu():
    banner()

    print(Fore.CYAN + "\n[1] BASIC USAGE")
    print("python3 deepweb_scraper.py --seed URL --keywords word1 word2\n")

    print(Fore.CYAN + "[2] AHMIA SEARCH MODE")
    print("python3 deepweb_scraper.py --ahmia cybersecurity --keywords privacy security\n")

    print(Fore.CYAN + "[3] TOR CHECK")
    print("python3 deepweb_scraper.py --check-tor\n")

    print(Fore.CYAN + "[4] FULL CRAWL EXAMPLE")
    print("""python3 deepweb_scraper.py \\
--seed http://example.onion \\
--keywords hacking security forum \\
--pages 20 \\
--output results.txt\n""")

    print(Fore.CYAN + "[5] OPTIONAL FLAGS")
    print("--pages   number of pages to crawl (default 20)")
    print("--output  save results file")
    print("--delay   delay between requests\n")

# =========================================
# TOR CHECK
# =========================================
def check_tor():
    print(Fore.CYAN + "[*] Checking Tor connection...\n")

    try:
        r = requests.get(
            "https://check.torproject.org",
            proxies=TOR_PROXIES,
            timeout=20
        )

        if "Congratulations" in r.text:
            print(Fore.GREEN + "[+] Tor is working")
        else:
            print(Fore.RED + "[-] Tor NOT detected")

    except Exception as e:
        print(Fore.RED + f"[-] Error: {e}")

# =========================================
# AHMIA SEARCH
# =========================================
def search_ahmia(keyword, limit=10):

    results = []

    try:
        url = f"https://ahmia.fi/search/?q={keyword}"

        r = requests.get(url, headers=HEADERS, timeout=20)

        soup = BeautifulSoup(r.text, "html.parser")

        for a in soup.find_all("a", href=True):

            href = a["href"]

            if ".onion" in href and href not in results:
                results.append(href)

            if len(results) >= limit:
                break

    except Exception as e:
        print(Fore.RED + f"[-] Ahmia error: {e}")

    return results

# =========================================
# EXTRACT LINKS
# =========================================
def extract_onion_links(html, base_url):

    links = set()

    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):

        try:
            full = urljoin(base_url, a["href"])

            if ".onion" in full:
                links.add(full)

        except:
            pass

    return links

# =========================================
# KEYWORD CHECK
# =========================================
def contains_keywords(text, keywords):

    text = text.lower()

    for k in keywords:
        if k.lower() in text:
            return True

    return False

# =========================================
# CRAWLER
# =========================================
def crawl(seed_urls, keywords, max_pages, output_file, delay):

    queue = deque(seed_urls)
    page = 0

    print(Fore.GREEN + "[+] Starting crawler...\n")

    while queue and page < max_pages:

        url = queue.popleft()

        if url in visited:
            continue

        visited.add(url)

        try:
            print(Fore.CYAN + f"[VISIT] {url}")

            r = requests.get(
                url,
                proxies=TOR_PROXIES,
                headers=HEADERS,
                timeout=25
            )

            if r.status_code != 200:
                continue

            html = r.text

            if contains_keywords(html, keywords):
                print(Fore.GREEN + f"[MATCH] {url}")

                with open(output_file, "a") as f:
                    f.write(url + "\n")

            links = extract_onion_links(html, url)

            for l in links:
                if l not in visited:
                    queue.append(l)
                    found_links.add(l)

            print(Fore.YELLOW + f"[+] Found {len(links)} links")

            page += 1
            time.sleep(delay)

        except Exception as e:
            print(Fore.RED + f"[-] Error: {e}")

    print(Fore.GREEN + "\n[+] Done")
    print(Fore.GREEN + f"[+] Total found: {len(found_links)}")

# =========================================
# MAIN
# =========================================
def main():

    parser = argparse.ArgumentParser(add_help=False)

    parser.add_argument("--seed", nargs="+")
    parser.add_argument("--keywords", nargs="+")
    parser.add_argument("--pages", type=int, default=20)
    parser.add_argument("--output", default="results.txt")
    parser.add_argument("--delay", type=int, default=2)

    parser.add_argument("--ahmia")
    parser.add_argument("--check-tor", action="store_true")
    parser.add_argument("-h", "--help", action="store_true")

    args = parser.parse_args()

    if args.help or len(sys.argv) == 1:
        help_menu()
        return

    if args.check_tor:
        check_tor()
        return

    banner()

    seeds = []

    # AHMIA MODE
    if args.ahmia:
        print(Fore.CYAN + f"[*] Searching Ahmia for: {args.ahmia}")
        seeds = search_ahmia(args.ahmia)

        if not seeds:
            print(Fore.RED + "[-] No results found")
            return

        for s in seeds:
            print(Fore.YELLOW + s)

    elif args.seed:
        seeds = args.seed

    else:
        print(Fore.RED + "[-] No seed or ahmia query provided")
        help_menu()
        return

    if not args.keywords:
        print(Fore.RED + "[-] Missing keywords")
        help_menu()
        return

    crawl(seeds, args.keywords, args.pages, args.output, args.delay)

# =========================================
# RUN
# =========================================
if __name__ == "__main__":
    main()