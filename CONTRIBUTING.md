# Contributing to Vessel

Thanks for your interest in contributing!

## Guidelines

1. **Single-file rule** — The dashboard must remain a single Python file (`vessel.py`). All HTML, CSS, and JS stay inline. Helper scripts go in `scripts/`.

2. **Keep it light** — Vessel runs on a Raspberry Pi. Avoid heavy dependencies. Every import counts.

3. **Don't break the WebSocket** — The real-time update system is the backbone. Test WebSocket functionality after changes.

4. **Security first** — Never use `shell=True` with user input. Use subprocess argument lists. Validate and sanitize everything.

## How to contribute

1. Fork the repo
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Test on a Pi if possible (or at least verify on Linux)
5. Submit a pull request

## Development

```bash
# Run in test mode (different port)
PORT=8091 python3 vessel.py

# Production
python3 vessel.py
```

## Reporting issues

Please include:
- Python version (`python3 --version`)
- Pi model and OS version
- Steps to reproduce
- Relevant error output

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
