# export_to_sheets.py — Exports all reports to Google Sheets

import json
import glob
import os
from datetime import datetime

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("[Export] Installing required packages...")
    os.system("pip3 install gspread google-auth")
    import gspread
    from google.oauth2.service_account import Credentials

# ── Config ────────────────────────────────────────────────────────────────────
SPREADSHEET_ID = "1Z-DOJEpNpLW0igjL9fBJp--5APtYGMsg7l5u9Susrz0"
CREDENTIALS_FILE = "credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# ── Helpers ───────────────────────────────────────────────────────────────────
def connect():
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)

def get_or_create_sheet(spreadsheet, title, headers):
    try:
        ws = spreadsheet.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = spreadsheet.add_worksheet(title=title, rows=1000, cols=20)
        ws.append_row(headers, value_input_option="RAW")
        # Bold the header row
        ws.format("1:1", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.1, "green": 0.1, "blue": 0.18}
        })
    return ws

def load_reports():
    files = sorted(glob.glob("reports/report_*.json"))
    reports = []
    for f in files:
        with open(f) as fp:
            try:
                reports.append(json.load(fp))
            except Exception as e:
                print(f"[Export] Skipping {f}: {e}")
    return reports

# ── Sheet builders ────────────────────────────────────────────────────────────
def build_summary(spreadsheet, reports):
    ws = get_or_create_sheet(spreadsheet, "📊 Summary", [
        "Run Timestamp", "Total Posts", "Volume Spikes", "Themes Found", "Entities Found"
    ])
    existing = ws.get_all_values()
    existing_timestamps = {row[0] for row in existing[1:]}

    rows = []
    for r in reports:
        ts = r.get("timestamp", "")[:19].replace("T", " ")
        if ts in existing_timestamps:
            continue
        rows.append([
            ts,
            r.get("total_posts_collected", 0),
            len(r.get("volume_spikes", [])),
            len(r.get("themes", [])),
            len(r.get("entities", []))
        ])

    if rows:
        ws.append_rows(rows, value_input_option="RAW")
    print(f"[Export] Summary → {len(rows)} new rows added")

def build_volume_spikes(spreadsheet, reports):
    ws = get_or_create_sheet(spreadsheet, "📈 Volume Spikes", [
        "Run Timestamp", "Query", "Platform", "Post Count", "Spike Level"
    ])
    existing = ws.get_all_values()
    existing_keys = {(row[0], row[1], row[2]) for row in existing[1:]}

    rows = []
    for r in reports:
        ts = r.get("timestamp", "")[:19].replace("T", " ")
        for spike in r.get("volume_spikes", []):
            key = (ts, spike.get("query", ""), spike.get("platform", ""))
            if key in existing_keys:
                continue
            rows.append([
                ts,
                spike.get("query", ""),
                spike.get("platform", "").upper(),
                spike.get("count", 0),
                spike.get("spike_level", "").upper()
            ])

    if rows:
        ws.append_rows(rows, value_input_option="RAW")
    print(f"[Export] Volume Spikes → {len(rows)} new rows added")

def build_themes(spreadsheet, reports):
    ws = get_or_create_sheet(spreadsheet, "💡 Themes", [
        "Run Timestamp", "Theme", "Description", "Query", "Platforms"
    ])
    existing = ws.get_all_values()
    existing_keys = {(row[0], row[1]) for row in existing[1:]}

    rows = []
    for r in reports:
        ts = r.get("timestamp", "")[:19].replace("T", " ")
        for theme in r.get("themes", []):
            key = (ts, theme.get("theme", ""))
            if key in existing_keys:
                continue
            rows.append([
                ts,
                theme.get("theme", ""),
                theme.get("description", ""),
                theme.get("query", ""),
                ", ".join(theme.get("platforms", []))
            ])

    if rows:
        ws.append_rows(rows, value_input_option="RAW")
    print(f"[Export] Themes → {len(rows)} new rows added")

def build_entities(spreadsheet, reports):
    ws = get_or_create_sheet(spreadsheet, "🔍 Entities", [
        "Run Timestamp", "Entity Name", "Type", "Context"
    ])
    existing = ws.get_all_values()
    existing_keys = {(row[0], row[1]) for row in existing[1:]}

    rows = []
    for r in reports:
        ts = r.get("timestamp", "")[:19].replace("T", " ")
        for entity in r.get("entities", []):
            key = (ts, entity.get("name", ""))
            if key in existing_keys:
                continue
            rows.append([
                ts,
                entity.get("name", ""),
                entity.get("type", "").upper(),
                entity.get("mention_context", "")
            ])

    if rows:
        ws.append_rows(rows, value_input_option="RAW")
    print(f"[Export] Entities → {len(rows)} new rows added")

def build_post_log(spreadsheet, reports):
    ws = get_or_create_sheet(spreadsheet, "🔗 Post Links", [
        "Run Timestamp", "Platform", "Query", "Post URL"
    ])
    # Pull from database instead of reports
    try:
        import sqlite3
        conn = sqlite3.connect("tracker.db")
        c = conn.cursor()
        c.execute("SELECT timestamp, platform, keyword, url FROM posts ORDER BY timestamp DESC")
        db_rows = c.fetchall()
        conn.close()

        existing = ws.get_all_values()
        existing_urls = {row[3] for row in existing[1:]}

        rows = []
        for row in db_rows:
            if row[3] in existing_urls:
                continue
            ts = row[0][:19].replace("T", " ")
            rows.append([ts, row[1].upper(), row[2], row[3]])

        if rows:
            ws.append_rows(rows, value_input_option="RAW")
        print(f"[Export] Post Links → {len(rows)} new rows added")

    except Exception as e:
        print(f"[Export] Post log error: {e}")

# ── Main ──────────────────────────────────────────────────────────────────────
def run():
    print("\n[Export] Connecting to Google Sheets...")

    if not os.path.exists(CREDENTIALS_FILE):
        print(f"[Export] ERROR: {CREDENTIALS_FILE} not found in this folder.")
        print("[Export] Please add your Google service account credentials file.")
        return

    if not os.path.exists("reports"):
        print("[Export] No reports folder found. Run main.py first to generate reports.")
        return

    reports = load_reports()
    if not reports:
        print("[Export] No report files found yet. Run main.py first.")
        return

    try:
        spreadsheet = connect()
        print(f"[Export] Connected to: {spreadsheet.title}")
        print(f"[Export] Exporting {len(reports)} reports...\n")

        build_summary(spreadsheet, reports)
        build_volume_spikes(spreadsheet, reports)
        build_themes(spreadsheet, reports)
        build_entities(spreadsheet, reports)
        build_post_log(spreadsheet, reports)

        print(f"\n[Export] ✅ Done! View your sheet at:")
        print(f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")

    except Exception as e:
        print(f"[Export] Connection error: {e}")
        print("[Export] Make sure credentials.json is valid and the sheet is shared with your service account.")

if __name__ == "__main__":
    run()
