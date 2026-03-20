#!/usr/bin/env python3
"""
triage.py — Flash Report Classifier & Cleaner
Keeps your reports/ folder clean and your dashboard's latest.json current.

What it does:
  1. Scans all flash_*.json files in reports/
  2. Archives reports older than ARCHIVE_AFTER_DAYS to reports/archive/
  3. Removes reports whose topics don't match current FLASH_TOPICS
  4. Copies the most recent valid report to dashboard/latest.json
  5. Prints a summary of everything it did

Usage:
    python3 triage.py              # Run triage + update dashboard
    python3 triage.py --dry-run    # Preview changes without touching files
    python3 triage.py --archive-only   # Archive old files, skip topic check
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────

# Archive reports older than this many days
ARCHIVE_AFTER_DAYS = 7

# Where reports live
REPORTS_DIR = Path("reports")
ARCHIVE_DIR = REPORTS_DIR / "archive"

# Where the dashboard reads from
DASHBOARD_DIR = Path("flash-dashboard/dashboard")
LATEST_JSON   = DASHBOARD_DIR / "latest.json"

# Pull current topics from flash_check.py config
# These must match the "label" fields in FLASH_TOPICS
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from flash_check import FLASH_TOPICS
    CURRENT_TOPICS = {t["label"] for t in FLASH_TOPICS}
except ImportError:
    # Fallback — edit this manually if flash_check.py isn't importable
    CURRENT_TOPICS = {"Injunction", "Luka Mother"}

# ── HELPERS ───────────────────────────────────────────────────────────────────

def log(action: str, filename: str, reason: str = ""):
    tag = {
        "ARCHIVE":  "\033[33m[ARCHIVE]\033[0m",
        "DELETE":   "\033[31m[DELETE ]\033[0m",
        "KEEP":     "\033[32m[KEEP   ]\033[0m",
        "UPDATE":   "\033[36m[UPDATE ]\033[0m",
        "SKIP":     "\033[90m[SKIP   ]\033[0m",
        "DRY":      "\033[35m[DRY RUN]\033[0m",
    }.get(action, f"[{action}]")
    reason_str = f"  ← {reason}" if reason else ""
    print(f"  {tag} {filename}{reason_str}")


def parse_report_time(data: dict):
    """Parse run_time from report JSON. Returns UTC-aware datetime or None."""
    rt = data.get("run_time", "")
    if not rt:
        return None
    for fmt in ("%Y-%m-%d %H:%M UTC", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(rt.replace(" UTC", ""), fmt.replace(" UTC", ""))
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def report_topics(data: dict) -> set[str]:
    """Get the set of topic labels in a report."""
    return set(data.get("topics", []) or data.get("analysis", {}).keys())


def is_stale(data: dict) -> bool:
    """True if report is older than ARCHIVE_AFTER_DAYS."""
    dt = parse_report_time(data)
    if not dt:
        return False  # Can't determine age — keep it
    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_AFTER_DAYS)
    return dt < cutoff


def topics_match(data: dict) -> bool:
    """True if report's topics are a subset of current FLASH_TOPICS."""
    report_t = report_topics(data)
    if not report_t:
        return True  # Empty/unknown — don't delete
    return report_t.issubset(CURRENT_TOPICS)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def run_triage(dry_run: bool = False, archive_only: bool = False):
    print(f"\n{'─'*55}")
    print(f"  TRIAGE — {'DRY RUN — ' if dry_run else ''}Flash Report Cleaner")
    print(f"  Current topics: {', '.join(sorted(CURRENT_TOPICS))}")
    print(f"  Archive threshold: {ARCHIVE_AFTER_DAYS} days")
    print(f"{'─'*55}\n")

    if not REPORTS_DIR.exists():
        print("  reports/ folder not found. Nothing to do.\n")
        return

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

    report_files = sorted(REPORTS_DIR.glob("flash_*.json"), reverse=True)

    if not report_files:
        print("  No flash_*.json files found.\n")
        return

    kept     = []
    archived = []
    deleted  = []
    skipped  = []

    for fpath in report_files:
        fname = fpath.name
        try:
            data = json.loads(fpath.read_text())
        except Exception as e:
            log("SKIP", fname, f"could not parse JSON: {e}")
            skipped.append(fname)
            continue

        stale    = is_stale(data)
        mismatch = not topics_match(data) and not archive_only

        if stale:
            archived.append(fpath)
            dest = ARCHIVE_DIR / fname
            log("DRY" if dry_run else "ARCHIVE", fname, f"older than {ARCHIVE_AFTER_DAYS} days")
            if not dry_run:
                shutil.move(str(fpath), str(dest))

        elif mismatch:
            deleted.append(fpath)
            log("DRY" if dry_run else "DELETE", fname, f"topics {report_topics(data)} not in current config")
            if not dry_run:
                fpath.unlink()

        else:
            kept.append(fpath)
            log("KEEP", fname)

    # ── Update dashboard/latest.json ──
    print()
    valid_kept = [f for f in kept if f.exists()]
    if valid_kept:
        latest = valid_kept[0]  # Already sorted newest-first
        log("DRY" if dry_run else "UPDATE", "dashboard/latest.json", f"← {latest.name}")
        if not dry_run:
            shutil.copy(str(latest), str(LATEST_JSON))
    else:
        print("  No valid reports remain — dashboard/latest.json not updated.")
        if LATEST_JSON.exists() and not dry_run:
            print("  Existing latest.json left in place.")

    # ── Summary ──
    print(f"\n{'─'*55}")
    print(f"  Done.")
    print(f"  Kept: {len(kept)}  |  Archived: {len(archived)}  |  Deleted: {len(deleted)}  |  Skipped: {len(skipped)}")
    if dry_run:
        print("  (Dry run — no files were changed)")
    print(f"{'─'*55}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Triage flash check reports")
    parser.add_argument("--dry-run",      action="store_true", help="Preview only, no file changes")
    parser.add_argument("--archive-only", action="store_true", help="Archive old files, skip topic mismatch check")
    args = parser.parse_args()
    run_triage(dry_run=args.dry_run, archive_only=args.archive_only)
