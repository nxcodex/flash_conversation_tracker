# view_reports.py — Run this to see your latest analysis reports

import json
import os
import glob

def view_latest(n=3):
    reports = sorted(glob.glob("reports/report_*.json"), reverse=True)

    if not reports:
        print("No reports found yet. Run main.py first.")
        return

    print(f"\nShowing {min(n, len(reports))} most recent reports:\n")

    for path in reports[:n]:
        with open(path) as f:
            r = json.load(f)

        print(f"{'='*60}")
        print(f"REPORT: {r.get('timestamp', 'unknown')}")
        print(f"Posts collected: {r.get('total_posts_collected', 0)}")

        print(f"\n--- VOLUME SPIKES ---")
        for spike in r.get("volume_spikes", []):
            print(f"  [{spike['spike_level'].upper()}] {spike['keyword']} on {spike['platform']} — {spike['count']} posts")

        print(f"\n--- THEMES ---")
        for theme in r.get("themes", []):
            print(f"  • {theme['theme']}: {theme['description']}")
            print(f"    Keywords: {', '.join(theme['keywords_involved'])}")
            print(f"    Platforms: {', '.join(theme['platforms'])}")

        print(f"\n--- ENTITIES ---")
        for entity in r.get("entities", []):
            print(f"  • [{entity['type']}] {entity['name']}: {entity['mention_context']}")

        print()

if __name__ == "__main__":
    view_latest()
