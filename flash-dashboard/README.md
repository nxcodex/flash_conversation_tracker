# Flash Check Dashboard

Private intelligence dashboard for social media discourse monitoring.

## Setup

### 1. Create the GitHub repo

1. Go to github.com → New repository
2. Name it `flash-dashboard` (or anything you like)
3. Set it to **Private**
4. Don't initialize with README

### 2. Push these files

```bash
cd flash-dashboard
git init
git add .
git commit -m "Initial dashboard"
git remote add origin https://github.com/YOUR_USERNAME/flash-dashboard.git
git push -u origin main
```

### 3. Enable GitHub Pages

1. Go to your repo → Settings → Pages
2. Source: **Deploy from a branch**
3. Branch: `main` / `/ (root)`
4. Save — your dashboard will be live at `https://YOUR_USERNAME.github.io/flash-dashboard/`

### 4. Set your password

1. Go to https://emn178.github.io/online-tools/sha256.html
2. Type your password → copy the hash
3. Open `index.html`, find `const PASSWORD_HASH = '';`
4. Paste your hash between the quotes
5. Commit and push

Leave `PASSWORD_HASH` empty to disable the gate (open access).

---

## Workflow

### After each flash check run

```bash
# From your discourse-tracker folder:
python3 triage.py
```

This will:
- Archive reports older than 7 days
- Remove reports with outdated topics
- Copy the latest valid report to `dashboard/latest.json`

Then commit and push `dashboard/latest.json` to update the live dashboard:

```bash
cd flash-dashboard
git add dashboard/latest.json
git commit -m "Update latest report"
git push
```

### Dry run (preview without changes)

```bash
python3 triage.py --dry-run
```

---

## File Structure

```
flash-dashboard/
├── index.html              ← Dashboard (GitHub Pages serves this)
├── dashboard/
│   └── latest.json         ← Current report (commit this after each run)
├── triage.py               ← Report cleaner — run after flash_check.py
└── README.md
```

---

## Adjusting triage settings

Open `triage.py` and edit the constants at the top:

```python
ARCHIVE_AFTER_DAYS = 7   # How old before archiving
```

Topic matching pulls automatically from `FLASH_TOPICS` in `flash_check.py`.
