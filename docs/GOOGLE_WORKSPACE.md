# Google Workspace Integration

Connect Google Calendar, Tasks, and Gmail to Vessel for morning briefings and productivity tracking.

## Overview

Vessel uses a lightweight Python script (`scripts/google_helper.py`) to interact with Google APIs. This is intentionally simple — no heavy MCP servers, no complex middleware. The script uses OAuth2 for authentication and can be called standalone or from the dashboard.

## Prerequisites

- A Google account
- Python 3.11+ with `google-api-python-client` and `google-auth-oauthlib`

```bash
pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
```

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g., "Vessel")
3. Enable these APIs:
   - Google Calendar API
   - Google Tasks API
   - Gmail API (if you want email in briefings)

## Step 2: Create OAuth Credentials

1. Go to **APIs & Services > Credentials**
2. Click **Create Credentials > OAuth client ID**
3. Application type: **Desktop app**
4. Download the JSON file
5. Save it to: `~/.config/google-workspace-mcp/credentials.json`

```bash
mkdir -p ~/.config/google-workspace-mcp/
# Move your downloaded file here
mv ~/Downloads/client_secret_*.json ~/.config/google-workspace-mcp/credentials.json
```

## Step 3: Authorize (first-time only)

Run the helper script — it will open a browser for OAuth consent:

```bash
python3 scripts/google_helper.py calendar today
```

On a headless Pi (no browser), you'll need to:
1. Run the authorization on a machine with a browser
2. Copy the resulting token file to the Pi

The token is saved to: `~/.google_workspace_mcp/credentials/<your-email>.json`

## Step 4: Configure environment

```bash
export GOOGLE_USER_EMAIL=you@gmail.com
export CALENDAR_TIMEZONE=Europe/Rome

# Optional: explicit paths
# export GOOGLE_TOKEN_PATH=~/.google_workspace_mcp/credentials/you@gmail.com.json
# export GOOGLE_CREDS_PATH=~/.config/google-workspace-mcp/credentials.json
```

## Usage

### Calendar

```bash
python3 scripts/google_helper.py calendar today
python3 scripts/google_helper.py calendar tomorrow
python3 scripts/google_helper.py calendar week
python3 scripts/google_helper.py calendar today --json      # Structured output
python3 scripts/google_helper.py calendar search "birthday"  # Search events by name (next 12 months)
python3 scripts/google_helper.py calendar month 10           # All events in October
python3 scripts/google_helper.py calendar add "Meeting" "2026-03-01T10:00" "2026-03-01T11:00"
```

### Tasks

```bash
python3 scripts/google_helper.py tasks list
python3 scripts/google_helper.py tasks add "Buy groceries"
python3 scripts/google_helper.py tasks done TASK_ID
```

### Gmail

```bash
python3 scripts/google_helper.py gmail recent 5
python3 scripts/google_helper.py gmail unread
```

## Morning Briefing Integration

The briefing script (`scripts/briefing.py`) automatically calls google_helper.py for calendar data. Configure it:

```bash
export GOOGLE_HELPER=~/vessel-pi/scripts/google_helper.py
export GOOGLE_PYTHON=python3
```

## Publishing the OAuth App

By default, Google OAuth apps are in "Testing" mode and tokens expire after 7 days. To get permanent tokens:

1. Go to **APIs & Services > OAuth consent screen**
2. Click **Publish App**
3. For personal use, this is sufficient — no review needed

## Token Refresh

The helper script automatically refreshes expired tokens and saves the updated token file. No manual intervention needed.

## Troubleshooting

### "Token has been expired or revoked"
Delete the token file and re-authorize:
```bash
rm ~/.google_workspace_mcp/credentials/you@gmail.com.json
python3 scripts/google_helper.py calendar today
```

### "Access Not Configured" error
Ensure the required APIs are enabled in Google Cloud Console.

### Can't authorize on headless Pi
Run the authorization on a machine with a browser, then SCP the token file:
```bash
scp you@desktop:~/.google_workspace_mcp/credentials/you@gmail.com.json \
    you@vessel.local:~/.google_workspace_mcp/credentials/
```
