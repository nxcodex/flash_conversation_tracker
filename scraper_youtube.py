# scraper_youtube.py — YouTube scraper, no login required

import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
from database import save_post
from config import (BOOLEAN_QUERIES, INDIVIDUAL_QUERIES, EXCLUDE_TERMS, MAX_POSTS_PER_KEYWORD)

SEARCH_MAP = {
    "Luka + Anamaria": ["Luka Doncic Anamaria", "Luka Anamaria Goltes"],
    "Luka + Madelyn":  ["Luka Doncic Madelyn Cline", "Luka Madelyn"],
    "Anamaria Solo":   ["Anamaria Goltes Luka", "Anamaria Goltes"],
    "Madelyn Solo":    ["Madelyn Cline Luka Doncic", "Madelyn Cline dating"],
    "Luka Custody":    ["Luka Doncic custody", "Luka Doncic son custody"],
    "Luka Breakup":    ["Luka Doncic breakup", "Luka Doncic split Anamaria"],
    "Luka Handle":     ["Luka Doncic personal life", "Luka Doncic girlfriend"],
}

# Only collect videos from the past 30 days
FILTER_UPLOAD_DATE = "&sp=EgIIAQ%3D%3D"  # "This month" filter

def is_excluded(text):
    return any(term.lower() in text.lower() for term in EXCLUDE_TERMS)

async def scrape_search(page, search_term, label):
    collected = set()
    encoded = search_term.replace(" ", "+")
    url = f"https://www.youtube.com/results?search_query={encoded}{FILTER_UPLOAD_DATE}"

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=90000)
        await page.wait_for_timeout(5000)

        # Dismiss cookie consent if present
        for btn_text in ["Accept all", "Reject all", "Accept", "I agree"]:
            try:
                btn = await page.query_selector(f'button:has-text("{btn_text}")')
                if btn:
                    await btn.click()
                    await page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        scroll_attempts = 0
        while len(collected) < MAX_POSTS_PER_KEYWORD and scroll_attempts < 8:
            # Get all video links
            links = await page.eval_on_selector_all(
                'a#video-title',
                'els => els.map(e => ({ href: e.href, title: e.title || e.innerText }))'
            )

            for item in links:
                href = item.get("href", "")
                title = item.get("title", "")
                if "/watch?v=" in href:
                    # Filter out pure basketball content by title
                    if not is_excluded(title):
                        collected.add(href.split("&")[0])  # Clean URL

            await page.evaluate("window.scrollBy(0, 2000)")
            await page.wait_for_timeout(2500)
            scroll_attempts += 1

        print(f"[YouTube] '{search_term}' → {len(collected)} videos found")
        return collected

    except Exception as e:
        print(f"[YouTube] Error on '{search_term}': {e}")
        return collected

async def scrape_youtube():
    print("[YouTube] Starting scrape...")

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

        all_queries = BOOLEAN_QUERIES + INDIVIDUAL_QUERIES
        seen_terms = set()

        for query in all_queries:
            label = query["label"]
            all_collected = set()

            for term in SEARCH_MAP.get(label, []):
                if term in seen_terms:
                    continue
                seen_terms.add(term)

                results = await scrape_search(page, term, label)
                all_collected.update(results)

            saved = 0
            for url in list(all_collected)[:MAX_POSTS_PER_KEYWORD]:
                save_post("youtube", url, label, datetime.utcnow().isoformat())
                saved += 1
            print(f"[YouTube] '{label}' → {saved} videos saved")

        await browser.close()
    print("[YouTube] Done.")

def run():
    asyncio.run(scrape_youtube())

if __name__ == "__main__":
    run()
