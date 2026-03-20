# Discourse Tracker — Setup Guide
### Tracks: Luka Dončić, Annamaria Goltes, Madelyn Cline
### Platforms: TikTok, X, Instagram, Threads

---

## STEP 1 — Install Python

1. Go to https://www.python.org/downloads/
2. Download Python 3.11 or newer
3. During install, **check the box that says "Add Python to PATH"**
4. Click Install

---

## STEP 2 — Open Terminal (Command Prompt)

**Mac:** Press `Cmd + Space`, type `Terminal`, hit Enter
**Windows:** Press `Windows key`, type `cmd`, hit Enter

---

## STEP 3 — Navigate to this folder

Unzip the downloaded folder to your Desktop, then type:

**Mac:**
```
cd ~/Desktop/discourse-tracker
```

**Windows:**
```
cd %USERPROFILE%\Desktop\discourse-tracker
```

---

## STEP 4 — Install dependencies

Copy and paste this exactly:

```
pip install playwright instaloader requests schedule
```

Then:

```
playwright install chromium
```

---

## STEP 5 — Add your Anthropic API Key

Open the file called `config.py` in any text editor (Notepad is fine).

Replace `YOUR_API_KEY_HERE` with your actual key from https://console.anthropic.com

---

## STEP 6 — Run the tracker

```
python main.py
```

The tracker will now run every hour automatically.
Results are saved to the `reports/` folder as JSON files.

---

## Output

Each hourly report looks like this:
```json
{
  "timestamp": "2026-03-10T14:00:00",
  "volume_spikes": [...],
  "themes": [...],
  "entities": [...]
}
```

---

## To stop the tracker
Press `Ctrl + C` in the terminal window.
