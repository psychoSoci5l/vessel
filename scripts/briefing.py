#!/usr/bin/env python3
"""
Morning Briefing — Fetches weather, calendar events, and tech news.

Designed to run via cron (e.g. daily at 07:30) or triggered from the dashboard.
Optionally sends the briefing to a Discord webhook.

Configuration via environment variables:
  WEATHER_LAT       Latitude for weather (default: 45.4654 = Milan)
  WEATHER_LON       Longitude for weather (default: 9.1859)
  WEATHER_TIMEZONE  Timezone (default: Europe/Rome)
  WEATHER_CITY      City name in weather output (default: Milan)
  DISCORD_WEBHOOK   Discord webhook URL (empty = skip Discord)
  NANOBOT_DIR       Base config directory (default: ~/.nanobot)
  GOOGLE_HELPER     Path to google_helper.py (default: ~/scripts/google_helper.py)
  GOOGLE_PYTHON     Python binary for Google scripts (default: python3)
"""
import urllib.request
import xml.etree.ElementTree as ET
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

HNRSS_URL = "https://hnrss.org/frontpage"

WEATHER_LAT = os.environ.get("WEATHER_LAT", "45.4654")
WEATHER_LON = os.environ.get("WEATHER_LON", "9.1859")
WEATHER_TZ = os.environ.get("WEATHER_TIMEZONE", "Europe/Rome")
WEATHER_CITY = os.environ.get("WEATHER_CITY", "Milan")
WEATHER_URL = (
    f"https://api.open-meteo.com/v1/forecast?"
    f"latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
    f"&current=temperature_2m,weathercode&timezone={WEATHER_TZ}"
)

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")

NANOBOT_DIR = Path(os.environ.get("NANOBOT_DIR", str(Path.home() / ".nanobot")))
BRIEFING_LOG = NANOBOT_DIR / "briefing_log.jsonl"
GOOGLE_HELPER = Path(os.environ.get("GOOGLE_HELPER", str(Path.home() / "scripts" / "google_helper.py")))
GOOGLE_PYTHON = os.environ.get("GOOGLE_PYTHON", "python3")


def fetch_hn_stories():
    try:
        with urllib.request.urlopen(HNRSS_URL, timeout=10) as r:
            root = ET.fromstring(r.read())
        stories = []
        for item in root.findall('.//item')[:5]:
            t = item.find('title')
            l = item.find('link')
            if t is not None and l is not None:
                stories.append({'title': t.text, 'link': l.text})
        return stories
    except Exception as e:
        print(f"HN error: {e}")
        return []


def fetch_weather():
    try:
        with urllib.request.urlopen(WEATHER_URL, timeout=10) as r:
            data = json.loads(r.read())
        temp = data['current']['temperature_2m']
        code = data['current']['weathercode']
        codes = {
            0: 'Clear', 1: 'Mostly clear', 2: 'Partly cloudy', 3: 'Overcast',
            51: 'Drizzle', 61: 'Rain', 71: 'Snow', 80: 'Showers', 95: 'Thunderstorm',
        }
        return f"{WEATHER_CITY}: {temp}C - {codes.get(code, str(code))}"
    except Exception as e:
        print(f"Weather error: {e}")
        return "Weather unavailable"


def send_to_discord(message):
    if not DISCORD_WEBHOOK:
        return
    try:
        data = json.dumps({"content": message[:2000]}).encode('utf-8')
        req = urllib.request.Request(
            DISCORD_WEBHOOK, data=data,
            headers={'Content-Type': 'application/json', 'User-Agent': 'Vessel-Briefing/1.0'},
            method='POST',
        )
        urllib.request.urlopen(req, timeout=10)
        print("Sent to Discord")
    except Exception as e:
        print(f"Discord error: {e}")


def fetch_calendar_events(period="today"):
    """Call google_helper.py to get calendar events (requires Google OAuth setup)."""
    if not GOOGLE_HELPER.exists():
        return []
    try:
        result = subprocess.run(
            [GOOGLE_PYTHON, str(GOOGLE_HELPER), "calendar", period, "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout.strip())
            return data.get("events", [])
        return []
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        return []


def save_to_log(briefing_text, weather, stories, events_today=None, events_tomorrow=None):
    BRIEFING_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = json.dumps({
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "weather": weather,
        "stories": stories,
        "calendar_today": events_today or [],
        "calendar_tomorrow": events_tomorrow or [],
        "text": briefing_text,
    }, ensure_ascii=False)
    with open(BRIEFING_LOG, "a") as f:
        f.write(entry + "\n")


def main():
    print("Generating morning briefing...")
    stories = fetch_hn_stories()
    weather = fetch_weather()
    events_today = fetch_calendar_events("today")
    events_tomorrow = fetch_calendar_events("tomorrow")
    now = datetime.now()

    lines = [
        f"MORNING BRIEFING - {now.strftime('%A %d %B %Y, %H:%M')}",
        f"{weather}",
        "",
        "Today's calendar",
    ]
    if events_today:
        for e in events_today:
            loc = f" @ {e['location']}" if e.get("location") else ""
            lines.append(f"  {e['time']} - {e['summary']}{loc}")
    else:
        lines.append("  No events today")

    lines.append("")
    lines.append("Top Tech News (HackerNews)")
    for i, s in enumerate(stories, 1):
        lines.append(f"{i}. {s['title']}\n   {s['link']}")

    if events_tomorrow:
        lines.append("")
        lines.append(f"Tomorrow ({len(events_tomorrow)} events)")
        for e in events_tomorrow:
            lines.append(f"  {e['time']} - {e['summary']}")

    lines.append("\nHave a great day!")
    briefing = "\n".join(lines)
    print(briefing)
    save_to_log(briefing, weather, stories, events_today, events_tomorrow)
    send_to_discord(briefing)


if __name__ == "__main__":
    main()
