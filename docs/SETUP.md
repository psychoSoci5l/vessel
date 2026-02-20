# Full Setup Guide

Complete guide to setting up Vessel on a Raspberry Pi 5 from scratch.

## Prerequisites

### Hardware
- Raspberry Pi 5 (8GB recommended, 4GB minimum)
- USB-C power supply (5V/5A official recommended)
- MicroSD card or USB SSD (SSD strongly recommended for performance)
- Network connection (Ethernet or Wi-Fi)

### Software
- Raspberry Pi OS Lite (64-bit) or Debian 13 Trixie Lite
- Python 3.11 or newer

## Step 1: Flash the OS

Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/) to flash **Raspberry Pi OS Lite (64-bit)** to your SD card or SSD.

In the imager settings:
- Set hostname (e.g., `vessel`)
- Enable SSH with password or key authentication
- Configure Wi-Fi if needed
- Set locale and timezone

## Step 2: First boot and update

```bash
ssh your-user@vessel.local

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git tmux
```

## Step 3: Install Vessel

```bash
# Clone the repo
git clone https://github.com/psychoSoci5l/vessel-pi.git
cd vessel-pi

# Install Python dependencies
pip install -r requirements.txt
# Or: pip install fastapi uvicorn
```

## Step 4: Install Ollama (local AI)

See [OLLAMA.md](OLLAMA.md) for detailed instructions.

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma3:4b
```

## Step 5: Configure

```bash
# Create the data directory
mkdir -p ~/.nanobot/workspace/memory

# Set your environment variables
export VESSEL_HOST=vessel.local
export VESSEL_USER=yourname

# Or create a .env file (Vessel reads environment variables)
cp config/vessel.env.example .env
# Edit .env with your settings
```

## Step 6: Run

```bash
# Quick test
python3 vessel.py

# Or run in tmux for persistence
tmux new-session -d -s vessel 'python3 ~/vessel-pi/vessel.py'
```

Open `http://vessel.local:8090` in your browser.

## Step 7: Set up as a service (optional)

For automatic startup on boot:

```bash
cp config/vessel.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable vessel
systemctl --user start vessel

# Enable lingering so user services start at boot
sudo loginctl enable-linger $USER
```

## Step 8: Set PIN

On first visit to the dashboard, you'll be prompted to create a 4+ digit PIN. This PIN protects all dashboard access.

## PWA Installation

### iPhone/iPad
1. Open the dashboard URL in Safari
2. Tap the Share button
3. Select "Add to Home Screen"

### Android
1. Open the dashboard URL in Chrome
2. Tap the three-dot menu
3. Select "Add to Home screen" or "Install app"

## Troubleshooting

### Dashboard won't start
```bash
# Check if the port is in use
ss -tlnp | grep 8090

# Check Python version
python3 --version  # Should be 3.11+

# Run with verbose logging
python3 vessel.py  # Check error output
```

### Can't access from other devices
```bash
# Check firewall
sudo ufw status
sudo ufw allow 8090/tcp

# Verify binding
# vessel.py binds to 0.0.0.0 by default (all interfaces)
```

### Ollama not responding
```bash
# Check if Ollama is running
systemctl status ollama
curl http://localhost:11434/api/tags

# Restart Ollama
sudo systemctl restart ollama
```
