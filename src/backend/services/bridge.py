# ─── Claude Bridge (Remote Code) ─────────────────────────────────────────────
def check_bridge_health() -> dict:
    """Verifica se il Claude Bridge su Windows è raggiungibile."""
    try:
        req = urllib.request.Request(f"{CLAUDE_BRIDGE_URL}/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read())
    except Exception:
        return {"status": "offline"}

def get_claude_tasks(n: int = 10) -> list[dict]:
    """Legge gli ultimi N task da SQLite."""
    return db_get_claude_tasks(n)

def log_claude_task(prompt: str, status: str, exit_code: int = 0,
                    duration_ms: int = 0, output_preview: str = ""):
    """Logga un task Claude in SQLite."""
    db_log_claude_task(prompt, status, exit_code, duration_ms, output_preview)

async def run_claude_task_stream(websocket: WebSocket, prompt: str, use_loop: bool = False):
    """Esegue un task via Claude Bridge con streaming output via WS."""
    queue: asyncio.Queue = asyncio.Queue()
    start_time = time.time()
    endpoint = "/run-loop" if use_loop else "/run"

    def _bridge_worker():
        try:
            # Parse host:port da CLAUDE_BRIDGE_URL
            url = CLAUDE_BRIDGE_URL.replace("http://", "")
            if ":" in url:
                host, port_s = url.split(":", 1)
                port = int(port_s.split("/")[0])
            else:
                host, port = url.split("/")[0], 80
            conn = http.client.HTTPConnection(host, port, timeout=TASK_TIMEOUT)
            payload = json.dumps({
                "prompt": prompt,
                "token": CLAUDE_BRIDGE_TOKEN,
            })
            conn.request("POST", endpoint, body=payload,
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            if resp.status != 200:
                body = resp.read().decode("utf-8", errors="replace")
                queue.put_nowait(("error", {"text": f"HTTP {resp.status}: {body[:200]}"}))
                queue.put_nowait(("end", None))
                conn.close()
                return
            buf = ""
            while True:
                raw = resp.read(512)
                if not raw:
                    break
                buf += raw.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        queue.put_nowait((data.get("type", "chunk"), data))
                    except json.JSONDecodeError:
                        queue.put_nowait(("chunk", {"text": line + "\n"}))
            conn.close()
        except Exception as e:
            queue.put_nowait(("error", {"text": str(e)}))
        finally:
            queue.put_nowait(("end", None))

    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _bridge_worker)

    full_output = ""
    exit_code = -1
    iterations = 1
    completed = False

    while True:
        try:
            kind, val = await asyncio.wait_for(queue.get(), timeout=TASK_TIMEOUT)
        except asyncio.TimeoutError:
            await websocket.send_json({"type": "claude_chunk", "text": "\n(timeout bridge)"})
            break
        if kind == "chunk":
            text = val.get("text", "") if isinstance(val, dict) else str(val)
            full_output += text
            await websocket.send_json({"type": "claude_chunk", "text": text})
        elif kind == "done":
            exit_code = val.get("exit_code", 0) if isinstance(val, dict) else 0
            iterations = val.get("iterations", 1) if isinstance(val, dict) else 1
            completed = val.get("completed", exit_code == 0) if isinstance(val, dict) else False
            break
        elif kind == "error":
            err = val.get("text", "") if isinstance(val, dict) else str(val)
            await websocket.send_json({"type": "claude_chunk", "text": f"\n⚠️ {err}"})
            break
        elif kind == "iteration_start":
            i = val.get("iteration", 1) if isinstance(val, dict) else 1
            m = val.get("max", 3) if isinstance(val, dict) else 3
            await websocket.send_json({"type": "claude_iteration", "iteration": i, "max": m})
        elif kind == "supervisor":
            text = val.get("text", "") if isinstance(val, dict) else str(val)
            await websocket.send_json({"type": "claude_supervisor", "text": text})
        elif kind in ("info", "rollback"):
            text = val.get("text", "") if isinstance(val, dict) else str(val)
            await websocket.send_json({"type": "claude_info", "text": text})
        elif kind == "end":
            break

    elapsed = int((time.time() - start_time) * 1000)
    status = "done" if exit_code == 0 else "error"
    await websocket.send_json({
        "type": "claude_done",
        "exit_code": exit_code,
        "duration_ms": elapsed,
        "iterations": iterations,
        "completed": completed,
        "notify": True
    })
    log_claude_task(prompt, status, exit_code, elapsed, full_output[:200])

    # Notifica Telegram al completamento
    secs = elapsed // 1000
    icon = "✅" if completed else "❌"
    summary = full_output.strip()[-500:] if full_output.strip() else "(nessun output)"
    tg_msg = (
        f"{icon} Remote Task {'completato' if completed else 'fallito'}\n"
        f"Prompt: {prompt[:200]}\n"
        f"Durata: {secs}s | Iterazioni: {iterations}\n"
        f"---\n{summary}"
    )
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, telegram_send, tg_msg)
