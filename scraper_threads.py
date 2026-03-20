# scraper_threads.py — Scrapes Threads with strict boolean keyword enforcement

import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
from database import save_post
from config import BOOLEAN_QUERIES, INDIVIDUAL_QUERIES, EXCLUDE_TERMS, MAX_POSTS_PER_KEYWORD

def is_excluded(text):
    return any(term.lower() in text.lower() for term in EXCLUDE_TERMS)

def has_context(text, keywords):
    return any(kw.lower() in text.lower() for kw in keywords)

def matches_boolean(text, query):
    """For boolean queries, BOTH terms must appear in the post text."""
    if "terms" in query:
        return all(term.lower() in text.lower() for term in query["terms"])
    return has_context(text, query["context_keywords"])

async def scrape_query(page, query, is_boolean=False):
    """Scrape a single query with strict boolean enforcement."""
    label = query["label"]
    context_keywords = query["context_keywords"]

    # Build search term — use first term for boolean, full string for individual
    if is_boolean:
        primary = query["terms"][0]
    else:
        primary = query["search_string"].replace('"', '').strip()

    encoded = primary.replace(" ", "%20")
    search_url = f"https://www.threads.net/search?q={encoded}&serp_type=default"
    retries = 3

    while retries > 0:
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(6000)

            collected = set()
            scroll_attempts = 0

            while len(collected) < MAX_POSTS_PER_KEYWORD and scroll_attempts < 10:
                # Get all post containers to check content per post
                post_texts = await page.eval_on_selector_all(
                    'div[data-pressable-container="true"]',
                    'els => els.map(e => e.innerText)'
                )
                post_links = await page.eval_on_selector_all(
                    'a[href*="/post/"]',
                    'els => els.map(e => e.href)'
                )

                page_text = await page.inner_text("body")

                # Skip entirely if excluded content dominates
                if is_excluded(page_text) and not has_context(page_text, context_keywords):
                    await page.evaluate("window.scrollBy(0, 1500)")
                    await page.wait_for_timeout(3000)
                    scroll_attempts += 1
                    continue

                for link in post_links:
                    if "/post/" in link:
                        clean = link.split("?")[0]
                        # For boolean queries enforce both terms appear on page
                        if is_boolean:
                            if matches_boolean(page_text, query):
                                collected.add(clean)
                        else:
                            if has_context(page_text, context_keywords):
                                collected.add(clean)

                await page.evaluate("window.scrollBy(0, 1500)")
                await page.wait_for_timeout(3000)
                scroll_attempts += 1

            for url in list(collected)[:MAX_POSTS_PER_KEYWORD]:
                save_post("threads", url, label, datetime.utcnow().isoformat())

            print(f"[Threads] '{label}' → {min(len(collected), MAX_POSTS_PER_KEYWORD)} posts")
            return

        except Exception as e:
            retries -= 1
            if retries > 0:
                print(f"[Threads] Timeout on '{label}', retrying... ({retries} left)")
                await page.wait_for_timeout(6000)
            else:
                print(f"[Threads] Skipping '{label}' after 3 failed attempts: {e}")

async def scrape_threads():
    print("[Threads] Starting scrape...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
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

        for query in BOOLEAN_QUERIES:
            await scrape_query(page, query, is_boolean=True)

        for query in INDIVIDUAL_QUERIES:
            await scrape_query(page, query, is_boolean=False)

        await browser.close()
    print("[Threads] Done.")

def run():
    asyncio.run(scrape_threads())

if __name__ == "__main__":
    run()
