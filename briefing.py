#!/usr/bin/env python3
import urllib.request
import xml.etree.ElementTree as ET
import json
import os
from datetime import datetime
from pathlib import Path

HNRSS_URL = "https://hnrss.org/frontpage"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast?latitude=45.4654&longitude=9.1859&current=temperature_2m,weathercode&timezone=Europe/Rome"
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1474119098509295716/7GgZomfhrub5615WUjYf1IS2q7TsLfbGGK0qJip0fE6HVzy8Bm0bw8RS9OeHoLN8GTOI"

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
        codes = {0:'☀️ Sereno',1:'🌤 Poco nuvoloso',2:'⛅ Nuvoloso',3:'☁️ Coperto',
                 51:'🌦 Pioggerella',61:'🌧 Pioggia',71:'🌨 Neve',80:'🌦 Rovesci',95:'⛈ Temporale'}
        return f"Milano: {temp}°C - {codes.get(code, str(code))}"
    except Exception as e:
        print(f"Weather error: {e}")
        return "Meteo non disponibile"

def send_to_discord(message):
    try:
        data = json.dumps({"content": message[:2000]}).encode('utf-8')
        req = urllib.request.Request(DISCORD_WEBHOOK, data=data,
              headers={'Content-Type': 'application/json', 'User-Agent': 'curl/7.64.1'}, method='POST')
        urllib.request.urlopen(req, timeout=10)
        print("✅ Inviato su Discord!")
    except Exception as e:
        print(f"Discord error: {e}")

BRIEFING_LOG = Path.home() / ".nanobot" / "briefing_log.jsonl"

def save_to_log(briefing_text, weather, stories):
    entry = json.dumps({
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "weather": weather,
        "stories": stories,
        "text": briefing_text,
    }, ensure_ascii=False)
    with open(BRIEFING_LOG, "a") as f:
        f.write(entry + "\n")

def main():
    print("⏳ Generating morning briefing...")
    stories = fetch_hn_stories()
    weather = fetch_weather()
    now = datetime.now()
    lines = [
        f"🌅 **MORNING BRIEFING** - {now.strftime('%A %d %B %Y, %H:%M')}",
        f"🌤 {weather}",
        "",
        "📰 **Top Tech News (HackerNews)**"
    ]
    for i, s in enumerate(stories, 1):
        lines.append(f"{i}. {s['title']}\n   🔗 {s['link']}")
    lines.append("\nHave a great day! 🚀")
    briefing = "\n".join(lines)
    print(briefing)
    save_to_log(briefing, weather, stories)
    send_to_discord(briefing)

if __name__ == "__main__":
    main()
