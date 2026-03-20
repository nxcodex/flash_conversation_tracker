# Platform Scraping Playbook

**Purpose:** Reusable knowledge about scraping each major social media platform. Written from hard-won trial and error. Read this before starting any new scraping project to avoid repeating solved problems.

**Stack assumed:** Python 3, Playwright (Chromium), headless browser unless noted.

**Last updated:** March 2026

---

## X (Twitter)

### Authentication
- **Use cookies.** Export from Chrome using "Get cookies.txt LOCALLY" extension while logged into x.com. Load via `context.add_cookies()`. Cookies last 30–90 days.
- **Automated login is unreliable.** X uses React-rendered inputs. Standard `page.fill()` does not update React state, so the Next button stays disabled. If you must automate login, use the native input value setter:

```javascript
const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value').set;
setter.call(input, 'USERNAME');
input.dispatchEvent(new Event('input', { bubbles: true }));
input.dispatchEvent(new Event('change', { bubbles: true }));
```

- Then click Next/Log in via JavaScript: `document.querySelector('[role="button"]').click()` — but scan all buttons and match by `innerText` since data-testid attributes change frequently.

### Search
- Search URL format: `https://x.com/search?q=QUERY&src=typed_query&f=live&lang=en`
- Add `since:YYYY-MM-DD` to the query string for date filtering.
- URL-encode spaces as `%20` and quotes as `%22`.
- Collect links via `a[href*="/status/"]` selector.
- Strip query parameters: `url.split("?")[0]`

### Bot Detection
- Moderate. Headless browser with a realistic Mac Chrome user-agent works fine for search.
- Do not hammer the search endpoint. Add 3–6 second waits between scrolls.
- If you get rate-limited, wait 10+ minutes before retrying.

### What Doesn't Work
- Scraping without being logged in — X's search wall blocks unauthenticated requests.
- `page.fill()` and `page.type()` for login — React state not updated.

---

## Instagram

### Authentication
- **Use a burner account.** Automate login with a secondary account, not your real account. Bot detection on real accounts is more aggressive and a ban is hard to recover from.
- Cookie export from Chrome does not work reliably — Instagram stores too few cookies (~10–20 vs the 30+ needed).
- **Login automation works** using React-compatible JS input setter (same pattern as X above).
- After login, dismiss **two sequential popups** before the main feed loads:
  1. "Save your login info?" — click "Not Now" (capital N)
  2. "Turn on Notifications" — click "Not Now" (capital N)
  - Run popup dismissal 3 times in a row to catch both.

### Search
- **Keyword search URL is the right approach:**
  `https://www.instagram.com/explore/search/keyword/?q=SEARCH+TERM`
- This is the same URL the browser navigates to when a user types a search and presses Enter. It returns a full grid of posts.
- Do not try to automate the search bar UI — it's finicky and unreliable (terms concatenate, Enter press doesn't register).

### What Doesn't Work
- Hashtag pages (`/explore/tags/TAG/`) — blocked for headless browsers. Returns blank page.
- Search bar automation — terms concatenate without clearing, Enter navigation unreliable.
- Cookie-only auth — insufficient cookies available from Chrome export.
- Headless mode for logged-in browsing — Instagram serves bot-detection page. Use `headless=False` if debugging, headless=True works fine once login is working.

### Notes
- Instagram's search is account-discovery-focused. Multi-word keyword searches ("Luka Doncic Anamaria") return posts that match the combined topic, not just accounts with those names.
- Results are ordered by recency/relevance and include posts from public accounts.

---

## TikTok

### Authentication
- **Use cookies for best results.** Export from Chrome via "Get cookies.txt LOCALLY" while logged into tiktok.com. TikTok stores ~33 cookies.
- Without cookies, keyword search returns 0 results (bot detection strips content).

### Search
- **Hashtag pages work without login:**
  `https://www.tiktok.com/tag/HASHTAG`
- **Keyword search pages are blocked for headless browsers.** `https://www.tiktok.com/search?q=TERM` returns empty content or a bot-detection wall.
- Collect links via `a[href*="/video/"]` selector.

### Limitations
- Niche or multi-word topics often have no hashtag. You will get 0 results for specific query combinations.
- Hashtag searches are blunt — `#lukadoncic` returns all Luka content, not just personal life topics. Apply context keyword filtering after collection.

### User-Agent
- TikTok responds better to a mobile user-agent than desktop:
```python
"Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
```

### What Doesn't Work
- Keyword search pages without cookies — returns 0 results.
- Desktop user-agent — more likely to trigger bot detection.

---

## Threads (Meta)

### Authentication
- Public search works without login for recent posts.
- Login not required for the current implementation.

### Search
- Threads search returns results for recent posts. Works reliably for keyword queries.
- Apply boolean enforcement manually — Threads search does not support boolean operators natively.
- `matches_boolean()` function: check that all terms in a boolean query appear in the page text before saving.

### Notes
- Threads is the most straightforward platform to scrape. Minimal bot detection on public search.
- Content is text-heavy which makes context keyword filtering effective.

---

## Reddit

### Authentication
- **No login required.** Reddit public search is fully accessible.

### Search
- URL format: `https://www.reddit.com/search/?q=QUERY&sort=new&t=day`
- `t=day` restricts to the past 24 hours. Use `t=week` for broader coverage.
- Also search specific subreddits directly:
  - r/Fauxmoi — celebrity gossip
  - r/entertainment — general entertainment
  - r/celebrities — celebrity news
  - Format: `https://www.reddit.com/r/SUBREDDIT/search/?q=QUERY&restrict_sr=1&sort=new`
- Collect links via `a[href*="/comments/"]` selector.

### Notes
- Reddit is the easiest platform to scrape. Zero bot detection on standard search.
- High signal-to-noise ratio for celebrity gossip — the Fauxmoi and entertainment subreddits are well-moderated communities with substantive discussion.
- Comments threads often contain more nuanced discourse than the original post.

### What Doesn't Work
- Nothing significant. Reddit public search is reliable.

---

## YouTube

### Authentication
- **No login required.** YouTube search is fully public.

### Search
- URL format: `https://www.youtube.com/results?search_query=QUERY&sp=EgIIAQ%3D%3D`
- `sp=EgIIAQ%3D%3D` is the "This month" upload date filter. Remove it for all-time results.
- Collect links via `a#video-title` selector, which also exposes the video title for filtering.
- Apply title filtering before saving to exclude pure basketball/sports content.

### Notes
- YouTube search is very clean to scrape. No bot detection for standard browsing.
- Video titles are exposed in the `a#video-title` element — use them for content filtering before storing URLs.
- Comments are not accessible without login and are extremely noisy. Stick to video URLs.

### What Doesn't Work
- Comments without login — requires authenticated API access.
- Live video streams — URLs are different format; filter them out if needed.

---

## General Patterns

### React Input Filling
Most modern social platforms (X, Instagram, TikTok, Threads) use React. Standard Playwright `fill()` and `type()` methods don't update React's internal state, leaving submit buttons disabled. Use this pattern:

```python
await page.evaluate(f"""
    () => {{
        const input = document.querySelector('input[name="username"]');
        if (input) {{
            input.focus();
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, '{USERNAME}');
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
        }}
    }}
""")
```

### Popup Dismissal
Run popup dismissal multiple times in sequence to handle chained popups. Use a list of text variants:

```python
for btn_text in ["Not now", "Not Now", "Skip", "Cancel", "Later"]:
    try:
        btn = await page.query_selector(f'button:has-text("{btn_text}")')
        if btn:
            await btn.click()
            await page.wait_for_timeout(1000)
    except:
        pass
```

### Deduplication
Always use a UNIQUE constraint on the URL column in your database. Let the DB handle deduplication — don't try to do it in Python. Saves complexity and is faster.

### User-Agent
Always set a realistic Mac Chrome user-agent. The default Playwright user-agent is detected by most platforms:

```python
"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
```

Add `--disable-blink-features=AutomationControlled` to Chromium launch args.

### Wait Times
- After page navigation: 4–6 seconds
- After clicking a button: 1–2 seconds
- After login form submission: 8–10 seconds
- Between scrolls: 2.5–3 seconds
- Don't reduce these — platforms detect rapid interactions.

### Debugging
Take screenshots at key steps during login flows. Name them descriptively:
```python
await page.screenshot(path="debug_after_login.png")
```
Upload screenshots to Claude for diagnosis when behavior is unexpected.

### What URL Does a Human See?
When a platform's search behavior is unclear, test it manually. Type the search term as a human would and note the URL the browser navigates to. That URL is often directly navigable by the scraper — saving you the complexity of automating UI interactions.
