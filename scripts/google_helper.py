#!/usr/bin/env python3
"""Google Workspace helper — Calendar, Tasks, Gmail via Google API.

Usage:
  python3 google_helper.py calendar [today|tomorrow|week]
  python3 google_helper.py calendar today --json
  python3 google_helper.py calendar add "title" "2026-02-21T10:00" "2026-02-21T11:00"
  python3 google_helper.py tasks [list|add "title"|done TASK_ID]
  python3 google_helper.py gmail [recent N|unread]

Requires Google OAuth credentials. See docs/GOOGLE_WORKSPACE.md for setup.

Environment variables:
  GOOGLE_TOKEN_PATH   Path to OAuth token file (default: ~/.google_workspace_mcp/credentials/<email>.json)
  GOOGLE_CREDS_PATH   Path to client credentials (default: ~/.config/google-workspace-mcp/credentials.json)
  GOOGLE_USER_EMAIL   Google account email (used to find token file)
  CALENDAR_TIMEZONE   Timezone for calendar events (default: Europe/Rome)
"""
import sys, json, os
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

GOOGLE_EMAIL = os.environ.get("GOOGLE_USER_EMAIL", "")
CREDS_PATH = os.environ.get("GOOGLE_CREDS_PATH",
    os.path.expanduser("~/.config/google-workspace-mcp/credentials.json"))
CALENDAR_TZ = os.environ.get("CALENDAR_TIMEZONE", "Europe/Rome")

# Token path: explicit env var > email-based default > error
if os.environ.get("GOOGLE_TOKEN_PATH"):
    TOKEN_PATH = os.environ["GOOGLE_TOKEN_PATH"]
elif GOOGLE_EMAIL:
    TOKEN_PATH = os.path.expanduser(f"~/.google_workspace_mcp/credentials/{GOOGLE_EMAIL}.json")
else:
    # Try to find any token file in the default directory
    _token_dir = os.path.expanduser("~/.google_workspace_mcp/credentials/")
    _tokens = [f for f in os.listdir(_token_dir) if f.endswith(".json")] if os.path.isdir(_token_dir) else []
    TOKEN_PATH = os.path.join(_token_dir, _tokens[0]) if _tokens else ""

def get_creds():
    with open(TOKEN_PATH) as f:
        data = json.load(f)
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes"),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Save refreshed token
        data["token"] = creds.token
        if creds.expiry:
            data["expiry"] = creds.expiry.isoformat()
        with open(TOKEN_PATH, "w") as f:
            json.dump(data, f, indent=2)
    return creds

# --- CALENDAR ---
def _fetch_calendar_events(period="today"):
    """Fetch eventi calendario e ritorna (lista_dict, label)."""
    creds = get_creds()
    service = build("calendar", "v3", credentials=creds)
    now = datetime.now()
    if period == "today":
        t_min = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
        t_max = (now.replace(hour=0, minute=0, second=0) + timedelta(days=1)).isoformat() + "Z"
        label = "today"
    elif period == "tomorrow":
        tom = now + timedelta(days=1)
        t_min = tom.replace(hour=0, minute=0, second=0).isoformat() + "Z"
        t_max = (tom.replace(hour=0, minute=0, second=0) + timedelta(days=1)).isoformat() + "Z"
        label = "tomorrow"
    elif period == "week":
        t_min = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
        t_max = (now.replace(hour=0, minute=0, second=0) + timedelta(days=7)).isoformat() + "Z"
        label = "this week"
    else:
        return [], period

    result = service.events().list(
        calendarId="primary", timeMin=t_min, timeMax=t_max,
        maxResults=20, singleEvents=True, orderBy="startTime"
    ).execute()
    events = []
    for e in result.get("items", []):
        start_raw = e["start"].get("dateTime", e["start"].get("date", ""))
        end_raw = e["end"].get("dateTime", e["end"].get("date", ""))
        time_str = start_raw[11:16] if "T" in start_raw else "all day"
        events.append({
            "summary": e.get("summary", "(untitled)"),
            "start": start_raw,
            "end": end_raw,
            "time": time_str,
            "location": e.get("location", ""),
        })
    return events, label

def calendar_events(period="today"):
    """Output human-readable degli eventi calendario."""
    events, label = _fetch_calendar_events(period)
    if not events:
        print(f"No events {label}.")
        return
    print(f"Events {label} ({len(events)}):")
    for e in events:
        loc = f" @ {e['location']}" if e.get("location") else ""
        print(f"  {e['time']} - {e['summary']}{loc}")

def calendar_events_json(period="today"):
    """Output JSON strutturato degli eventi calendario."""
    events, label = _fetch_calendar_events(period)
    print(json.dumps({"events": events, "label": label, "period": period}, ensure_ascii=False))

def calendar_add(title, start, end):
    creds = get_creds()
    service = build("calendar", "v3", credentials=creds)
    event = {
        "summary": title,
        "start": {"dateTime": start, "timeZone": CALENDAR_TZ},
        "end": {"dateTime": end, "timeZone": CALENDAR_TZ},
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    print(f"Event created: {created.get('summary')} ({created.get('start', {}).get('dateTime', '')})")
    print(f"ID: {created['id']}")

# --- TASKS ---
def tasks_list():
    creds = get_creds()
    service = build("tasks", "v1", credentials=creds)
    lists = service.tasklists().list().execute().get("items", [])
    for tl in lists:
        print(f"Lista: {tl['title']} (ID: {tl['id']})")
        tasks = service.tasks().list(tasklist=tl["id"], showCompleted=False).execute().get("items", [])
        if not tasks:
            print("  (empty)")
        for t in tasks:
            due = t.get("due", "")[:10] if t.get("due") else ""
            due_str = f" [due: {due}]" if due else ""
            print(f"  - {t['title']}{due_str} (ID: {t['id']})")

def tasks_add(title, tasklist_id=None):
    creds = get_creds()
    service = build("tasks", "v1", credentials=creds)
    if not tasklist_id:
        lists = service.tasklists().list().execute().get("items", [])
        tasklist_id = lists[0]["id"] if lists else None
    if not tasklist_id:
        print("Error: no task list found")
        return
    task = service.tasks().insert(tasklist=tasklist_id, body={"title": title}).execute()
    print(f"Task created: {task['title']} (ID: {task['id']})")

def tasks_done(task_id, tasklist_id=None):
    creds = get_creds()
    service = build("tasks", "v1", credentials=creds)
    if not tasklist_id:
        lists = service.tasklists().list().execute().get("items", [])
        tasklist_id = lists[0]["id"] if lists else None
    service.tasks().patch(
        tasklist=tasklist_id, task=task_id, body={"status": "completed"}
    ).execute()
    print(f"Task {task_id} completed.")

# --- GMAIL ---
def gmail_recent(count=5):
    creds = get_creds()
    service = build("gmail", "v1", credentials=creds)
    result = service.users().messages().list(userId="me", maxResults=count, q="in:inbox").execute()
    messages = result.get("messages", [])
    if not messages:
        print("No recent emails.")
        return
    print(f"Recent {len(messages)} emails:")
    for msg in messages:
        detail = service.users().messages().get(userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]).execute()
        headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        frm = headers.get("From", "?")
        subj = headers.get("Subject", "(no subject)")
        date = headers.get("Date", "")[:16]
        print(f"  [{date}] {frm[:40]} — {subj}")

def gmail_unread():
    creds = get_creds()
    service = build("gmail", "v1", credentials=creds)
    result = service.users().messages().list(userId="me", maxResults=10, q="is:unread in:inbox").execute()
    messages = result.get("messages", [])
    if not messages:
        print("No unread emails.")
        return
    print(f"Unread emails ({len(messages)}):")
    for msg in messages:
        detail = service.users().messages().get(userId="me", id=msg["id"], format="metadata",
            metadataHeaders=["From", "Subject"]).execute()
        headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
        print(f"  {headers.get('From', '?')[:40]} — {headers.get('Subject', '(no subject)')}")

# --- MAIN ---
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "calendar":
        sub = sys.argv[2] if len(sys.argv) > 2 else "today"
        if sub == "--json":
            sub = "today"
        if sub == "add":
            if len(sys.argv) < 5:
                print("Usage: google_helper.py calendar add \"title\" \"start\" \"end\"")
                sys.exit(1)
            calendar_add(sys.argv[3], sys.argv[4], sys.argv[5] if len(sys.argv) > 5 else "")
        elif "--json" in sys.argv:
            calendar_events_json(sub)
        else:
            calendar_events(sub)

    elif cmd == "tasks":
        sub = sys.argv[2] if len(sys.argv) > 2 else "list"
        if sub == "list":
            tasks_list()
        elif sub == "add":
            tasks_add(sys.argv[3] if len(sys.argv) > 3 else "New task")
        elif sub == "done":
            tasks_done(sys.argv[3] if len(sys.argv) > 3 else "")
        else:
            print(f"Unknown tasks subcommand: {sub}")

    elif cmd == "gmail":
        sub = sys.argv[2] if len(sys.argv) > 2 else "recent"
        if sub == "recent":
            count = int(sys.argv[3]) if len(sys.argv) > 3 else 5
            gmail_recent(count)
        elif sub == "unread":
            gmail_unread()
        else:
            print(f"Unknown gmail subcommand: {sub}")

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
