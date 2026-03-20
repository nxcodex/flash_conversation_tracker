# Discourse Tracker — Architecture Decision Log

**Project:** Social media discourse tracker
**Period:** March 2026
**Purpose:** Record of key decisions made during build, including what was tried, what failed, and why final choices were made. Reference this at the start of future similar projects.

---

## ADR-001: Store URLs Only, Not Post Content

**Decision:** The database stores only post URLs (with platform, query label, and timestamp). No post text, images, or metadata is stored locally.

**Rationale:** Post content changes, gets deleted, and raises storage and legal concerns. URLs are stable identifiers. Claude can fetch and analyze content from URLs at analysis time. This keeps the database small and simple — a year of tracking across six platforms would be tens of thousands of rows, still under 10MB as URLs only.

**Trade-off:** Analysis requires a live fetch, so deleted posts can't be analyzed retroactively. Acceptable for this use case.

---

## ADR-002: Cookie-Based Auth for X and TikTok

**Decision:** X and TikTok use manually exported browser cookies for authentication, not automated login.

**Context:** Both X and TikTok have strong bot detection on their login flows. X uses React-rendered inputs that don't respond to standard Playwright `fill()` calls — the Next button stays disabled unless the React state is updated via native JS setter. TikTok's login flow is similarly protected and frequently triggers CAPTCHA.

**What was tried:**
- Standard `page.fill()` — X's Next button stays disabled (React state not updated)
- JavaScript click on buttons — failed because the input state wasn't set correctly
- React-compatible native input setter via `Object.getOwnPropertyDescriptor` — worked for X but still unreliable across sessions
- iframe detection and searching frames for the input — attempted but X doesn't use iframes

**Final solution:** Manual cookie export using the "Get cookies.txt LOCALLY" Chrome extension. User logs in normally in their browser, exports cookies once, and the scraper loads them on each run. Cookies last 30–90 days.

**For future projects:** Always try cookie-based auth first for any platform with aggressive bot detection. It's more reliable than automated login and doesn't risk account flags.

---

## ADR-003: Instagram Uses Burner Account + Keyword Search URL

**Decision:** Instagram uses a burner (secondary) account for login, and navigates directly to `/explore/search/keyword/?q=TERM` for search results.

**Context:** Instagram's search is only available to logged-in users. The scraper cannot use the user's real account because automated login on a real account risks a ban.

**What was tried:**
1. **Cookie export (like X/TikTok)** — Instagram only stores 10–20 cookies in Chrome, far fewer than the 30+ needed. Session didn't persist.
2. **Automated login with React-compatible JS** — Login succeeded but got stuck on sequential popups ("Save your login info?" → "Turn on Notifications"). Case-sensitivity mattered: `"Not now"` vs `"Not Now"` caused failures.
3. **Hashtag pages (`/explore/tags/HASHTAG/`)** — Blocked by Instagram for headless browsers. Returned blank pages.
4. **Instagram native search bar automation** — The scraper was correctly opening the search panel but was: (a) not pressing Enter to execute the search, and (b) concatenating all search terms into the search box without clearing between runs.
5. **Keyword search URL** — Navigating directly to `instagram.com/explore/search/keyword/?q=luka%20anamaria` returns a full grid of relevant posts. This is the same URL the browser navigates to when a user types a search and presses Enter. Works reliably.

**Key insight (from user screenshot):** A human manually typing "luka anamaria" in Instagram search and pressing Enter navigated to the keyword URL and showed a full grid including gossip posts, custody headlines, and couple photos. The scraper just needed to navigate directly to that URL.

**Popup handling:** After login, run popup dismissal three times in a row to catch sequential popups ("Save login info" → "Turn on Notifications"). Both popups must be handled before the explore page loads.

**For future projects:** Instagram keyword search URL is a reliable way to get post-level search results. Check what URL the browser navigates to when you manually search — that URL is often directly navigable.

---

## ADR-004: TikTok Uses Hashtag Pages Only

**Decision:** TikTok scrapes hashtag pages (`/tag/HASHTAG`) rather than keyword search pages.

**Context:** TikTok's search results page (`/search?q=TERM`) returns 0 results for headless browsers — bot detection strips the content. Hashtag pages are public and load normally.

**Trade-off:** Hashtag-based search means some queries return 0 results if no hashtag exists for that topic. "Anamaria Solo," "Madelyn Solo," and "Luka Breakup" return 0 because users don't hashtag those specific topics on TikTok.

**For future projects:** TikTok hashtag pages are the reliable fallback when keyword search is blocked. Accept that niche or multi-word topics won't have matching hashtags.

---

## ADR-005: Reddit Added as Fifth (Now Sixth) Platform

**Decision:** Reddit was added mid-build as an additional platform, with no login required.

**Rationale:** Reddit has rich celebrity/gossip discussion communities (r/Fauxmoi, r/entertainment, r/celebrities) that generate substantial discourse. Reddit's search is fully public — no login, no bot detection, no cookies needed. It was the easiest platform to add and adds significant value for tracking fan discussion.

**Implementation:** Uses `t=day` parameter for recency. Searches all Reddit plus three priority subreddits.

---

## ADR-006: YouTube Added for Video Coverage

**Decision:** YouTube was added as a sixth platform, scraping video links only (not comments), with no login required.

**Rationale:** Celebrity gossip YouTube channels (TMZ, ET, independent creators) are major discourse amplifiers. A gossip channel posting a video about Luka and Madelyn is a high-signal event worth tracking. Comments are too noisy and voluminous to be useful.

**Implementation:** Navigates to YouTube search with "this month" filter (`&sp=EgIIAQ%3D%3D`). Collects `/watch?v=` URLs. Applies `EXCLUDE_TERMS` filter to video titles before saving to avoid basketball content.

**No login needed:** YouTube search is fully public. No cookies, no bot detection for standard search browsing.

---

## ADR-007: Boolean Query Enforcement

**Decision:** Boolean queries require both terms to appear in post content before a URL is saved.

**Context:** Searching for `"Luka Doncic" "Anamaria Goltes"` on some platforms returns posts that mention either name but not both. The `matches_boolean()` function checks that all terms in a boolean query appear in the page text before saving.

**Implementation:** Each scraper has a `matches_boolean()` function that checks `all(term.lower() in text.lower() for term in query["terms"])`.

**Threads** enforces this most strictly — all individual queries also run through context keyword matching.

---

## ADR-008: Architecture Is Scraper → DB → Claude → Sheets, Not Real-Time

**Decision:** The pipeline runs as a batch job on a 60-minute interval, not in real-time.

**Rationale:** Real-time scraping would require persistent browser sessions and much more complex state management. A 60-minute lag is acceptable for discourse tracking — a story breaking at 10am will be in the system by 11am. The batch approach is simpler, more resilient, and easier to debug.

**Trade-off:** Very fast-breaking stories (within the hour) might be missed in the first cycle but will be caught on the next run.

---

## ADR-009: Google Sheets as Primary Output Interface

**Decision:** Google Sheets is used as the main output interface rather than a custom web dashboard.

**Rationale:** The user (Nick) is non-technical and works in Google Workspace. Sheets allows him to filter, sort, and share results without any additional tools. A custom dashboard would require hosting, authentication, and ongoing maintenance.

**Implementation:** Service account auth with `gspread`. Five structured tabs auto-created and overwritten on each cycle.

---

## ADR-010: Single SQLite Database, Not Postgres or Cloud DB

**Decision:** SQLite is used for local storage, not a hosted database.

**Rationale:** This tool runs on one machine (Nick's Mac). There's no need for multi-user access, replication, or cloud hosting. SQLite requires no setup, has zero running cost, and the database file is easily backed up or moved. The UNIQUE constraint on URLs handles deduplication automatically.

**For future projects:** SQLite is fine for any single-machine tool. Only move to Postgres or similar when multiple machines need to write simultaneously or the dataset exceeds ~1GB.
