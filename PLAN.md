# Fase 50: Dashboard Coherence & Unified Header

## Obiettivo
Coerenza visiva totale tra tutte le pagine (Dashboard, Code, Profile, PIN), header unificato, logout riorganizzato, settings accessibili.

---

## 1. Header Unificato (tutte le tab)

**Attuale**: 3 header diversi — Dashboard (ricco), Code (minimale), Profile (con Logout/Help)

**Nuovo**: Un UNICO header fisso sopra `app-content`, visibile sempre su tutte e 3 le tab.

### Contenuto header unificato:
```
[logo] VESSEL [health-dot] [sigil-indicator] ─── [weather] [temp] · [clock] [gear]
```

### Modifiche:
- **index.html**: Estrarre `dash-header` da dentro `tab-dashboard` e posizionarlo sopra `app-content` (dentro `app-layout`, prima di `app-content`)
- **Rimuovere** `code-header` dal tab Code
- **Rimuovere** `prof-header` dal tab Profile
- **CSS** (`03-dashboard.css`): `.dash-header` diventa `.app-header`, stesso stile
- **CSS** (`04-code.css`): Rimuovere `.code-header` e stili correlati
- **CSS** (`06-profile.css`): Rimuovere `.prof-header` e stili correlati
- **JS** (`08-ui.js`): Il clock aggiorna solo `home-clock` (uno solo, globale). Rimuovere ref a `chat-clock`

---

## 2. Logout -> System Drawer

**Attuale**: Bottone rosso "Logout" nel prof-header

**Nuovo**: Bottone Logout nella riga `sys-actions` del System drawer (accanto a Refresh, Reboot, Off)

### Modifiche:
- **index.html**: Aggiungere `<button class="btn-red" onclick="doLogout()">&#x23FB; Logout</button>` nella riga `sys-actions`
- La funzione `doLogout()` in `08-ui.js` resta invariata
- Ordine bottoni: `Refresh | Logout | Reboot | Off`

---

## 3. PIN Screen — Coerenza con Dashboard + Temi

**Attuale**: CSS hardcoded Terminal Green, nessun supporto temi, Sigil face con colori fissi verde

**Nuovo**: Supporto completo theme engine, aspetto coerente con la dashboard

### Modifiche su `login.html`:
- **Aggiungere `data-theme` su `<html>`** leggendo da `localStorage('vessel-theme')`
- **Aggiungere le 6 definizioni tema** (copia da `01-design-system.css`) come override CSS nel `<style>`
- `:root` diventa il default Terminal Green, poi `[data-theme="sigil"]` etc. come la dashboard
- **Colori Sigil face dinamici**: `_SC.eye` e `_SC.glow` leggono `--accent` dal computed style invece di hardcoded `#00ff41`
- `_SC.hood` legge `--accent3` (cosicche' in Sigil Violet il cappuccio e' viola scuro, in green e' verde scuro, etc.)
- **Scan-line CRT**: Aggiungere `body::after` overlay identico alla dashboard
- **CRT transition**: Adattare i colori dell'animazione `crt-glow` per usare `--accent` invece di rgba hardcoded
- **Numpad + bordi**: Tutti i colori usano var(--accent*) per seguire il tema attivo

---

## 4. Mini Settings Panel in Dashboard

**Attuale**: Colonna destra ha Chart + 4 widget tiles, con spazio vuoto sotto

**Nuovo**: Aggiungere un pannello "SETTINGS" sotto le widget tiles nella colonna destra

### Contenuto del pannello:
```
SETTINGS
├── Tema: [6 chip colorati selezionabili]
├── Info: picoclaw.local · uptime: XX · vX.X.X
└── [? Help]
```

### Modifiche:
- **index.html**: Aggiungere `div.dash-settings` dentro `dash-right-col`, dopo `dash-widgets`
  - Selettore temi (stessa struttura, riusando `buildThemeSelector()` o ID `theme-selector`)
  - Riga info compatta: hostname, uptime (id riusato `hc-uptime-val`), version badge
  - Bottone Help
- **CSS** (`03-dashboard.css`): Stili per `.dash-settings` — card bg, bordo, padding compatto
- **JS** (`00-theme.js`): `buildThemeSelector()` deve buildare nel nuovo target dashboard
- **Profile tab**: RIMUOVERE la sezione TEMA (non duplicata, vive solo in Dashboard)
- **Profile tab**: RIMUOVERE il bottone Help (spostato in settings dashboard)

---

## 5. Riepilogo file da modificare

| File | Azione |
|------|--------|
| `src/frontend/index.html` | Header fuori da tab, rimuovere code-header e prof-header, logout in system drawer, aggiungere dash-settings, rimuovere tema/help da profile |
| `src/frontend/login.html` | Theme engine, colori dinamici Sigil face, scan-lines |
| `src/frontend/css/03-dashboard.css` | `.dash-header` -> `.app-header`, nuovo `.dash-settings` |
| `src/frontend/css/04-code.css` | Rimuovere `.code-header` |
| `src/frontend/css/06-profile.css` | Rimuovere `.prof-header` |
| `src/frontend/css/08-responsive.css` | Verificare responsive header unificato |
| `src/frontend/js/core/00-theme.js` | Theme selector target dashboard |
| `src/frontend/js/core/08-ui.js` | Clock singolo, rimuovere ref chat-clock |

---

## 6. Ordine di esecuzione
1. Header unificato (HTML + CSS + JS)
2. Logout nel System drawer
3. Mini settings panel in Dashboard (incluso spostamento tema)
4. PIN screen coerenza temi
5. Build + test locale porta 8091
