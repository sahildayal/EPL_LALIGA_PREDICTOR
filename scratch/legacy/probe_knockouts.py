import requests
import json
from datetime import datetime, timezone

headers = {'User-Agent': 'Mozilla/5.0'}
url_base = 'https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard'
dates = ['20260703', '20260704', '20260705', '20260706', '20260707', '20260708']
all_matches = []

for d in dates:
    try:
        r = requests.get(url_base, params={'dates': d}, headers=headers, timeout=10)
        if r.status_code == 200:
            events = r.json().get('events', [])
            for ev in events:
                comp = ev.get('competitions', [{}])[0]
                competitors = comp.get('competitors', [])
                if len(competitors) < 2:
                    continue
                home = competitors[0].get('team', {}).get('displayName', '')
                away = competitors[1].get('team', {}).get('displayName', '')
                home_score = competitors[0].get('score', '')
                away_score = competitors[1].get('score', '')
                status = ev.get('status', {}).get('type', {}).get('description', '')
                completed = ev.get('status', {}).get('type', {}).get('completed', False)
                # Parse stage info if any
                note = ""
                for note_obj in ev.get('notes', []):
                    note = note_obj.get('text', '')
                all_matches.append({
                    "date": d,
                    "home": home,
                    "away": away,
                    "home_score": home_score,
                    "away_score": away_score,
                    "status": status,
                    "completed": completed,
                    "note": note
                })
    except Exception as e:
        print(f"Error on date {d}: {e}")

print(json.dumps(all_matches, indent=2))
