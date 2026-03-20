# main.py — Run this file to start the tracker

import schedule
import time
from datetime import datetime

from database import init_db
from scraper_x import run as run_x
from scraper_tiktok import run as run_tiktok
from scraper_instagram import run as run_instagram
from scraper_threads import run as run_threads
from scraper_reddit import run as run_reddit
from scraper_youtube import run as run_youtube
from analyst import run_analysis
from export_to_sheets import run as run_export
from config import SCRAPE_INTERVAL_MINUTES

def run_all():
    print(f"\n{'='*50}")
    print(f"[Main] Starting cycle — {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*50}")

    run_x()
    run_tiktok()
    run_instagram()
    run_threads()
    run_reddit()
    run_youtube()
    run_analysis()
    run_export()

    print(f"\n[Main] Cycle complete. Next run in {SCRAPE_INTERVAL_MINUTES} minutes.")

if __name__ == "__main__":
    print("="*50)
    print(" Discourse Tracker — Starting Up")
    print(" Tracking: Luka Doncic, Anamaria Goltes, Madelyn Cline")
    print(" Platforms: X, TikTok, Instagram, Threads, Reddit, YouTube")
    print(" Export: Google Sheets (automatic)")
    print("="*50)

    init_db()
    run_all()

    schedule.every(SCRAPE_INTERVAL_MINUTES).minutes.do(run_all)

    print(f"\n[Main] Scheduler running. Press Ctrl+C to stop.\n")

    while True:
        schedule.run_pending()
        time.sleep(30)
