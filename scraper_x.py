# scraper_x.py — X scraper using manually exported cookies from Chrome

import asyncio
import os
import json
from datetime import datetime
from playwright.async_api import async_playwright
from database import save_post
from config import (BOOLEAN_QUERIES, INDIVIDUAL_QUERIES, EXCLUDE_TERMS,
                    MAX_POSTS_PER_KEYWORD, TRACK_FROM_DATE)

COOKIES_TXT = "x_cookies.txt"
COOKIES_JSON = "x_cookies.json"

def is_excluded(text):
    return any(term.lower() in text.lower() for term in EXCLUDE_TERMS)

def has_context(text, keywords):
    return any(kw.lower() in text.lower() for kw in keywords)

def build_search_url(search_string):
    full_query = f"{search_string} since:{TRACK_FROM_DATE}"
    encoded = full_query.replace(" ", "%20").replace('"', '%22')
    return f"https://x.com/search?q={encoded}&src=typed_query&f=live&lang=en"

def parse_cookies_txt(filepath):
    """Parse Netscape/cookies.txt format into Playwright cookie list."""
    cookies = []
    try:
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                domain, flag, path, secure, expiry, name, value = parts[:7]
                cookies.append({
                    "name": name,
                    "value": value,
                    "domain": domain.lstrip("."),
                    "path": path,
                    "secure": secure.upper() == "TRUE",
                    "sameSite": "Lax"
                })
        print(f"[X] Parsed {len(cookies)} cookies from {filepath}")
        return cookies
    except Exception as e:
        print(f"[X] Error parsing cookies.txt: {e}")
        return []

async def scrape_query(page, search_string, label, context_keywords):
    search_url = build_search_url(search_string)
    retries = 3
    print(f"[X] Searching '{label}' since {TRACK_FROM_DATE}...")

    while retries > 0:
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(6000)

            # Check if we got redirected to login
            if "login" in page.url:
                print(f"[X] Redirected to login — cookies may be expired")
                return

            collected = set()
            scroll_attempts = 0

            while len(collected) < MAX_POSTS_PER_KEYWORD and scroll_attempts < 10:
                page_text = await page.inner_text("body")

                if is_excluded(page_text) and not has_context(page_text, context_keywords):
                    await page.evaluate("window.scrollBy(0, 1500)")
                    await page.wait_for_timeout(3000)
                    scroll_attempts += 1
                    continue

                links = await page.eval_on_selector_all(
                    'a[href*="/status/"]', 'els => els.map(e => e.href)'
                )
                for link in links:
                    if "/status/" in link:
                        collected.add(link.split("?")[0])

                await page.evaluate("window.scrollBy(0, 1500)")
                await page.wait_for_timeout(3000)
                scroll_attempts += 1

            for url in list(collected)[:MAX_POSTS_PER_KEYWORD]:
                save_post("x", url, label, datetime.utcnow().isoformat())

            print(f"[X] '{label}' → {min(len(collected), MAX_POSTS_PER_KEYWORD)} posts")
            return

        except Exception as e:
            retries -= 1
            if retries > 0:
                print(f"[X] Retrying '{label}'... ({retries} left)")
                await page.wait_for_timeout(6000)
            else:
                print(f"[X] Skipping '{label}': {e}")

async def scrape_x():
    print("[X] Starting scrape...")

    if not os.path.exists(COOKIES_TXT):
        print(f"[X] ERROR: {COOKIES_TXT} not found in folder.")
        print("[X] Please export cookies from Chrome and place x_cookies.txt in the discourse-tracker folder.")
        return

    cookies = parse_cookies_txt(COOKIES_TXT)
    if not cookies:
        print("[X] No cookies loaded — skipping X scrape.")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800}
        )

        # Load cookies directly
        try:
            await context.add_cookies(cookies)
            print("[X] Cookies loaded successfully.")
        except Exception as e:
            print(f"[X] Error loading cookies: {e}")
            await browser.close()
            return

        page = await context.new_page()

        # Verify we're logged in
        await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await page.screenshot(path="x_login_step1.png")

        if "login" in page.url:
            print("[X] Cookies didn't work — may be expired. Re-export from Chrome and try again.")
            await browser.close()
            return

        print(f"[X] Logged in! URL: {page.url}")

        for query in BOOLEAN_QUERIES:
            await scrape_query(page, query["search_string"], query["label"], query["context_keywords"])
        for query in INDIVIDUAL_QUERIES:
            await scrape_query(page, query["search_string"], query["label"], query["context_keywords"])

        await browser.close()
    print("[X] Done.")

def run():
    asyncio.run(scrape_x())

if __name__ == "__main__":
    run()
