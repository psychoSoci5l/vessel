# Ollama Setup — Local LLM on Raspberry Pi

Run a local language model on your Pi 5 with zero cloud dependency.

## Installation

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

This installs Ollama and sets up a systemd service that starts automatically.

## Download a model

```bash
# Recommended for Pi 5 (3.3 GB, good balance of quality and speed)
ollama pull gemma3:4b

# Alternatives:
# ollama pull phi4-mini      # 2.5 GB, faster but less capable
# ollama pull llama3.2:3b    # 2.0 GB, lightweight
# ollama pull qwen2.5:3b     # 1.9 GB, very fast
```

## Performance on Pi 5

| Model | Size | Speed (CPU) | RAM Usage |
|-------|------|-------------|-----------|
| gemma3:4b | 3.3 GB | ~3.5 tok/s | ~4.7 GB total |
| phi4-mini | 2.5 GB | ~5 tok/s | ~3.8 GB total |
| llama3.2:3b | 2.0 GB | ~6 tok/s | ~3.5 GB total |

- Pi 5 (8GB): comfortable with gemma3:4b, ~3.1 GB free RAM
- Pi 5 (4GB): use smaller models (phi4-mini or llama3.2:3b)

## Verify installation

```bash
# Check service status
systemctl status ollama

# Test the API
curl http://localhost:11434/api/tags

# Test a generation
curl http://localhost:11434/api/generate -d '{
  "model": "gemma3:4b",
  "prompt": "Hello!",
  "stream": false
}'
```

## Configure Vessel to use Ollama

Vessel uses Ollama by default. Configure via environment variables:

```bash
export OLLAMA_BASE=http://127.0.0.1:11434   # Default
export OLLAMA_MODEL=gemma3:4b                # Default
export OLLAMA_TIMEOUT=120                    # Seconds
export OLLAMA_SYSTEM="You are a helpful assistant. Be concise."
```

## Running Ollama on a different machine

If your LLM runs on a separate, more powerful machine:

```bash
# On the LLM machine: bind Ollama to all interfaces
# Edit /etc/systemd/system/ollama.service and add:
# Environment="OLLAMA_HOST=0.0.0.0"

# On the Pi: point Vessel to the remote Ollama
export OLLAMA_BASE=http://192.168.1.100:11434
```

## Managing models

```bash
# List installed models
ollama list

# Remove a model
ollama rm gemma3:4b

# Show model info
ollama show gemma3:4b
```

## Troubleshooting

### Ollama service won't start
```bash
sudo systemctl restart ollama
journalctl -u ollama -f
```

### Out of memory
The Pi will become unresponsive if RAM is exhausted. Use a smaller model or add swap:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Slow generation
- Ensure no other heavy processes are running
- CPU-only inference is inherently slow on ARM — this is expected
- Consider offloading to a separate machine (see above)
