# Deploy & Procedure — picoclaw

## SSH (senza password)
```bash
ssh psychosocial@picoclaw.local
```
Chiave: `C:\Users\Tsune\.ssh\id_ed25519` (ed25519, configurata 2026-02-20)

## Deploy rapido (un comando)
```bash
scp "C:/claude-code/C Claude Codice/Pi Nanobot/nanobot_dashboard_v2.py" psychosocial@picoclaw.local:~/nanobot_dashboard_v2.py && ssh psychosocial@picoclaw.local "cp ~/nanobot_dashboard_v2.py ~/nanobot_dashboard.py && tmux kill-session -t nanobot-dashboard 2>/dev/null; tmux new-session -d -s nanobot-dashboard 'python3.13 ~/nanobot_dashboard.py'"
```

## Verifica
```bash
# Da Windows — HTTP check
curl -s -o /dev/null -w "%{http_code}" http://picoclaw.local:8090
# Deve restituire: 200

# Tmux sessions (redirect su file per Bash tool)
ssh psychosocial@picoclaw.local "tmux ls" > "C:/Users/Tsune/ssh_out.txt" 2>&1
# Poi leggere ssh_out.txt — deve mostrare nanobot-dashboard e nanobot-gateway
```

## NOTA per Claude Code
Il Bash tool NON cattura stdout di SSH. Workaround:
```bash
# NON funziona (output vuoto):
ssh psychosocial@picoclaw.local "tmux ls"

# FUNZIONA (redirect su file + Read tool):
ssh psychosocial@picoclaw.local "tmux ls" > "C:/Users/Tsune/ssh_out.txt" 2>&1
# Poi usare Read tool su C:/Users/Tsune/ssh_out.txt

# FUNZIONA anche: SCP per scaricare file dal Pi
scp psychosocial@picoclaw.local:/path/remoto "C:/Users/Tsune/AppData/Local/Temp/file_locale"

# FUNZIONA: curl da Windows per verificare la dashboard
curl -s http://picoclaw.local:8090 | head -5
```

## Test locale (porta 8091, non tocca la live)
```bash
# Sul Pi:
PORT=8091 python3.13 ~/nanobot_dashboard_v2.py
# Apri: http://picoclaw.local:8091
```

## Comandi utili sul Pi
```bash
# Vedere log dashboard in tempo reale
tmux attach -t nanobot-dashboard

# Riavviare gateway Discord
tmux kill-session -t nanobot-gateway
tmux new-session -d -s nanobot-gateway 'nanobot gateway'

# Vedere config nanobot (struttura)
python3.13 -c "import json; c=json.load(open('/home/psychosocial/.nanobot/config.json')); [print(k) for k in c.keys()]"

# Vedere token usage log
cat ~/.nanobot/usage_dashboard.jsonl
```

## Rollback
```bash
# La versione precedente e' in ~/nanobot_dashboard.py (sovrascritta dal deploy)
# Per sicurezza, fare backup prima di deploy critici:
ssh psychosocial@picoclaw.local "cp ~/nanobot_dashboard.py ~/nanobot_dashboard.py.bak"
```

## Sicurezza (Fase 4)
- **PIN auth**: al primo avvio, aprire la dashboard e impostare il PIN (4-6 cifre)
- **PIN hash**: salvato in `~/.nanobot/dashboard_pin.hash` (SHA-256, permessi 0600)
- **Sessioni**: cookie `vessel_session`, durata 7 giorni, `httponly`, `samesite=lax`
- **Reset PIN da SSH**: `rm ~/.nanobot/dashboard_pin.hash` e riaprire la dashboard per re-setup
- **WebSocket**: richiede cookie auth, rifiuta con codice 4001 se non autenticato
- **`/api/file`**: whitelist rigida (solo MEMORY, HISTORY, QUICKREF, BRIEFING_LOG, USAGE_LOG)
- **Rate limiting**: auth 5/5min, chat 20/min, cron 10/min, reboot 1/5min, file 30/min
- **Security headers**: CSP, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy

---

## Dipendenze Pi
```bash
python3.13 -m pip install fastapi uvicorn --break-system-packages
```

## Servizi attivi
| Servizio | Tipo | Porta | Comando |
|----------|------|-------|---------|
| Dashboard | tmux `nanobot-dashboard` | 8090 | `python3.13 ~/nanobot_dashboard.py` |
| Gateway Discord | tmux `nanobot-gateway` | — | `nanobot gateway` |
| Home Assistant | Docker/systemd | 8123 | (gestito separatamente) |
| Cloudflare Tunnel | systemd | — | `nanobot.psychosoci5l.com` → 8090 |

## Troubleshooting
- **Dashboard non risponde**: `tmux attach -t nanobot-dashboard` per vedere errori
- **WebSocket non connette**: controlla che il server sia attivo, prova hard refresh `Ctrl+Shift+R`
- **Dati Pi tutti N/A**: i comandi Linux (`top`, `free`, `df`) non funzionano — verifica di essere sul Pi
- **Errore JS in console**: probabilmente un `\n` o `{` non escaped nella f-string Python
- **SSH output vuoto nel Bash tool**: usare redirect su file (vedi sezione NOTA sopra)
- **Token widget mostra 0**: verificare che la chat passi da API diretta e non CLI fallback
