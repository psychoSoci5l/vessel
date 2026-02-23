#!/usr/bin/env python3
"""
Benchmark LLM per selezione modello ottimale su Ollama PC
Misura: tok/s (oggettivo) + qualità output (rubrica 0-3)
"""

import json
import time
import requests
from datetime import datetime

OLLAMA_HOST = "http://192.168.178.34:11434"
NUM_PREDICT = 512   # token max per risposta — abbastanza per valutare, non troppo
TEMPERATURE = 0.0   # deterministico

# ─── MODELLI DA TESTARE ───────────────────────────────────────────────
MODELS = [
    "qwen2.5-coder:14b",   # baseline attuale — full GPU (9GB)
    "qwen3-coder:30b",     # candidato — parziale offload (19GB, ~7GB su RAM)
]

# ─── TASK DI BENCHMARK ───────────────────────────────────────────────
# Casi reali del bridge — semplici ma rappresentativi
TASKS = [
    {
        "id": "T1_debug_syntax",
        "category": "debug",
        "prompt": """Questo codice Python ha un errore. Trovalo e correggilo. Rispondi SOLO con il codice corretto, nessuna spiegazione.

```python
def build_context(messages, max_tokens=4000):
    result = []
    total = 0
    for msg on messages:
        tokens = len(msg['content'].split()) * 1.3
        if total + tokens > max_tokens:
            break
        result.append(msg)
        total += tokens
    return result
```""",
        "expected_fix": "for msg in messages",  # keyword attesa nel codice corretto
        "rubric": {
            3: "Codice corretto, solo `for msg in messages`, nessuna spiegazione extra",
            2: "Trova l'errore ma aggiunge testo non richiesto",
            1: "Individua il problema ma il codice non è direttamente eseguibile",
            0: "Non trova l'errore o risposta errata"
        }
    },
    {
        "id": "T2_add_feature",
        "category": "modifica",
        "prompt": """Aggiungi a questa funzione il parametro opzionale `include_system=True`. Se False, filtra i messaggi con role='system'.
Rispondi SOLO con la funzione modificata.

```python
def get_recent_messages(db_path, limit=20):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT role, content FROM chat_messages ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
```""",
        "expected_fix": "include_system",
        "rubric": {
            3: "Funzione corretta con parametro, filtraggio condizionale, solo codice",
            2: "Logica corretta ma include spiegazione o firma sbagliata",
            1: "Aggiunge il parametro ma il filtraggio è incompleto/errato",
            0: "Non modifica correttamente"
        }
    },
    {
        "id": "T3_create_function",
        "category": "crea",
        "prompt": """Scrivi una funzione Python `format_uptime(seconds: int) -> str` che converte secondi in formato leggibile tipo "3g 4h 12m". Rispondi SOLO con la funzione.""",
        "expected_fix": "def format_uptime",
        "rubric": {
            3: "Funzione corretta, gestisce giorni/ore/minuti, solo codice",
            2: "Funzione corretta ma con extra non richiesto",
            1: "Funzione parziale (manca un'unità o logica errata)",
            0: "Non restituisce una funzione valida"
        }
    },
    {
        "id": "T4_analyze_code",
        "category": "analizza",
        "prompt": """Analizza questo codice e rispondi con UNA sola frase: qual è il problema principale?

```python
@app.route('/api/messages', methods=['GET'])
def get_messages():
    user = request.args.get('user')
    query = f"SELECT * FROM messages WHERE user = '{user}'"
    conn = sqlite3.connect('app.db')
    results = conn.execute(query).fetchall()
    return jsonify(results)
```""",
        "expected_fix": "SQL injection",
        "rubric": {
            3: "Identifica SQL injection in una frase, conciso",
            2: "Identifica SQL injection ma risposta troppo lunga",
            1: "Menziona un problema ma non il principale",
            0: "Non identifica SQL injection"
        }
    },
    {
        "id": "T5_refactor",
        "category": "modifica",
        "prompt": """Riscrivi questa funzione in modo pythonic usando una list comprehension. Rispondi SOLO con la funzione.

```python
def filter_errors(logs):
    result = []
    for entry in logs:
        if entry.get('level') == 'ERROR':
            result.append(entry['message'])
    return result
```""",
        "expected_fix": "list comprehension",
        "rubric": {
            3: "Una list comprehension corretta, solo codice",
            2: "Usa list comprehension ma aggiunge spiegazione",
            1: "Refactor ma non usa list comprehension",
            0: "Non refactora correttamente"
        }
    },
]

# ─── CORE BENCHMARK ──────────────────────────────────────────────────

def run_single(model: str, task: dict) -> dict:
    """Esegue un singolo task su un modello, restituisce metriche."""
    payload = {
        "model": model,
        "prompt": task["prompt"],
        "stream": False,
        "options": {
            "temperature": TEMPERATURE,
            "num_predict": NUM_PREDICT,
            "seed": 42,
        }
    }
    t_start = time.time()
    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": str(e), "toks": 0, "elapsed": time.time() - t_start}

    t_elapsed = time.time() - t_start
    eval_count = data.get("eval_count", 0)
    eval_duration_ns = data.get("eval_duration", 1)
    toks_per_sec = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns else 0

    return {
        "output": data.get("response", ""),
        "toks_per_sec": round(toks_per_sec, 1),
        "eval_count": eval_count,
        "elapsed_s": round(t_elapsed, 1),
        "error": None
    }


def score_output(output: str, task: dict) -> int:
    """Scoring semi-automatico: verifica presenza keyword attesa + lunghezza."""
    out_lower = output.lower()
    expected = task["expected_fix"].lower()

    # Check keyword
    has_keyword = expected in out_lower

    # Penalità per risposte troppo verbose (> 60 parole per task di codice)
    word_count = len(output.split())
    is_verbose = word_count > 200 and task["category"] in ("debug", "modifica", "crea")

    if not has_keyword:
        return 0
    if is_verbose:
        return 2
    return 3  # keyword presente, non verboso — score massimo automatico


def benchmark_model(model: str) -> dict:
    """Esegue tutti i task su un modello."""
    print(f"\n{'='*60}")
    print(f"  Modello: {model}")
    print(f"{'='*60}")

    results = []
    for task in TASKS:
        print(f"  [{task['id']}] {task['category']}...", end=" ", flush=True)
        r = run_single(model, task)
        if r.get("error"):
            print(f"ERRORE: {r['error']}")
            results.append({"task_id": task["id"], "score": 0, "toks_per_sec": 0, "error": r["error"]})
            continue

        score = score_output(r["output"], task)
        tps = r["toks_per_sec"]
        print(f"{tps:.1f} tok/s | score {score}/3 | {r['elapsed_s']}s")

        results.append({
            "task_id": task["id"],
            "category": task["category"],
            "score": score,
            "toks_per_sec": tps,
            "elapsed_s": r["elapsed_s"],
            "output_snippet": r["output"][:200].replace('\n', ' '),
        })

    return {"model": model, "results": results}


def print_summary(all_results: list):
    print(f"\n{'='*60}")
    print("  RIEPILOGO BENCHMARK")
    print(f"{'='*60}")
    print(f"{'Modello':<30} {'Avg tok/s':>10} {'Score tot':>10} {'Score%':>8}")
    print("-" * 60)

    for mr in all_results:
        results = mr["results"]
        avg_tps = sum(r["toks_per_sec"] for r in results) / len(results)
        total_score = sum(r["score"] for r in results)
        max_score = len(results) * 3
        score_pct = total_score / max_score * 100

        print(f"{mr['model']:<30} {avg_tps:>10.1f} {total_score:>7}/{max_score} {score_pct:>7.0f}%")

    print(f"\nNote:")
    print(f"  - Scoring automatico (keyword + verbosità) — verifica output manuale consigliata")
    print(f"  - Temperature=0 + seed=42 per riproducibilità")


def save_results(all_results: list):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"benchmark_results_{ts}.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n  Risultati salvati in: {fname}")
    return fname


# ─── MAIN ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Modelli da testare — aggiornare con i nomi confermati
    models_to_test = MODELS
    if not models_to_test:
        # fallback: chiedi all'API quali sono disponibili
        try:
            r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
            available = [m["name"] for m in r.json().get("models", [])]
            print(f"Modelli disponibili su Ollama PC: {available}")
            print("Aggiorna MODELS = [...] nello script con i modelli da testare.")
        except Exception as e:
            print(f"Errore connessione Ollama PC: {e}")
        exit(0)

    print(f"Benchmark LLM — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Modelli: {models_to_test}")
    print(f"Task: {len(TASKS)} | Token max: {NUM_PREDICT} | Temp: {TEMPERATURE}")

    all_results = []
    for model in models_to_test:
        mr = benchmark_model(model)
        all_results.append(mr)

    print_summary(all_results)
    fname = save_results(all_results)

    # Stampa output completi per review manuale
    print(f"\n{'='*60}")
    print("  OUTPUT COMPLETI (per valutazione manuale)")
    print(f"{'='*60}")
    for mr in all_results:
        print(f"\n--- {mr['model']} ---")
        for r in mr["results"]:
            print(f"\n[{r['task_id']}] score={r['score']}/3 | {r['toks_per_sec']} tok/s")
            print(f"  Output: {r.get('output_snippet', 'N/A')}")
