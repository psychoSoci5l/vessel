#!/usr/bin/env python3
"""
AI Monitor — digest giornaliero notizie AI per Vessel Pi.
Fonti: HackerNews (filtro AI), r/LocalLLaMA, GitHub releases (ollama).
Nanobot version check via PyPI. Output in italiano, invia su Discord.
Cron: 30 6 * * *
"""
import glob as _glob
import urllib.request
import xml.etree.ElementTree as ET
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1474119098509295716/7GgZomfhrub5615WUjYf1IS2q7TsLfbGGK0qJip0fE6HVzy8Bm0bw8RS9OeHoLN8GTOI"
AI_MONITOR_LOG = Path.home() / ".nanobot" / "ai_monitor_log.jsonl"
HEADERS = {"User-Agent": "Vessel-AI-Monitor/1.0"}


def _fetch_url(url: str, timeout: int = 10) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:
        print(f"  Errore fetch {url[:60]}: {e}")
        return None


# ── HackerNews filtrato AI ──────────────────────────────────────────────────
def fetch_hn_ai(count: int = 8) -> list[dict]:
    keywords = "AI+OR+LLM+OR+GPT+OR+Claude+OR+Anthropic+OR+OpenAI+OR+DeepSeek+OR+Mistral+OR+Gemini+OR+Llama+OR+transformer+OR+diffusion"
    url = f"https://hnrss.org/newest?q={keywords}&count={count}&points=50"
    data = _fetch_url(url)
    if not data:
        return []
    try:
        root = ET.fromstring(data)
        stories = []
        for item in root.findall(".//item")[:count]:
            t = item.find("title")
            l = item.find("link")
            if t is not None and l is not None:
                stories.append({"title": t.text, "link": l.text})
        return stories
    except Exception as e:
        print(f"  HN parse error: {e}")
        return []


# ── Reddit r/LocalLLaMA ─────────────────────────────────────────────────────
def fetch_localllama(count: int = 5) -> list[dict]:
    url = f"https://www.reddit.com/r/LocalLLaMA/hot.json?limit={count + 2}&raw_json=1"
    data = _fetch_url(url)
    if not data:
        return []
    try:
        obj = json.loads(data)
        posts = []
        for child in obj.get("data", {}).get("children", []):
            d = child.get("data", {})
            if d.get("stickied"):
                continue
            posts.append({
                "title": d.get("title", ""),
                "link": f"https://reddit.com{d.get('permalink', '')}",
                "score": d.get("score", 0),
            })
        return posts[:count]
    except Exception as e:
        print(f"  Reddit parse error: {e}")
        return []


# ── GitHub releases ──────────────────────────────────────────────────────────
def fetch_github_release(owner: str, repo: str) -> dict | None:
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    data = _fetch_url(url)
    if not data:
        return None
    try:
        obj = json.loads(data)
        pub = obj.get("published_at", "")
        if pub:
            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            if datetime.now(pub_dt.tzinfo) - pub_dt > timedelta(days=7):
                return None
        return {
            "tag": obj.get("tag_name", ""),
            "name": obj.get("name", ""),
            "url": obj.get("html_url", ""),
            "published": pub[:10] if pub else "",
        }
    except Exception as e:
        print(f"  GitHub release error ({owner}/{repo}): {e}")
        return None


# ── Nanobot version check (PyPI) ────────────────────────────────────────────
def check_nanobot_version() -> dict | None:
    url = "https://pypi.org/pypi/nanobot-ai/json"
    data = _fetch_url(url, timeout=5)
    if not data:
        return None
    try:
        obj = json.loads(data)
        latest = obj.get("info", {}).get("version", "")
        # Cerca versione installata da dist-info (qualsiasi versione)
        installed = ""
        pattern = str(Path.home() / ".local" / "lib" / "python3.*" / "site-packages" / "nanobot_ai-*.dist-info" / "METADATA")
        for meta_path in _glob.glob(pattern):
            with open(meta_path) as f:
                for line in f:
                    if line.startswith("Version:"):
                        installed = line.split(":", 1)[1].strip()
                        break
            if installed:
                break
        if not installed:
            installed = "0.1.4"
        if latest and latest != installed:
            return {"installed": installed, "latest": latest}
        return None
    except Exception:
        return None


# ── Output ──────────────────────────────────────────────────────────────────
def send_to_discord(message: str):
    try:
        payload = json.dumps({"content": message[:2000]}).encode("utf-8")
        req = urllib.request.Request(
            DISCORD_WEBHOOK, data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "curl/7.64.1"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"Discord error: {e}")


def save_log(digest: str, hn: list, reddit: list, releases: list, nanobot_update: dict | None):
    entry = json.dumps({
        "ts": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "hn_ai": hn,
        "localllama": reddit,
        "releases": releases,
        "nanobot_update": nanobot_update,
        "text": digest,
    }, ensure_ascii=False)
    with open(AI_MONITOR_LOG, "a", encoding="utf-8") as f:
        f.write(entry + "\n")


def main():
    now = datetime.now()

    hn = fetch_hn_ai()
    reddit = fetch_localllama()

    releases = []
    for owner, repo, label in [("ollama", "ollama", "Ollama")]:
        rel = fetch_github_release(owner, repo)
        if rel:
            rel["label"] = label
            releases.append(rel)

    nanobot_update = check_nanobot_version()

    # ── Componi digest ──
    lines = [f"[AI MONITOR] {now.strftime('%d/%m/%Y %H:%M')}"]

    if nanobot_update:
        lines.append(f"\n**Nanobot update**: v{nanobot_update['installed']} -> v{nanobot_update['latest']}")

    if releases:
        lines.append("\n**Release recenti**")
        for r in releases:
            lines.append(f"  {r['label']} **{r['tag']}** ({r['published']})")

    if hn:
        lines.append("\n**AI su HackerNews**")
        for i, s in enumerate(hn[:6], 1):
            lines.append(f"{i}. {s['title']}")
            lines.append(f"   {s['link']}")

    if reddit:
        lines.append("\n**r/LocalLLaMA**")
        for i, p in enumerate(reddit, 1):
            score = f" (+{p['score']})" if p.get("score") else ""
            lines.append(f"{i}. {p['title']}{score}")

    if not hn and not reddit and not releases and not nanobot_update:
        lines.append("\nNessuna novita oggi.")

    digest = "\n".join(lines)
    print(digest, file=sys.stderr)
    save_log(digest, hn, reddit, releases, nanobot_update)
    send_to_discord(digest)


if __name__ == "__main__":
    main()
