# Contributing to Vessel

Thanks for your interest! Vessel is a Raspberry Pi AI dashboard built with FastAPI + SQLite + a modular frontend. Contributions are welcome.

---

## Development Workflow

The project uses a build system. **Never edit `vessel.py` or `nanobot_dashboard_v2.py` directly** — they are compiled artifacts.

```bash
# 1. Clone
git clone https://github.com/psychoSoci5l/vessel-pi.git
cd vessel-pi

# 2. Edit source files
#    Backend  → src/backend/
#    Frontend → src/frontend/

# 3. Build
python build.py
# Output: nanobot_dashboard_v2.py

# 4. Test locally
PORT=8091 python nanobot_dashboard_v2.py
# Open http://localhost:8091
```

---

## Project Structure

```
src/
  backend/
    imports.py          # Python dependencies
    config.py           # constants, env vars, provider config
    database.py         # SQLite (WAL), schema, queries
    providers.py        # Strategy pattern for 5 LLM providers
    services/           # chat, crypto, monitor, telegram, knowledge, tokens, ...
    routes/             # core, ws_handlers, tamagotchi, telegram
    main.py             # FastAPI app, startup, shutdown
  frontend/
    index.html          # HTML template
    css/                # 8 CSS files (design system, dashboard, code, profile, ...)
    js/core/            # 10 JS modules (theme, state, websocket, nav, chat, ...)
    js/widgets/         # 11 widgets (briefing, crypto, knowledge, sigil, tracker, analytics, ...)

build.py                # compiles src/ into a single-file Python app
vessel.py               # public distribution (compiled artifact)
```

---

## Adding a Widget

1. **Backend handler** — add to `src/backend/routes/ws_handlers.py`:
   ```python
   async def handle_my_widget(websocket, msg, ctx):
       data = await bg(db_get_my_data)
       await websocket.send_json({"type": "my_widget", "data": data})

   WS_DISPATCHER["get_my_widget"] = handle_my_widget
   ```

2. **Frontend JS** — create `src/frontend/js/widgets/my-widget.js`:
   ```javascript
   function renderMyWidget(data) { /* update DOM */ }
   ```
   `build.py` includes all `*.js` files automatically.

3. **Frontend CSS** — add to an existing file or create `src/frontend/css/09-my-widget.css`.

4. **HTML placeholder** — add to `src/frontend/index.html` (Profile tab or Drawer).

5. **WebSocket handler** — register in `src/frontend/js/core/02-websocket.js`:
   ```javascript
   else if (msg.type === 'my_widget') { renderMyWidget(msg.data); }
   ```

Widget best practices:
- Heavy widgets use **on-demand loading**: render a placeholder, load only when opened.
- Keep DOM updates minimal — prefer `innerHTML` on a container element.

---

## Adding an LLM Provider

1. Add provider class to `src/backend/providers.py` (extend `BaseProvider`)
2. Register in `PROVIDERS` dict in `src/backend/config.py`
3. Add name/color mapping in `src/frontend/js/widgets/analytics.js`
4. Add prefix handling in `src/backend/services/telegram.py` if applicable

---

## Core Rules

- **Keep it light** — Vessel runs on a Raspberry Pi 4/5. Every dependency has a cost.
- **Don't break the WebSocket** — the real-time system is the backbone. Test WS after any backend change.
- **Security first** — never `shell=True` with user input. Use subprocess argument lists. Validate all inputs.
- **No credentials in source** — use env vars or `~/.nanobot/config.json`. Never commit API keys.
- **Mobile-first** — test at 375px viewport width. The dashboard is used daily on iPhone.
- **Error isolation** — catch exceptions per-widget. One broken widget must not crash the dashboard.

---

## Submitting a PR

1. Fork the repo
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make changes in `src/`, run `python build.py`, test on port 8091
4. Test on a Pi if possible (or at least verify the build succeeds)
5. Submit a pull request against `main`

---

## Reporting Issues

Please include:
- Python version (`python3 --version`)
- Pi model and OS
- Steps to reproduce
- Relevant error output or logs

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
