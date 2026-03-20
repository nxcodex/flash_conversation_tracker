# Discourse Tracker — Technical README

**Project:** Social media discourse tracker for Luka Dončić personal life coverage
**Built:** March 2026
**Owner:** Nick Mazzucco
**Stack:** Python 3, Playwright, SQLite, Claude API, Google Sheets API

---

## What This Does

Scrapes six social media platforms every 60 minutes for posts related to configured search queries, stores post URLs in a local SQLite database, sends them to Claude for analysis, and exports structured reports to Google Sheets automatically.

---

## File Structure

```
discourse-tracker/
├── discourse-tracker.code-workspace   ← Open this in VS Code
├── main.py                            ← Run this to start everything
├── config.py                          ← All credentials and queries go here
├── database.py                        ← SQLite setup and save functions
├── scraper_x.py                       ← X (Twitter) scraper
├── scraper_tiktok.py                  ← TikTok scraper
├── scraper_instagram.py               ← Instagram scraper
├── scraper_threads.py                 ← Threads scraper
├── scraper_reddit.py                  ← Reddit scraper
├── scraper_youtube.py                 ← YouTube scraper
├── analyst.py                         ← Claude analysis engine
├── export_to_sheets.py                ← Google Sheets export
├── view_reports.py                    ← View latest reports in terminal
├── x_cookies.txt                      ← X auth cookies (export from Chrome)
├── tiktok_cookies.txt                 ← TikTok auth cookies (export from Chrome)
├── credentials.json                   ← Google Sheets service account key
└── tracker.db                         ← SQLite database (auto-created)
```

---

## First-Time Setup

### 1. Install dependencies

```bash
pip3 install playwright instaloader requests schedule gspread google-auth --break-system-packages
python3 -m playwright install chromium
```

### 2. Fill in config.py

Open `config.py` and fill in:

```python
ANTHROPIC_API_KEY = "sk-ant-..."       # From console.anthropic.com
INSTAGRAM_USERNAME = "..."              # Burner account username
INSTAGRAM_PASSWORD = "..."              # Burner account password
TRACK_FROM_DATE = "2026-03-09"         # Date to track posts from
```

### 3. Export cookies for X and TikTok

**X cookies:**
1. Log into x.com in Chrome (your real account)
2. Install the Chrome extension "Get cookies.txt LOCALLY"
3. Click the extension icon while on x.com
4. Export cookies for x.com only
5. Save as `x_cookies.txt` in the discourse-tracker folder

**TikTok cookies:**
1. Log into tiktok.com in Chrome
2. Same extension — export tiktok.com cookies
3. Save as `tiktok_cookies.txt` in the discourse-tracker folder

Cookies expire every 30–90 days. When X or TikTok starts returning 0 results, re-export.

### 4. Set up Google Sheets credentials

1. Go to console.cloud.google.com
2. Create a project → Enable Google Sheets API and Google Drive API
3. Create a Service Account → Download the JSON key
4. Save the JSON key as `credentials.json` in the discourse-tracker folder
5. Open your Google Sheet → Share it with the service account email as Editor

The Spreadsheet ID is already set in config.py:
```
1Z-DOJEpNpLW0igjL9fBJp--5APtYGMsg7l5u9Susrz0
```

### 5. Run the tracker

```bash
cd discourse-tracker
python3 main.py
```

---

## How It Runs

Every 60 minutes, the tracker executes this cycle:

1. **X** — searches configured queries since `TRACK_FROM_DATE`, collects post URLs
2. **TikTok** — searches hashtag pages, collects video URLs
3. **Instagram** — logs in with burner account, navigates to `/explore/search/keyword/?q=TERM`, collects post URLs
4. **Threads** — searches configured queries, enforces boolean matching
5. **Reddit** — searches all Reddit plus priority subreddits (r/Fauxmoi, r/entertainment, r/celebrities)
6. **YouTube** — searches configured queries with "this month" filter, collects video URLs
7. **Analysis** — sends collected URLs to Claude API for theme/spike/entity detection
8. **Export** — writes results to Google Sheets (5 tabs)

---

## Search Queries

Queries are configured in `config.py` in two lists:

**BOOLEAN_QUERIES** — both terms must appear together:
- Luka + Anamaria: `"Luka Doncic" "Anamaria Goltes"`
- Luka + Madelyn: `"Luka Doncic" "Madelyn Cline"`

**INDIVIDUAL_QUERIES** — single subject searches:
- Anamaria Solo
- Madelyn Solo
- Luka Custody
- Luka Breakup
- Luka Handle (`@luka7doncic`)

**EXCLUDE_TERMS** — basketball content is filtered out:
```
fine, NBA fine, technical foul, ejected, points, assists, rebounds,
game, playoff, trade, contract, salary cap, Mavericks, basketball
```

---

## Database

SQLite database saved locally as `tracker.db`.

Schema:
```sql
posts (
  id        INTEGER PRIMARY KEY,
  platform  TEXT,
  url       TEXT UNIQUE,    -- duplicates auto-blocked
  keyword   TEXT,
  timestamp TEXT,
  processed INTEGER DEFAULT 0
)
```

Only URLs are stored — no post content.

---

## Google Sheets Output

Five tabs auto-created and updated after every cycle:

| Tab | Contents |
|-----|----------|
| 📊 Summary | Total posts per platform, last run time |
| 📈 Volume Spikes | Queries with unusual activity (low/medium/high) |
| 💡 Themes | Narrative themes detected across platforms |
| 🔍 Entities | Named entities (people, topics) with context |
| 🔗 Post Links | All collected URLs with platform and query label |

---

## Viewing Reports

In addition to Google Sheets, reports are saved locally as JSON:

```bash
python3 view_reports.py
```

Reports are stored in `reports/report_YYYYMMDD_HHMMSS.json`.

---

## Maintenance

### When X stops returning results
Re-export `x_cookies.txt` from Chrome (logged into x.com).

### When TikTok stops returning results
Re-export `tiktok_cookies.txt` from Chrome (logged into tiktok.com).

### When Instagram login fails
Check that the burner account hasn't been flagged. Try logging in manually at instagram.com to confirm it's active. If locked, create a new burner account and update `config.py`.

### When Google Sheets export fails
Check that `credentials.json` is present and the service account email still has Editor access to the sheet.

### To change what's being tracked
Edit `BOOLEAN_QUERIES` and `INDIVIDUAL_QUERIES` in `config.py`. Also update `SEARCH_MAP` dictionaries in each scraper file to match the new query labels.

### To change the scrape interval
Edit `SCRAPE_INTERVAL_MINUTES` in `config.py`.

---

## To Stop the Tracker

Press `Ctrl+C` in the terminal. The database and all reports are preserved.

---

## Dependencies Summary

| Package | Purpose |
|---------|---------|
| playwright | Browser automation for all scrapers |
| requests | HTTP requests |
| schedule | Run scraper cycle on interval |
| gspread | Google Sheets API |
| google-auth | Google authentication |
