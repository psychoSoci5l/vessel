# ─── Telegram ────────────────────────────────────────────────────────────────
def telegram_send(text: str) -> bool:
    """Invia un messaggio al bot Telegram. Restituisce True se successo."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text[:4096],
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"[Telegram] send error: {e}")
        return False

def telegram_get_file(file_id: str) -> str:
    """Ottiene il file_path dal file_id Telegram. Restituisce stringa vuota su errore."""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getFile?file_id={file_id}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        return data.get("result", {}).get("file_path", "")
    except Exception as e:
        print(f"[Telegram] getFile error: {e}")
        return ""


def telegram_download_file(file_path: str) -> bytes:
    """Scarica un file dai server Telegram. Restituisce bytes vuoti su errore."""
    try:
        url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_path}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        print(f"[Telegram] download error: {e}")
        return b""


def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Trascrive audio via Groq Whisper API (urllib puro, multipart/form-data).
    Restituisce il testo trascritto, stringa vuota su errore."""
    if not GROQ_API_KEY:
        print("[STT] Groq API key non configurata")
        return ""
    if not audio_bytes:
        return ""
    try:
        boundary = "----VesselSTTBoundary"
        body = b""
        # Campo: file
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        body += b"Content-Type: audio/ogg\r\n\r\n"
        body += audio_bytes
        body += b"\r\n"
        # Campo: model
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="model"\r\n\r\n'
        body += f"{GROQ_WHISPER_MODEL}\r\n".encode()
        # Campo: language
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="language"\r\n\r\n'
        body += f"{GROQ_WHISPER_LANGUAGE}\r\n".encode()
        # Campo: response_format
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="response_format"\r\n\r\n'
        body += b"json\r\n"
        # Campo: temperature
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="temperature"\r\n\r\n'
        body += b"0\r\n"
        # Chiudi boundary
        body += f"--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            data=body, method="POST"
        )
        req.add_header("Authorization", f"Bearer {GROQ_API_KEY}")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("User-Agent", "Vessel-Dashboard/1.0")

        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        text = result.get("text", "").strip()
        if text:
            print(f"[STT] Trascritto: {text[:80]}...")
        return text
    except Exception as e:
        print(f"[STT] Groq Whisper error: {e}")
        return ""


def text_to_voice(text: str) -> bytes:
    """Converte testo in audio OGG Opus via Edge TTS + ffmpeg.
    Restituisce bytes OGG pronti per Telegram sendVoice, bytes vuoti su errore."""
    if not text or not text.strip():
        return b""
    # Tronca testo troppo lungo
    if len(text) > TTS_MAX_CHARS:
        text = text[:TTS_MAX_CHARS]
    try:
        import edge_tts
        import tempfile
        # Edge TTS genera MP3 — scriviamo su temp file
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as mp3_f:
            mp3_path = mp3_f.name
        ogg_path = mp3_path.replace(".mp3", ".ogg")
        # Esegui edge-tts in modo sincrono (asyncio.run in thread separato)
        async def _generate():
            comm = edge_tts.Communicate(text, TTS_VOICE)
            await comm.save(mp3_path)
        # Usa un nuovo event loop (siamo in un thread executor)
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            # Siamo già in un event loop — usa asyncio.run_coroutine_threadsafe
            # Non dovrebbe succedere, ma gestiamo il caso
            new_loop = asyncio.new_event_loop()
            new_loop.run_until_complete(_generate())
            new_loop.close()
        else:
            asyncio.run(_generate())
        # Converti MP3 → OGG Opus via ffmpeg
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", mp3_path, "-c:a", "libopus", "-b:a", "48k",
             "-application", "voip", ogg_path],
            capture_output=True, timeout=30
        )
        if result.returncode != 0:
            print(f"[TTS] ffmpeg error: {result.stderr.decode()[:200]}")
            return b""
        with open(ogg_path, "rb") as f:
            ogg_bytes = f.read()
        try:
            os.unlink(mp3_path)
        except Exception:
            pass
        try:
            os.unlink(ogg_path)
        except Exception:
            pass
        if ogg_bytes:
            print(f"[TTS] Generato vocale: {len(ogg_bytes)} bytes, {len(text)} chars")
        return ogg_bytes
    except Exception as e:
        print(f"[TTS] Error: {e}")
        return b""


def telegram_send_voice(ogg_bytes: bytes, caption: str = "") -> bool:
    """Invia un messaggio vocale OGG Opus a Telegram via sendVoice API (multipart).
    Restituisce True se successo."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    if not ogg_bytes:
        return False
    try:
        boundary = "----VesselTTSBoundary"
        body = b""
        # Campo: chat_id
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        body += f"{TELEGRAM_CHAT_ID}\r\n".encode()
        # Campo: voice (file OGG)
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="voice"; filename="voice.ogg"\r\n'
        body += b"Content-Type: audio/ogg\r\n\r\n"
        body += ogg_bytes
        body += b"\r\n"
        # Campo: caption (opzionale)
        if caption:
            body += f"--{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
            body += f"{caption[:1024]}\r\n".encode()
        # Chiudi boundary
        body += f"--{boundary}--\r\n".encode()

        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendVoice"
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("User-Agent", "Vessel-Dashboard/1.0")
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        if result.get("ok"):
            print("[TTS] Vocale inviato su Telegram")
            return True
        print(f"[TTS] sendVoice failed: {result}")
        return False
    except Exception as e:
        print(f"[TTS] sendVoice error: {e}")
        return False
