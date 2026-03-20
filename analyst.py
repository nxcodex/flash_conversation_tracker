# analyst.py — Sends collected post data to Claude for analysis

import json
import requests
import os
from datetime import datetime
from database import get_unprocessed_posts, get_recent_post_counts, mark_processed
from config import ANTHROPIC_API_KEY

def run_analysis():
    print("[Analyst] Running analysis...")

    posts = get_unprocessed_posts()
    volume_data = get_recent_post_counts(hours=2)

    if not posts:
        print("[Analyst] No new posts to analyze.")
        return None

    post_lines = [f"- [{p[1].upper()}] query='{p[3]}' url={p[2]}" for p in posts]
    volume_lines = [f"- query='{row[0]}' platform={row[1]} count={row[2]}" for row in volume_data]

    prompt = f"""You are a social media discourse analyst tracking public conversation about Luka Doncic's personal life.

Posts were collected using these queries:
BOOLEAN (both names must appear):
- "Luka Doncic" AND "Anamaria Goltes" — filtered for: custody, child support, breakup
- "Luka Doncic" AND "Madelyn Cline" — filtered for: dating, relationship

INDIVIDUAL (wider net):
- Anamaria Goltes alone
- Madelyn Cline + dating
- Luka Doncic + custody
- Luka Doncic + breakup

Basketball content (fines, game stats, trades) has been filtered out.

COLLECTED POSTS ({len(posts)} total):
{chr(10).join(post_lines)}

VOLUME DATA (last 2 hours):
{chr(10).join(volume_lines)}

Return ONLY a valid JSON object (no markdown, no explanation) with this exact structure:
{{
  "timestamp": "{datetime.utcnow().isoformat()}",
  "total_posts_collected": {len(posts)},
  "volume_spikes": [
    {{
      "query": "...",
      "platform": "...",
      "count": 0,
      "spike_level": "low|medium|high"
    }}
  ],
  "themes": [
    {{
      "theme": "...",
      "description": "...",
      "query": "...",
      "platforms": ["..."]
    }}
  ],
  "entities": [
    {{
      "name": "...",
      "type": "person|brand|event|place",
      "mention_context": "..."
    }}
  ]
}}"""

    try:
        print("[Analyst] Sending to Claude API...")
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )

        # Debug: print full API response if something goes wrong
        result = response.json()
        print(f"[Analyst] API status: {response.status_code}")

        if response.status_code != 200:
            print(f"[Analyst] API error response: {json.dumps(result, indent=2)}")
            return None

        if "content" not in result:
            print(f"[Analyst] Unexpected response structure: {json.dumps(result, indent=2)}")
            return None

        if not result["content"]:
            print("[Analyst] Empty content in response")
            return None

        raw_text = result["content"][0]["text"].strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
        raw_text = raw_text.strip()

        report = json.loads(raw_text)

        os.makedirs("reports", exist_ok=True)
        filename = f"reports/report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w") as f:
            json.dump(report, f, indent=2)

        mark_processed([p[0] for p in posts])

        print(f"[Analyst] Report saved to {filename}")
        print(f"[Analyst] Themes: {len(report.get('themes', []))}")
        print(f"[Analyst] Entities: {len(report.get('entities', []))}")
        print(f"[Analyst] Volume spikes: {len(report.get('volume_spikes', []))}")

        return report

    except json.JSONDecodeError as e:
        print(f"[Analyst] JSON parse error: {e}")
        print(f"[Analyst] Raw text was: {raw_text[:500]}")
        return None
    except Exception as e:
        print(f"[Analyst] Error during analysis: {e}")
        return None

if __name__ == "__main__":
    run_analysis()
