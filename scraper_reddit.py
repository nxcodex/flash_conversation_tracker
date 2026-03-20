# scraper_reddit.py — Scrapes Reddit using boolean + individual queries

import asyncio
from datetime import datetime
from playwright.async_api import async_playwright
from database import save_post
from config import BOOLEAN_QUERIES, INDIVIDUAL_QUERIES, EXCLUDE_TERMS, MAX_POSTS_PER_KEYWORD

# Reddit search URL template
REDDIT_SEARCH = "https://www.reddit.com/search/?q={query}&sort=new&t=day"

# Subreddits likely to have relevant discourse
TARGET_SUBREDDITS = [
    "nba", "nbacirclejerk", "lakers", "mavericks",
    "celebrities", "entertainment", "Fauxmoi",
    "Dallasmavszone", "WestElm", "PopCultureCelebrity"
]

def is_excluded(text):
    return any(term.lower() in text.lower() for term in EXCLUDE_TERMS)

def has_context(text, keywords):
    return any(kw.lower() in text.lower() for kw in keywords)

async def scrape_query(page, search_string, label, context_keywords):
    # Clean search string for URL
    clean = search_string.replace('"', '').strip()
    encoded = clean.replace(" ", "+")
    search_url = REDDIT_SEARCH.format(query=encoded)
    retries = 3

    while retries > 0:
        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(5000)

            collected = set()
            scroll_attempts = 0

            while len(collected) < MAX_POSTS_PER_KEYWORD and scroll_attempts < 10:
                page_text = await page.inner_text("body")

                # Skip if dominated by basketball content
                if is_excluded(page_text) and not has_context(page_text, context_keywords):
                    await page.evaluate("window.scrollBy(0, 1500)")
                    await page.wait_for_timeout(2000)
                    scroll_attempts += 1
                    continue

                # Collect post links
                links = await page.eval_on_selector_all(
                    'a[href*="/comments/"]',
                    'els => els.map(e => e.href)'
                )
                for link in links:
                    if "/comments/" in link:
                        clean_link = link.split("?")[0]
                        if "reddit.com" in clean_link:
                            collected.add(clean_link)

                await page.evaluate("window.scrollBy(0, 1500)")
                await page.wait_for_timeout(2000)
                scroll_attempts += 1

            for url in list(collected)[:MAX_POSTS_PER_KEYWORD]:
                save_post("reddit", url, label, datetime.utcnow().isoformat())

            print(f"[Reddit] '{label}' → {min(len(collected), MAX_POSTS_PER_KEYWORD)} posts")
            return

        except Exception as e:
            retries -= 1
            if retries > 0:
                print(f"[Reddit] Timeout on '{label}', retrying... ({retries} left)")
                await page.wait_for_timeout(6000)
            else:
                print(f"[Reddit] Skipping '{label}' after 3 failed attempts: {e}")

async def scrape_subreddits(page, context_keywords, label):
    """Also search high-signal subreddits directly"""
    priority_subs = ["Fauxmoi", "entertainment", "celebrities"]

    for sub in priority_subs:
        try:
            url = f"https://www.reddit.com/r/{sub}/search/?q=Luka+Doncic&sort=new&restrict_sr=1&t=week"
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            await page.wait_for_timeout(4000)

            page_text = await page.inner_text("body")

            if not has_context(page_text, context_keywords):
                print(f"[Reddit] r/{sub} — no relevant context found, skipping")
                continue

            links = await page.eval_on_selector_all(
                'a[href*="/comments/"]',
                'els => els.map(e => e.href)'
            )
            count = 0
            for link in links:
                if "/comments/" in link and "reddit.com" in link:
                    clean_link = link.split("?")[0]
                    save_post("reddit", clean_link, label, datetime.utcnow().isoformat())
                    count += 1
                    if count >= 10:
                        break

            print(f"[Reddit] r/{sub} → {count} posts")

        except Exception as e:
            print(f"[Reddit] Error on r/{sub}: {e}")

async def scrape_reddit():
    print("[Reddit] Starting scrape...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        # Run boolean queries
        for query in BOOLEAN_QUERIES:
            await scrape_query(page, query["search_string"], query["label"], query["context_keywords"])

        # Run individual queries
        for query in INDIVIDUAL_QUERIES:
            await scrape_query(page, query["search_string"], query["label"], query["context_keywords"])

        # Also hit high-signal subreddits directly
        combined_keywords = []
        for q in BOOLEAN_QUERIES + INDIVIDUAL_QUERIES:
            combined_keywords.extend(q["context_keywords"])
        await scrape_subreddits(page, list(set(combined_keywords)), "Reddit Subreddit Scan")

        await browser.close()
    print("[Reddit] Done.")

def run():
    asyncio.run(scrape_reddit())

if __name__ == "__main__":
    run()
