# scraper_instagram.py — uses /explore/search/keyword/ URL directly

import asyncio
import os
from datetime import datetime
from playwright.async_api import async_playwright
from database import save_post
from config import (BOOLEAN_QUERIES, INDIVIDUAL_QUERIES, EXCLUDE_TERMS,
                    MAX_POSTS_PER_KEYWORD, INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)

COOKIES_TXT = "instagram_cookies.txt"

SEARCH_MAP = {
    "Luka + Anamaria": ["luka anamaria", "luka anamaria goltes"],
    "Luka + Madelyn":  ["luka madelyn", "luka madelyn cline"],
    "Anamaria Solo":   ["anamaria goltes", "anamaria luka"],
    "Madelyn Solo":    ["madelyn cline luka", "madelyn cline doncic"],
    "Luka Custody":    ["luka doncic custody", "luka doncic kids"],
    "Luka Breakup":    ["luka doncic breakup", "luka doncic split"],
    "Luka Handle":     ["luka doncic", "luka7doncic"],
}

def parse_cookies_txt(filepath):
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
                    "name": name, "value": value,
                    "domain": domain.lstrip("."), "path": path,
                    "secure": secure.upper() == "TRUE", "sameSite": "Lax"
                })
        print(f"[Instagram] Parsed {len(cookies)} cookies.")
        return cookies
    except Exception as e:
        print(f"[Instagram] Error parsing cookies: {e}")
        return []

async def check_logged_in(page):
    await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=60000)
    await page.wait_for_timeout(4000)
    return "login" not in page.url and "accounts" not in page.url

async def dismiss_all_popups(page):
    await page.wait_for_timeout(2000)
    for btn_text in ["Not now", "Not Now", "Skip", "Cancel", "Later", "Close"]:
        for selector in [
            f'button:has-text("{btn_text}")',
            f'a:has-text("{btn_text}")',
            f'div[role="button"]:has-text("{btn_text}")',
        ]:
            try:
                btn = await page.query_selector(selector)
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass
    await page.wait_for_timeout(1000)

async def burner_login(page):
    print("[Instagram] Logging in with burner account...")
    try:
        await page.goto("https://www.instagram.com/accounts/login/",
                        wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(6000)

        await page.evaluate(f"""
            () => {{
                const input = document.querySelector('input[name="username"]')
                    || document.querySelector('input[type="text"]');
                if (input) {{
                    input.focus();
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, '{INSTAGRAM_USERNAME}');
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            }}
        """)
        await page.wait_for_timeout(800)
        await page.evaluate(f"""
            () => {{
                const input = document.querySelector('input[name="password"]')
                    || document.querySelector('input[type="password"]');
                if (input) {{
                    input.focus();
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, '{INSTAGRAM_PASSWORD}');
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            }}
        """)
        await page.wait_for_timeout(800)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(10000)

        # Dismiss all popups — run 3 times to catch sequential ones
        await dismiss_all_popups(page)
        await dismiss_all_popups(page)
        await dismiss_all_popups(page)

        if "login" not in page.url and "accounts" not in page.url:
            print("[Instagram] Burner login successful!")
            return True
        print("[Instagram] Burner login failed.")
        return False

    except Exception as e:
        print(f"[Instagram] Burner login error: {e}")
        return False

async def scrape_keyword_search(page, search_term, label):
    """Navigate directly to keyword search URL — same as pressing Enter in search bar."""
    collected = set()
    encoded = search_term.replace(" ", "%20")
    url = f"https://www.instagram.com/explore/search/keyword/?q={encoded}"

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(5000)

        if "login" in page.url or "accounts" in page.url:
            print(f"[Instagram] Redirected to login on '{search_term}'")
            return collected, True  # needs reauth

        await dismiss_all_popups(page)

        scroll_attempts = 0
        while len(collected) < MAX_POSTS_PER_KEYWORD and scroll_attempts < 10:
            # Collect all post and reel links
            links = await page.eval_on_selector_all(
                'a[href*="/p/"], a[href*="/reel/"]',
                'els => els.map(e => e.href)'
            )
            for link in links:
                if "/p/" in link or "/reel/" in link:
                    collected.add(link.split("?")[0])

            await page.evaluate("window.scrollBy(0, 1500)")
            await page.wait_for_timeout(2500)
            scroll_attempts += 1

        print(f"[Instagram] '{search_term}' → {len(collected)} posts found")
        return collected, False

    except Exception as e:
        print(f"[Instagram] Error on '{search_term}': {e}")
        return collected, False

async def run_scrape(page):
    total_saved = 0
    all_queries = BOOLEAN_QUERIES + INDIVIDUAL_QUERIES
    seen_terms = set()

    for query in all_queries:
        label = query["label"]
        all_collected = set()

        for term in SEARCH_MAP.get(label, []):
            if term in seen_terms:
                continue
            seen_terms.add(term)

            results, needs_reauth = await scrape_keyword_search(page, term, label)
            if needs_reauth:
                return total_saved, True
            all_collected.update(results)

        saved = 0
        for url in list(all_collected)[:MAX_POSTS_PER_KEYWORD]:
            save_post("instagram", url, label, datetime.utcnow().isoformat())
            saved += 1
        total_saved += saved
        print(f"[Instagram] '{label}' → {saved} posts saved")

    return total_saved, False

async def scrape_instagram():
    print("[Instagram] Starting scrape...")

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
        page = await context.new_page()
        logged_in = False

        # Try cookies first
        if os.path.exists(COOKIES_TXT):
            cookies = parse_cookies_txt(COOKIES_TXT)
            if cookies:
                await context.add_cookies(cookies)
                logged_in = await check_logged_in(page)
                if logged_in:
                    print("[Instagram] Cookies valid.")
                    await dismiss_all_popups(page)
                else:
                    print("[Instagram] Cookies failed — trying burner login.")

        if not logged_in:
            logged_in = await burner_login(page)

        if not logged_in:
            print("[Instagram] Could not log in. Skipping.")
            await browser.close()
            return

        total, needs_reauth = await run_scrape(page)

        if needs_reauth:
            print("[Instagram] Session dropped — retrying with burner login...")
            logged_in = await burner_login(page)
            if logged_in:
                total, _ = await run_scrape(page)

        print(f"[Instagram] Done. Total posts saved: {total}")
        await browser.close()

def run():
    asyncio.run(scrape_instagram())

if __name__ == "__main__":
    run()
