# test_instagram_search.py v3 — fixes notification popup + clicks Search icon

import asyncio
import os
from playwright.async_api import async_playwright
from config import INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD

COOKIES_TXT = "instagram_cookies.txt"

TEST_SEARCHES = [
    "Luka Doncic Anamaria",
    "Luka Doncic Madelyn Cline",
    "Anamaria Goltes",
    "Luka Doncic custody",
]

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
        return cookies
    except Exception:
        return []

async def dismiss_all_popups(page):
    """Aggressively dismiss every known Instagram popup."""
    await page.wait_for_timeout(2000)
    # All known dismiss button texts
    for btn_text in ["Not now", "Not Now", "Skip", "Cancel", "Later",
                     "Close", "Dismiss", "No Thanks", "No thanks"]:
        for selector in [
            f'button:has-text("{btn_text}")',
            f'a:has-text("{btn_text}")',
            f'div[role="button"]:has-text("{btn_text}")',
        ]:
            try:
                btn = await page.query_selector(selector)
                if btn:
                    await btn.click()
                    print(f"[Test] Dismissed popup: '{btn_text}'")
                    await page.wait_for_timeout(1500)
            except Exception:
                pass
    await page.wait_for_timeout(1000)

async def test_search():
    print("[Test] Starting Instagram native search test v3...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--no-sandbox"]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900}
        )
        page = await context.new_page()
        logged_in = False

        # Try cookies first
        if os.path.exists(COOKIES_TXT):
            cookies = parse_cookies_txt(COOKIES_TXT)
            if cookies:
                await context.add_cookies(cookies)
                await page.goto("https://www.instagram.com/",
                               wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(5000)
                if "login" not in page.url:
                    print("[Test] Cookies worked!")
                    await dismiss_all_popups(page)
                    logged_in = True

        # Burner login
        if not logged_in:
            print("[Test] Logging in with burner account...")
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

            # Dismiss ALL popups — may be multiple in sequence
            await dismiss_all_popups(page)
            await page.wait_for_timeout(2000)
            await dismiss_all_popups(page)  # Run twice to catch sequential popups
            await page.wait_for_timeout(2000)

            await page.screenshot(path="ig_test_afterlogin.png")
            print(f"[Test] After login URL: {page.url}")

            if "login" not in page.url and "accounts" not in page.url:
                print("[Test] Logged in!")
                logged_in = True
            else:
                print("[Test] Login failed.")
                await browser.close()
                return

        # Now find and click the Search icon in the sidebar
        await page.screenshot(path="ig_test_beforesearch.png")
        print("[Test] Looking for Search icon...")

        search_clicked = False
        # Try multiple ways to find the search icon
        for selector in [
            'a[href="/search/"]',
            'span:has-text("Search")',
            '[aria-label="Search"]',
            'a:has-text("Search")',
        ]:
            try:
                el = await page.wait_for_selector(selector, timeout=5000)
                if el:
                    await el.click()
                    await page.wait_for_timeout(3000)
                    print(f"[Test] Clicked Search via: {selector}")
                    search_clicked = True
                    break
            except Exception:
                continue

        await page.screenshot(path="ig_test_searchpanel.png")
        print(f"[Test] After search click URL: {page.url}")

        if not search_clicked:
            print("[Test] Could not click Search icon — check ig_test_beforesearch.png")
            await browser.close()
            return

        # Find the search input
        search_input = None
        for selector in [
            'input[placeholder="Search"]',
            'input[aria-label="Search input"]',
            'input[placeholder*="earch"]',
            'input[type="text"]',
        ]:
            try:
                el = await page.wait_for_selector(selector, timeout=5000)
                if el:
                    search_input = el
                    print(f"[Test] Found search input via: {selector}")
                    break
            except Exception:
                continue

        if not search_input:
            print("[Test] No search input found — check ig_test_searchpanel.png")
            await browser.close()
            return

        # Test each search term
        for i, term in enumerate(TEST_SEARCHES):
            print(f"\n[Test] Searching: '{term}'")

            await search_input.click()
            await page.wait_for_timeout(500)
            # Clear existing text
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Backspace")
            await page.wait_for_timeout(500)
            await search_input.type(term, delay=80)
            await page.wait_for_timeout(5000)  # Wait for results

            await page.screenshot(path=f"ig_search_{i}_{term.replace(' ', '_')}.png")
            print(f"[Test] Screenshot: ig_search_{i}_{term.replace(' ', '_')}.png")

            # Count what's in results
            all_links = await page.eval_on_selector_all(
                'a', 'els => els.map(e => e.href)'
            )
            post_links = [l for l in all_links if "/p/" in l or "/reel/" in l]
            print(f"[Test] Post/reel links visible: {len(post_links)}")
            if post_links:
                print(f"[Test] Sample: {post_links[:3]}")

        await page.screenshot(path="ig_test_FINAL.png")
        await browser.close()
        print("\n[Test] Done! Upload all ig_search_*.png files to Claude.")

if __name__ == "__main__":
    asyncio.run(test_search())
