# ─── Chat Providers ─────────────────────────────────────────────────────────────

class BaseChatProvider:
    def __init__(self, model: str, system_prompt: str, history: list):
        self.model = model
        self.system_prompt = system_prompt
        self.history = history
        self.host = ""
        self.port = 80
        self.use_https = False
        self.path = ""
        self.headers = {}
        self.payload = ""
        self.timeout = 60
        self.parser_type = "json_lines"
        self.is_valid = True
        self.error_msg = ""
    
    def setup(self):
        pass

class AnthropicProvider(BaseChatProvider):
    def setup(self):
        cfg = _get_config("config.json")
        api_key = cfg.get("providers", {}).get("anthropic", {}).get("apiKey", "")
        if not api_key:
            self.is_valid = False
            self.error_msg = "(nessuna API key Anthropic)"
            return
        self.host, self.port, self.use_https = "api.anthropic.com", 443, True
        self.path = "/v1/messages"
        self.headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01", "x-api-key": api_key}
        self.payload = json.dumps({"model": self.model, "max_tokens": 1024, "system": self.system_prompt, "messages": self.history, "stream": True})
        self.parser_type = "sse_anthropic"

class OpenRouterProvider(BaseChatProvider):
    def setup(self):
        or_cfg = _get_config("openrouter.json")
        api_key = os.environ.get("OPENROUTER_API_KEY", or_cfg.get("apiKey", ""))
        if not api_key:
            self.is_valid = False
            self.error_msg = "(nessuna API key OpenRouter)"
            return
        self.host, self.port, self.use_https = "openrouter.ai", 443, True
        self.path = "/api/v1/chat/completions"
        self.headers = {
            "Content-Type": "application/json", "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://vessel.local", "X-Title": "Vessel Dashboard"
        }
        self.payload = json.dumps({
            "model": self.model, "messages": [{"role": "system", "content": self.system_prompt}] + self.history,
            "max_tokens": 1024, "stream": True, "provider": {"order": or_cfg.get("providerOrder", ["ModelRun", "DeepInfra"])}
        })
        self.parser_type = "sse_openai"

class OllamaPCProvider(BaseChatProvider):
    def setup(self):
        pc_cfg = _get_config("ollama_pc.json")
        self.host = pc_cfg.get("host", "localhost")
        self.port = pc_cfg.get("port", 11434)
        self.use_https = False
        self.path = "/api/chat"
        self.headers = {"Content-Type": "application/json"}
        self.payload = json.dumps({
            "model": self.model, "messages": [{"role": "system", "content": self.system_prompt}] + self.history,
            "stream": True, "keep_alive": "60m",
            "options": {"num_predict": OLLAMA_PC_NUM_PREDICT}
        })

class OllamaProvider(BaseChatProvider):
    def setup(self):
        self.host, self.port, self.use_https = "127.0.0.1", 11434, False
        self.path = "/api/chat"
        self.headers = {"Content-Type": "application/json"}
        self.payload = json.dumps({
            "model": self.model, "messages": [{"role": "system", "content": self.system_prompt}] + self.history,
            "stream": True, "keep_alive": OLLAMA_KEEP_ALIVE,
            "options": {"num_predict": 1024}
        })
        self.timeout = OLLAMA_TIMEOUT

class BrainProvider(BaseChatProvider):
    """Claude Code CLI via bridge — ragionamento con memoria cross-sessione."""
    def setup(self):
        if not CLAUDE_BRIDGE_TOKEN:
            self.is_valid = False
            self.error_msg = "(Bridge token mancante)"
            return
        from urllib.parse import urlparse
        parsed = urlparse(CLAUDE_BRIDGE_URL)
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or 8095
        self.use_https = parsed.scheme == "https"
        self.path = "/brain"
        self.headers = {"Content-Type": "application/json"}
        # Estrai ultimo messaggio utente dalla history
        last_user_msg = ""
        for msg in reversed(self.history):
            if msg.get("role") == "user":
                last_user_msg = msg["content"]
                break
        self.payload = json.dumps({
            "token": CLAUDE_BRIDGE_TOKEN,
            "prompt": last_user_msg,
            "system_prompt": self.system_prompt,
        })
        self.timeout = 120
        self.parser_type = "ndjson_brain"

def get_provider(provider_id: str, model: str, system_prompt: str, history: list) -> BaseChatProvider:
    if provider_id == "brain":
        p = BrainProvider(model, system_prompt, history)
    elif provider_id == "anthropic":
        p = AnthropicProvider(model, system_prompt, history)
    elif provider_id == "openrouter":
        p = OpenRouterProvider(model, system_prompt, history)
    elif provider_id == "ollama_pc":
        p = OllamaPCProvider(model, system_prompt, history)
    else:
        p = OllamaProvider(model, system_prompt, history)
    p.setup()
    return p
