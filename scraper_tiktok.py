# scraper_tiktok.py — hashtag-only, no search pages

import asyncio
import os
from datetime import datetime
from playwright.async_api import async_playwright
from database import save_post
from config import (BOOLEAN_QUERIES, INDIVIDUAL_QUERIES, EXCLUDE_TERMS, MAX_POSTS_PER_KEYWORD)

COOKIES_TXT = "tiktok_cookies.txt"

# Hashtags for every query — expanded to cover solo queries properly
HASHTAG_MAP = {
    "Luka + Anamaria": ["lukadoncic", "anamariagoltes", "lukaanamaria"],
    "Luka + Madelyn":  ["lukadoncic", "madelyncline", "lukamadelyn"],
    "Anamaria Solo":   ["anamariagoltes", "anamaria", "annamariagoltes"],
    "Madelyn Solo":    ["madelyncline", "madelynclineandluka"],
    "Luka Custody":    ["lukadoncic", "lukadoncicson", "lukadoncicbaby"],
    "Luka Breakup":    ["lukadoncic", "lukadoncicbreakup", "lukadoncicex"],
    "Luka Handle":     ["luka7doncic", "lukadoncic"],
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
        print(f"[TikTok] Parsed {len(cookies)} cookies.")
        return cookies
    except Exception as e:
        print(f"[TikTok] Error parsing cookies: {e}")
        return []

async def collect_video_links(page):
    collected = set()
    scroll_attempts = 0
    while len(collected) < MAX_POSTS_PER_KEYWORD and scroll_attempts < 15:
        await page.wait_for_timeout(2500)
        all_links = await page.eval_on_selector_all('a', 'els => els.map(e => e.href)')
        for link in all_links:
            if "/video/" in link and "tiktok.com" in link:
                collected.add(link.split("?")[0])
        await page.evaluate("window.scrollBy(0, 2000)")
        scroll_attempts += 1
    return collected

async def scrape_tiktok():
    print("[TikTok] Starting scrape...")

    if not os.path.exists(COOKIES_TXT):
        print(f"[TikTok] ERROR: {COOKIES_TXT} not found.")
        return

    cookies = parse_cookies_txt(COOKIES_TXT)
    if not cookies:
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
        await context.add_cookies(cookies)
        print("[TikTok] Cookies loaded.")

        page = await context.new_page()
        await page.goto("https://www.tiktok.com/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)

        page_text = await page.inner_text("body")
        if "log in" in page_text.lower() and "For You" not in page_text:
            print("[TikTok] Not logged in — re-export cookies from Chrome.")
            await browser.close()
            return
        print("[TikTok] Logged in successfully.")

        all_queries = BOOLEAN_QUERIES + INDIVIDUAL_QUERIES
        seen_tags = set()

        for query in all_queries:
            label = query["label"]
            all_collected = set()

            for tag in HASHTAG_MAP.get(label, []):
                if tag in seen_tags:
                    continue
                seen_tags.add(tag)

                try:
                    await page.goto(f"https://www.tiktok.com/tag/{tag}",
                                   wait_until="domcontentloaded", timeout=90000)
                    await page.wait_for_timeout(5000)

                    if "login" in page.url:
                        print(f"[TikTok] Redirected to login on #{tag} — cookies expired")
                        continue

                    results = await collect_video_links(page)
                    print(f"[TikTok] #{tag} → {len(results)} links")
                    all_collected.update(results)
                except Exception as e:
                    print(f"[TikTok] Error on #{tag}: {e}")
                    continue

            saved = 0
            for url in list(all_collected)[:MAX_POSTS_PER_KEYWORD]:
                save_post("tiktok", url, label, datetime.utcnow().isoformat())
                saved += 1
            print(f"[TikTok] '{label}' → {saved} posts saved")

        await browser.close()
    print("[TikTok] Done.")

def run():
    asyncio.run(scrape_tiktok())

if __name__ == "__main__":
    run()
