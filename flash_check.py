#!/usr/bin/env python3
"""
flash_check.py — Topic Flash Classifier
Run this for a fast, one-time sweep on specific topics across all six platforms.
No scheduling. No DB cycle. Run → Read → Act.

Usage:
    python3 flash_check.py              # Single run
    python3 flash_check.py --watch      # Run now, wait 6h, run again, compare

Velocity tracking:
  - Every run appends counts to reports/velocity_log.json
  - On each run, deltas vs the previous run are shown in output
  - Cap hits (15/15 on unconstrained platforms) are flagged as high-velocity signals
  - --watch mode runs two snapshots and prints a before/after comparison

Results go to:
  - Terminal (immediate read)
  - reports/flash_YYYYMMDD_HHMMSS.json
  - reports/velocity_log.json (appended, never overwritten)
  - Google Sheets (Flash Check tab)
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import async_playwright

# ── CONFIG ────────────────────────────────────────────────────────────────────

# Topics to classify — edit these for each flash check
FLASH_TOPICS = [
    {
        "label": "Injunction",
        "search_terms": ["Luka Doncic injunction", "Luka injunction"],
        "keywords": ["injunction", "restraining order", "court order", "TRO", "filing", "filed", "legal action"],
    },
    {
        "label": "Luka Mother",
        "search_terms": ["Luka Doncic mother", "Mirjam Poterbin", "Luka mom"],
        "keywords": ["mother", "mom", "mama", "Mirjam", "Poterbin", "family", "parents"],
    },
]

# How many hours back to look
LOOKBACK_HOURS = 24

# Pull these from your existing config.py
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config import (
        ANTHROPIC_API_KEY,
        INSTAGRAM_USERNAME,
        INSTAGRAM_PASSWORD,
        SPREADSHEET_URL,
    )
    SPREADSHEET_ID = SPREADSHEET_URL.split("/d/")[1].split("/")[0]
    GOOGLE_SHEETS_ENABLED = True
except ImportError:
    print("[WARN] config.py not found or missing keys — running without Sheets export")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    INSTAGRAM_USERNAME = ""
    INSTAGRAM_PASSWORD = ""
    SPREADSHEET_ID = ""
    GOOGLE_SHEETS_ENABLED = False

UA_DESKTOP = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
UA_MOBILE  = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"

SINCE_DATE = (datetime.utcnow() - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%d")

# Max posts to collect from platforms that have no date filter
# These return results sorted by recency but cannot be hard-constrained to a time window
UNCONSTRAINED_POST_CAP = 15

# Per-platform constraint labels — shown in output and saved to JSON
PLATFORM_CONSTRAINTS = {
    "X":         {"type": "date-filtered",              "note": f"since:{SINCE_DATE} operator applied"},
    "Reddit":    {"type": "date-filtered",              "note": "t=day parameter applied"},
    "YouTube":   {"type": "period-filtered",            "note": "this-month filter applied (month-level only)"},
    "Threads":   {"type": "recency-ordered (unconstrained)", "note": f"top {UNCONSTRAINED_POST_CAP} results only — no date filter available"},
    "TikTok":    {"type": "recency-ordered (unconstrained)", "note": f"top {UNCONSTRAINED_POST_CAP} results only — no date filter available"},
    "Instagram": {"type": "recency-ordered (unconstrained)", "note": f"top {UNCONSTRAINED_POST_CAP} results only — no date filter available"},
}

collected_urls: list[dict] = []  # {url, platform, topic_label, search_term}

VELOCITY_LOG = "reports/velocity_log.json"
WATCH_INTERVAL_HOURS = 6  # hours between watch-mode snapshots


# ── VELOCITY LOG ──────────────────────────────────────────────────────────────

def load_velocity_log() -> list[dict]:
    """Load all previous run snapshots from the velocity log."""
    Path("reports").mkdir(exist_ok=True)
    if not os.path.exists(VELOCITY_LOG):
        return []
    try:
        with open(VELOCITY_LOG) as f:
            return json.load(f)
    except Exception:
        return []


def build_snapshot(run_time: str) -> dict:
    """Build a count snapshot from collected_urls for this run."""
    snapshot = {"run_time": run_time, "topics": {}}
    for topic in FLASH_TOPICS:
        label = topic["label"]
        snapshot["topics"][label] = {}
        for platform in PLATFORM_CONSTRAINTS:
            count = len([
                u for u in collected_urls
                if u["topic_label"] == label and u["platform"] == platform
            ])
            snapshot["topics"][label][platform] = count
    return snapshot


def append_velocity_log(snapshot: dict):
    """Append this run's snapshot to the velocity log."""
    log_data = load_velocity_log()
    log_data.append(snapshot)
    with open(VELOCITY_LOG, "w") as f:
        json.dump(log_data, f, indent=2)


def compute_deltas(current: dict, previous: dict) -> dict:
    """
    Compare current snapshot to previous. Returns per-topic, per-platform deltas.
    Also flags: cap hits (count == UNCONSTRAINED_POST_CAP on unconstrained platforms).
    """
    UNCONSTRAINED = {p for p, v in PLATFORM_CONSTRAINTS.items() if "unconstrained" in v["type"]}
    deltas = {}
    for topic_label, platforms in current["topics"].items():
        deltas[topic_label] = {}
        prev_platforms = previous.get("topics", {}).get(topic_label, {})
        for platform, count in platforms.items():
            prev_count = prev_platforms.get(platform, 0)
            delta = count - prev_count
            cap_hit = (platform in UNCONSTRAINED and count >= UNCONSTRAINED_POST_CAP)
            deltas[topic_label][platform] = {
                "current": count,
                "previous": prev_count,
                "delta": delta,
                "cap_hit": cap_hit,
                "velocity_alert": delta > 0 or cap_hit,
            }
    return deltas


def check_cap_hits(snapshot: dict) -> dict:
    """
    For a single snapshot (no previous), just flag cap hits on unconstrained platforms.
    Used on first-ever run when there is no prior snapshot to diff against.
    """
    UNCONSTRAINED = {p for p, v in PLATFORM_CONSTRAINTS.items() if "unconstrained" in v["type"]}
    deltas = {}
    for topic_label, platforms in snapshot["topics"].items():
        deltas[topic_label] = {}
        for platform, count in platforms.items():
            cap_hit = (platform in UNCONSTRAINED and count >= UNCONSTRAINED_POST_CAP)
            deltas[topic_label][platform] = {
                "current": count,
                "previous": None,
                "delta": None,
                "cap_hit": cap_hit,
                "velocity_alert": cap_hit,
            }
    return deltas


def print_velocity(deltas: dict, label_a: str = "prev", label_b: str = "now"):
    """Print velocity section to terminal."""
    any_alert = any(
        v["velocity_alert"]
        for topic in deltas.values()
        for v in topic.values()
    )

    print("\n" + "─"*60)
    print(f"  📈 VELOCITY  ({label_a} → {label_b})")
    print("─"*60)

    if not any_alert:
        print("  No velocity alerts. All counts stable or zero.\n")
        return

    for topic_label, platforms in deltas.items():
        topic_alerts = [p for p, v in platforms.items() if v["velocity_alert"]]
        if not topic_alerts:
            continue
        print(f"\n  {topic_label}:")
        for platform, v in platforms.items():
            if not v["velocity_alert"]:
                continue
            parts = []
            if v["cap_hit"]:
                parts.append(f"🔴 CAP HIT ({v['current']}/{UNCONSTRAINED_POST_CAP})")
            if v["delta"] is not None and v["delta"] > 0:
                parts.append(f"↑ +{v['delta']} ({v['previous']} → {v['current']})")
            elif v["delta"] is None and not v["cap_hit"]:
                parts.append(f"  {v['current']} posts (first run — no baseline)")
            flag = "  ".join(parts)
            print(f"    {platform:<12} {flag}")
    print()


def export_velocity_to_sheets(ws_sheet, deltas: dict, run_time: str):
    """Write velocity section to an existing open gspread worksheet."""
    rows = [[], ["VELOCITY DELTAS", run_time]]
    rows.append(["Topic", "Platform", "Previous", "Current", "Delta", "Cap Hit", "Alert"])
    for topic_label, platforms in deltas.items():
        for platform, v in platforms.items():
            rows.append([
                topic_label,
                platform,
                v["previous"] if v["previous"] is not None else "N/A (first run)",
                v["current"],
                v["delta"] if v["delta"] is not None else "N/A",
                "YES" if v["cap_hit"] else "",
                "⚠️ ALERT" if v["velocity_alert"] else "",
            ])
    return rows


# ── HELPERS ───────────────────────────────────────────────────────────────────

def log(platform, msg):
    print(f"[{platform.upper():<10}] {msg}")


def add_url(url: str, platform: str, topic_label: str, search_term: str):
    clean = url.split("?")[0].rstrip("/")
    if any(u["url"] == clean for u in collected_urls):
        return
    collected_urls.append({
        "url": clean,
        "platform": platform,
        "topic_label": topic_label,
        "search_term": search_term,
        "collected_at": datetime.utcnow().isoformat(),
    })


def load_cookies(path: str) -> list[dict] | None:
    if not os.path.exists(path):
        return None
    cookies = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            cookies.append({
                "name":    parts[5],
                "value":   parts[6],
                "domain":  parts[0].lstrip("."),
                "path":    parts[2],
                "secure":  parts[3].upper() == "TRUE",
                "httpOnly": False,
                "sameSite": "Lax",
            })
    return cookies or None


# ── SCRAPERS ──────────────────────────────────────────────────────────────────

async def scrape_x(page, topic):
    for term in topic["search_terms"]:
        query = f"{term} since:{SINCE_DATE}"
        encoded = query.replace(" ", "%20").replace('"', "%22")
        url = f"https://x.com/search?q={encoded}&src=typed_query&f=live&lang=en"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)
            for _ in range(3):
                links = await page.query_selector_all('a[href*="/status/"]')
                for link in links:
                    href = await link.get_attribute("href")
                    if href and "/status/" in href:
                        add_url("https://x.com" + href if href.startswith("/") else href,
                                "X", topic["label"], term)
                await page.evaluate("window.scrollBy(0, 1200)")
                await page.wait_for_timeout(2500)
            log("X", f"  '{term}' → {len([u for u in collected_urls if u['platform']=='X' and u['topic_label']==topic['label']])} urls")
        except Exception as e:
            log("X", f"  Error on '{term}': {e}")


async def scrape_reddit(page, topic):
    subreddits = ["", "r/Fauxmoi", "r/entertainment", "r/celebrities"]
    for term in topic["search_terms"]:
        for sub in subreddits:
            if sub:
                url = f"https://www.reddit.com/{sub}/search/?q={term.replace(' ', '+')}&restrict_sr=1&sort=new&t=day"
            else:
                url = f"https://www.reddit.com/search/?q={term.replace(' ', '+')}&sort=new&t=day"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(3000)
                links = await page.query_selector_all('a[href*="/comments/"]')
                for link in links:
                    href = await link.get_attribute("href")
                    if href and "/comments/" in href:
                        full = "https://www.reddit.com" + href if href.startswith("/") else href
                        add_url(full, "Reddit", topic["label"], term)
            except Exception as e:
                log("Reddit", f"  Error: {e}")
    log("Reddit", f"  {topic['label']} → {len([u for u in collected_urls if u['platform']=='Reddit' and u['topic_label']==topic['label']])} urls")


async def scrape_youtube(page, topic):
    for term in topic["search_terms"]:
        encoded = term.replace(" ", "+")
        url = f"https://www.youtube.com/results?search_query={encoded}&sp=EgIIAQ%3D%3D"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)
            links = await page.query_selector_all("a#video-title")
            for link in links:
                href = await link.get_attribute("href")
                if href and "/watch?v=" in href:
                    add_url("https://www.youtube.com" + href, "YouTube", topic["label"], term)
        except Exception as e:
            log("YouTube", f"  Error: {e}")
    log("YouTube", f"  {topic['label']} → {len([u for u in collected_urls if u['platform']=='YouTube' and u['topic_label']==topic['label']])} urls")


async def scrape_threads(page, topic):
    # UNCONSTRAINED — no date filter available. Capped at UNCONSTRAINED_POST_CAP top results.
    for term in topic["search_terms"]:
        encoded = term.replace(" ", "%20")
        url = f"https://www.threads.net/search?q={encoded}&serp_type=default"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(4000)
            links = await page.query_selector_all('a[href*="/post/"]')
            count = 0
            for link in links:
                if count >= UNCONSTRAINED_POST_CAP:
                    break
                href = await link.get_attribute("href")
                if href:
                    full = "https://www.threads.net" + href if href.startswith("/") else href
                    add_url(full, "Threads", topic["label"], term)
                    count += 1
        except Exception as e:
            log("Threads", f"  Error: {e}")
    total = len([u for u in collected_urls if u['platform']=='Threads' and u['topic_label']==topic['label']])
    log("Threads", f"  {topic['label']} → {total} urls (recency-ordered, capped at {UNCONSTRAINED_POST_CAP})")


async def scrape_tiktok(page, topic):
    # UNCONSTRAINED — no date filter available. Capped at UNCONSTRAINED_POST_CAP top results.
    # TikTok keyword search is blocked for headless; hashtag pages are the reliable fallback.
    hashtags_by_topic = {
        "Injunction":    ["lukadoncic", "lukainjunction", "nbainjunction"],
        "Luka Mother":   ["lukadoncic", "lukamom", "lukafamily"],
    }
    hashtags = hashtags_by_topic.get(topic["label"], [])
    for tag in hashtags:
        url = f"https://www.tiktok.com/tag/{tag}"
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(4000)
            links = await page.query_selector_all('a[href*="/video/"]')
            count = 0
            for link in links:
                if count >= UNCONSTRAINED_POST_CAP:
                    break
                href = await link.get_attribute("href")
                if href:
                    full = "https://www.tiktok.com" + href if href.startswith("/") else href
                    add_url(full, "TikTok", topic["label"], tag)
                    count += 1
        except Exception as e:
            log("TikTok", f"  Error on #{tag}: {e}")
    total = len([u for u in collected_urls if u['platform']=='TikTok' and u['topic_label']==topic['label']])
    log("TikTok", f"  {topic['label']} → {total} urls (recency-ordered, capped at {UNCONSTRAINED_POST_CAP})")


async def scrape_instagram(page, topic):
    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        log("Instagram", "  Skipped — no credentials in config.py")
        return
    try:
        await page.goto("https://www.instagram.com/accounts/login/", wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(4000)
        # React-compatible login
        await page.evaluate(f"""
            () => {{
                const input = document.querySelector('input[name="username"]');
                if (input) {{
                    input.focus();
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, '{INSTAGRAM_USERNAME}');
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
            }}
        """)
        await page.wait_for_timeout(800)
        await page.evaluate(f"""
            () => {{
                const input = document.querySelector('input[name="password"]');
                if (input) {{
                    input.focus();
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, '{INSTAGRAM_PASSWORD}');
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
            }}
        """)
        await page.wait_for_timeout(800)
        await page.evaluate("document.querySelector('button[type=\"submit\"]').click()")
        await page.wait_for_timeout(8000)
        # Dismiss popups
        for _ in range(3):
            for btn_text in ["Not now", "Not Now", "Skip", "Cancel", "Later"]:
                try:
                    btn = await page.query_selector(f'button:has-text("{btn_text}")')
                    if btn:
                        await btn.click()
                        await page.wait_for_timeout(1000)
                except:
                    pass
        # Search by keyword URL — UNCONSTRAINED, capped at UNCONSTRAINED_POST_CAP top results
        for term in topic["search_terms"]:
            encoded = term.replace(" ", "+")
            url = f"https://www.instagram.com/explore/search/keyword/?q={encoded}"
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(5000)
            links = await page.query_selector_all('a[href*="/p/"], a[href*="/reel/"]')
            count = 0
            for link in links:
                if count >= UNCONSTRAINED_POST_CAP:
                    break
                href = await link.get_attribute("href")
                if href:
                    full = "https://www.instagram.com" + href if href.startswith("/") else href
                    add_url(full, "Instagram", topic["label"], term)
                    count += 1
        total = len([u for u in collected_urls if u['platform']=='Instagram' and u['topic_label']==topic['label']])
        log("Instagram", f"  {topic['label']} → {total} urls (recency-ordered, capped at {UNCONSTRAINED_POST_CAP})")
    except Exception as e:
        log("Instagram", f"  Error: {e}")


# ── ANALYSIS ──────────────────────────────────────────────────────────────────

def analyze_with_claude(urls_by_topic: dict) -> dict:
    """Send collected URLs to Claude for classification."""
    import urllib.request

    results = {}

    for topic_label, urls in urls_by_topic.items():
        if not urls:
            results[topic_label] = {
                "verdict": "CLEAR",
                "legal": {"rating": "Clear", "summary": "No URLs collected."},
                "media": {"rating": "Clear", "summary": "No URLs collected."},
                "social_reaction": {"rating": "Clear", "summary": "No URLs collected."},
                "rumor": {"rating": "Clear", "summary": "No URLs collected."},
                "top_findings": [],
                "recommended_action": "No content found. Topic may not be in active circulation.",
            }
            continue

        # Build per-platform constraint summary for the prompt
        constraint_notes = "\n".join(
            f"  - {p}: {v['type']} ({v['note']})"
            for p, v in PLATFORM_CONSTRAINTS.items()
        )

        url_list = "\n".join([f"- [{u['platform']}] {u['url']}" for u in urls[:40]])

        prompt = f"""You are a professional media intelligence analyst. You are conducting a flash threat assessment for a public figure's management team.

TOPIC: "{topic_label}"
LOOKBACK TARGET: Last {LOOKBACK_HOURS} hours
RUN TIME: {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}

PLATFORM CONSTRAINTS — important context for your analysis:
{constraint_notes}

Note: Platforms marked "recency-ordered (unconstrained)" return results sorted by recency but cannot be hard-filtered to a time window. Results from these platforms are capped at {UNCONSTRAINED_POST_CAP} top posts and are assumed to be recent, but may include older content. Flag any URLs that appear to be older based on context clues in the slug, path, or post ID if relevant.

COLLECTED URLS ({len(urls)} total — showing up to 40):
{url_list}

Based on the platforms these URLs come from, the search terms used to find them, and the URL slugs/paths visible in the links, classify this topic across four dimensions. Rate each as: Clear / Watch / Alarm.

Respond ONLY with a JSON object in this exact format:
{{
  "verdict": "CLEAR|WATCH|ALARM",
  "legal": {{
    "rating": "Clear|Watch|Alarm",
    "summary": "2-3 sentences on legal dimension"
  }},
  "media": {{
    "rating": "Clear|Watch|Alarm",
    "summary": "2-3 sentences on media/press pickup"
  }},
  "social_reaction": {{
    "rating": "Clear|Watch|Alarm",
    "summary": "2-3 sentences on fan/public reaction volume and tone"
  }},
  "rumor": {{
    "rating": "Clear|Watch|Alarm",
    "summary": "2-3 sentences on unverified claims or speculation in circulation"
  }},
  "top_findings": [
    "Key finding 1",
    "Key finding 2",
    "Key finding 3"
  ],
  "recency_flags": "Note any URLs that appear potentially older than the lookback window, or 'None detected' if all appear recent.",
  "recommended_action": "One clear sentence on what management should do right now."
}}"""

        try:
            payload = json.dumps({
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            }).encode()

            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                }
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
                raw = data["content"][0]["text"]
                # Strip markdown fences if present
                raw = re.sub(r"```json|```", "", raw).strip()
                results[topic_label] = json.loads(raw)
        except Exception as e:
            print(f"[CLAUDE] Error analyzing {topic_label}: {e}")
            results[topic_label] = {"verdict": "UNKNOWN", "error": str(e)}

    return results


# ── OUTPUT ────────────────────────────────────────────────────────────────────

RATING_ICON = {"Clear": "✅", "Watch": "⚠️", "Alarm": "🚨", "CLEAR": "✅", "WATCH": "⚠️", "ALARM": "🚨", "UNKNOWN": "❓"}


def print_results(results: dict, run_time: str):
    print("\n" + "═" * 60)
    print(f"  FLASH CHECK RESULTS — {run_time}")
    print(f"  Lookback: {LOOKBACK_HOURS}h | URLs collected: {len(collected_urls)}")
    print(f"\n  PLATFORM CONSTRAINTS:")
    for p, v in PLATFORM_CONSTRAINTS.items():
        marker = "📅" if "date-filtered" in v["type"] else "📆" if "period" in v["type"] else "⚠️"
        print(f"  {marker} {p:<12} {v['type']} — {v['note']}")
    print("═" * 60)

    for topic_label, r in results.items():
        verdict = r.get("verdict", "UNKNOWN")
        icon = RATING_ICON.get(verdict, "❓")
        print(f"\n{'─'*60}")
        print(f"  {icon}  TOPIC: {topic_label.upper()}  —  {verdict}")
        print(f"{'─'*60}")

        if "error" in r:
            print(f"  Analysis error: {r['error']}")
            continue

        dims = [("Legal", r.get("legal")), ("Media", r.get("media")),
                ("Social Reaction", r.get("social_reaction")), ("Rumor", r.get("rumor"))]
        for dim_name, dim in dims:
            if dim:
                icon2 = RATING_ICON.get(dim["rating"], "❓")
                print(f"\n  {icon2} {dim_name}: {dim['rating']}")
                print(f"     {dim['summary']}")

        findings = r.get("top_findings", [])
        if findings:
            print(f"\n  📌 Top Findings:")
            for f in findings:
                print(f"     • {f}")

        recency = r.get("recency_flags")
        if recency and recency.lower() != "none detected":
            print(f"\n  🕐 Recency Flags: {recency}")

        action = r.get("recommended_action")
        if action:
            print(f"\n  ▶  ACTION: {action}")

    print(f"\n{'═'*60}\n")


def save_json(results: dict, run_time: str, filename: str, deltas: dict | None = None):
    Path("reports").mkdir(exist_ok=True)
    payload = {
        "run_time": run_time,
        "lookback_hours": LOOKBACK_HOURS,
        "topics": [t["label"] for t in FLASH_TOPICS],
        "platform_constraints": PLATFORM_CONSTRAINTS,
        "total_urls_collected": len(collected_urls),
        "urls": collected_urls,
        "analysis": results,
        "velocity": deltas or {},
    }
    with open(filename, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"[SAVED] {filename}")


def _export_to_sheets_internal(results: dict, run_time: str, deltas: dict | None = None):
    if not GOOGLE_SHEETS_ENABLED or not SPREADSHEET_ID:
        print("[SHEETS] Skipped — not configured")
        return
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SPREADSHEET_ID)

        tab_name = "⚡ Flash Check"
        try:
            ws = sheet.worksheet(tab_name)
            ws.clear()
        except gspread.WorksheetNotFound:
            ws = sheet.add_worksheet(title=tab_name, rows=200, cols=10)

        rows = [["FLASH CHECK", run_time, f"{LOOKBACK_HOURS}h lookback", f"{len(collected_urls)} URLs"]]
        rows.append([])
        rows.append(["PLATFORM CONSTRAINTS"])
        rows.append(["Platform", "Constraint Type", "Note"])
        for p, v in PLATFORM_CONSTRAINTS.items():
            rows.append([p, v["type"], v["note"]])
        rows.append([])
        rows.append(["Topic", "Verdict", "Legal", "Media", "Social Reaction", "Rumor", "Recency Flags", "Recommended Action"])

        for topic_label, r in results.items():
            rows.append([
                topic_label,
                r.get("verdict", "UNKNOWN"),
                r.get("legal", {}).get("rating", ""),
                r.get("media", {}).get("rating", ""),
                r.get("social_reaction", {}).get("rating", ""),
                r.get("rumor", {}).get("rating", ""),
                r.get("recency_flags", ""),
                r.get("recommended_action", ""),
            ])

        rows.append([])
        rows.append(["Platform", "Topic", "URL", "Search Term", "Collected At"])
        for u in collected_urls:
            rows.append([u["platform"], u["topic_label"], u["url"], u["search_term"], u["collected_at"]])

        if deltas:
            rows.extend(export_velocity_to_sheets(ws, deltas, run_time))
        ws.update("A1", rows)
        print(f"[SHEETS] Written to tab '{tab_name}'")
    except Exception as e:
        print(f"[SHEETS] Error: {e}")


def export_to_sheets(results: dict, run_time: str, deltas: dict | None = None):
    _export_to_sheets_internal(results, run_time, deltas)


# ── MAIN ──────────────────────────────────────────────────────────────────────

async def run_single_check(label: str = "") -> tuple[dict, dict, str]:
    """
    Run one complete flash check sweep. Returns (results, deltas, run_time).
    label: optional string shown in terminal header (e.g. "SNAPSHOT 1 OF 2")
    """
    global collected_urls
    collected_urls = []  # Reset for this run

    run_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    json_filename = f"reports/flash_{ts}.json"

    header = f"⚡ FLASH CHECK STARTING"
    if label:
        header += f" — {label}"
    print(f"\n{header} — {run_time}")
    print(f"   Topics: {', '.join(t['label'] for t in FLASH_TOPICS)}")
    print(f"   Lookback: {LOOKBACK_HOURS}h (since {SINCE_DATE})\n")

    x_cookies      = load_cookies("x_cookies.txt")
    tiktok_cookies  = load_cookies("tiktok_cookies.txt")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )

        for topic in FLASH_TOPICS:
            print(f"\n── {topic['label'].upper()} ──")

            ctx = await browser.new_context(user_agent=UA_DESKTOP)
            if x_cookies:
                await ctx.add_cookies(x_cookies)
            page = await ctx.new_page()
            await scrape_x(page, topic)
            await ctx.close()

            ctx = await browser.new_context(user_agent=UA_DESKTOP)
            page = await ctx.new_page()
            await scrape_reddit(page, topic)
            await ctx.close()

            ctx = await browser.new_context(user_agent=UA_DESKTOP)
            page = await ctx.new_page()
            await scrape_youtube(page, topic)
            await ctx.close()

            ctx = await browser.new_context(user_agent=UA_DESKTOP)
            page = await ctx.new_page()
            await scrape_threads(page, topic)
            await ctx.close()

            ctx = await browser.new_context(user_agent=UA_MOBILE)
            if tiktok_cookies:
                await ctx.add_cookies(tiktok_cookies)
            page = await ctx.new_page()
            await scrape_tiktok(page, topic)
            await ctx.close()

            ctx = await browser.new_context(user_agent=UA_DESKTOP)
            page = await ctx.new_page()
            await scrape_instagram(page, topic)
            await ctx.close()

        await browser.close()

    print(f"\n[COLLECTED] {len(collected_urls)} total URLs")

    # Build velocity snapshot and compute deltas vs previous run
    log_history = load_velocity_log()
    snapshot = build_snapshot(run_time)
    if log_history:
        deltas = compute_deltas(snapshot, log_history[-1])
        prev_time = log_history[-1]["run_time"]
    else:
        deltas = check_cap_hits(snapshot)
        prev_time = "first run"
    append_velocity_log(snapshot)

    urls_by_topic = {t["label"]: [] for t in FLASH_TOPICS}
    for u in collected_urls:
        urls_by_topic[u["topic_label"]].append(u)

    print("\n[CLAUDE] Analyzing...")
    results = analyze_with_claude(urls_by_topic)

    print_results(results, run_time)
    print_velocity(deltas, label_a=prev_time, label_b=run_time)
    save_json(results, run_time, json_filename, deltas=deltas)
    export_to_sheets(results, run_time, deltas=deltas)

    return results, deltas, run_time


async def main():
    parser = argparse.ArgumentParser(description="Flash Check — topic classifier")
    parser.add_argument(
        "--watch",
        action="store_true",
        help=f"Run now, wait {WATCH_INTERVAL_HOURS}h, run again, and print comparison"
    )
    args = parser.parse_args()

    if args.watch:
        print(f"\n👁  WATCH MODE — running two snapshots {WATCH_INTERVAL_HOURS}h apart")
        results_a, deltas_a, time_a = await run_single_check(label="SNAPSHOT 1 OF 2")

        wait_seconds = WATCH_INTERVAL_HOURS * 3600
        print(f"\n⏳ Waiting {WATCH_INTERVAL_HOURS}h before second snapshot...")
        print(f"   Next run at approximately {(datetime.utcnow() + timedelta(hours=WATCH_INTERVAL_HOURS)).strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"   Press Ctrl+C to cancel.\n")
        time.sleep(wait_seconds)

        results_b, deltas_b, time_b = await run_single_check(label="SNAPSHOT 2 OF 2")

        # Print a clean watch-mode summary comparing the two snapshots
        log_history = load_velocity_log()
        if len(log_history) >= 2:
            watch_deltas = compute_deltas(log_history[-1], log_history[-2])
            print(f"\n{'═'*60}")
            print(f"  👁  WATCH MODE COMPARISON")
            print_velocity(watch_deltas, label_a=time_a, label_b=time_b)
    else:
        await run_single_check()


if __name__ == "__main__":
    asyncio.run(main())
