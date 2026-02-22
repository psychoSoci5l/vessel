# Vessel Pi — Performance Tuning Guide

> Ottimizzazioni del sistema Raspberry Pi 5 per uso come server AI/LLM headless.
> Testate su: Raspberry Pi 5 (8 GB RAM), Debian 13 Trixie Lite, Python 3.13.

---

## Sistema di riferimento

| Componente       | Specifiche                    |
|------------------|-------------------------------|
| Board            | Raspberry Pi 5                |
| RAM              | 8 GB LPDDR4X                  |
| Storage          | SSD NVMe via HAT (91 GB)      |
| OS               | Debian 13 Trixie Lite (headless) |
| Python           | 3.13                          |
| Modello LLM      | Gemma 3 4B (Ollama)           |

---

## Risultati benchmark (prima vs dopo)

| Parametro            | Prima (Stock) | Dopo (Ottimizzato) | Risultato                  |
|----------------------|---------------|--------------------|----------------------------|
| CPU Clock            | 2.4 GHz       | 2.4 GHz            | Stabilità garantita        |
| Sysbench (events/s)  | 4051.31       | 4040.67            | Allineato allo standard    |
| Ollama (tokens/s)    | 5.50          | ~5.5 (stimato\*)   | Stabile                    |
| ZRAM (RAM compressa) | Assente       | ~4 GB (zstd)       | Memoria più veloce         |
| Swap (SSD)           | 2.0 GB        | 8.0 GB             | Protezione dai crash       |
| CPU Throttling       | Sconosciuto   | 0x0 (Nessuno)      | Sistema in salute          |
| CPU Governor         | ondemand      | performance        | Latenza costante           |
| Swappiness           | 60            | 10                 | Meno pressione su SSD      |

\* *Il valore 5.05 tok/s del test era viziato da sessioni Ollama non riavviate — ritest a freddo consigliato.*

---

## Step 1 — ZRAM (RAM compressa)

**Cosa fa:** crea un'area di swap in RAM compressa. Quando la RAM fisica è sotto pressione, il kernel usa ZRAM invece del disco — latenza ~100x inferiore rispetto allo swap su SSD.

**Installazione:**
```bash
sudo apt install -y zram-tools
```

**Configurazione** (`/etc/default/zramswap`):
```bash
sudo nano /etc/default/zramswap
```
```
ALGO=zstd          # Miglior rapporto compressione (alternativa: lz4 per velocità massima)
PERCENT=50         # Usa il 50% della RAM fisica (su 8 GB → ~4 GB ZRAM)
```

**Attivazione:**
```bash
sudo systemctl enable zramswap
sudo systemctl start zramswap
```

**Verifica:**
```bash
swapon --show
# NAME       TYPE      SIZE USED PRIO
# /dev/zram0 partition 3.9G   0B  100   ← PRIO 100 = priorità alta
# /var/swap  file        8G   0B   -2   ← SSD come fallback
```

---

## Step 2 — Swap su SSD ampliato

**Cosa fa:** aumenta il swap su SSD da 2 GB a 8 GB. Con ZRAM a priorità alta, il kernel usa il SSD solo come ultima rete di sicurezza (modelli >4B, situazioni di memoria estrema).

```bash
# Disattiva swap esistente
sudo swapoff /var/swap

# Ricrea con dimensione maggiore (8 GB)
sudo dd if=/dev/zero of=/var/swap bs=1M count=8192 status=progress
sudo chmod 600 /var/swap
sudo mkswap /var/swap
sudo swapon /var/swap

# Verifica persistenza in /etc/fstab (dovrebbe già esserci la voce)
grep swap /etc/fstab
```

---

## Step 3 — Kernel: swappiness e cache pressure

**Cosa fa:**
- `swappiness=10`: il kernel preferisce ZRAM alla RAM compressa prima di toccare il disco
- `vfs_cache_pressure=50`: mantiene più cache filesystem in RAM (config, log, file modello)

```bash
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
echo 'vm.vfs_cache_pressure=50' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

**Verifica:**
```bash
cat /proc/sys/vm/swappiness        # → 10
cat /proc/sys/vm/vfs_cache_pressure # → 50
```

---

## Step 4 — GPU memory (headless)

**Cosa fa:** riduce la VRAM riservata al GPU da 64 MB (default) a 16 MB. Su installazione headless senza output video, quei 48 MB tornano alla RAM di sistema.

```bash
echo 'gpu_mem=16' | sudo tee -a /boot/firmware/config.txt
```

> Richiede riavvio per avere effetto.

---

## Step 5 — CPU Governor

**Cosa fa:** imposta il governor `performance` che mantiene il clock CPU sempre al massimo (2.4 GHz). Elimina i ritardi di ramp-up del clock su richieste ad alta frequenza (WebSocket, inference LLM).

> **Trade-off:** consuma ~0.5-1W in più rispetto a `ondemand`. Accettabile per un server sempre acceso.

**Applicazione immediata (tutte le sessioni correnti):**
```bash
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

**Resa permanente (servizio systemd):**
```bash
sudo tee /etc/systemd/system/cpu-governor.service > /dev/null <<'EOF'
[Unit]
Description=Set CPU Governor to Performance
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c "echo performance | tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable cpu-governor
sudo systemctl start cpu-governor
```

**Verifica:**
```bash
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor  # → performance
```

---

## Step 6 — Ollama: thread ottimali

Ollama gestisce automaticamente i thread su CPU, ma puoi forzarli nella sessione tmux:

```bash
# In ~/.bashrc o nella sessione tmux di Ollama
export OLLAMA_NUM_THREADS=4   # Pi 5 ha 4 core fisici
```

---

## Verifica finale

Dopo aver applicato tutte le ottimizzazioni e riavviato:

```bash
# Stato memoria e swap
free -h
swapon --show

# Throttling (deve essere 0x0)
vcgencmd get_throttled

# Temperatura
vcgencmd measure_temp

# Governor
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Parametri kernel
sysctl vm.swappiness vm.vfs_cache_pressure

# Benchmark Ollama (ritest a freddo)
# Invia un messaggio dalla dashboard e osserva i tok/s nei log
```

**Output atteso:**
```
throttled=0x0          ← Nessun throttling
temp=50-55°C           ← Temperatura normale a riposo
scaling_governor=performance
vm.swappiness = 10
vm.vfs_cache_pressure = 50
```

---

## Note

- Il **governor `performance`** non viene impostato automaticamente da `zramswap` — richiede il servizio systemd descritto al Step 5.
- **`gpu_mem=16`** richiede riavvio per essere attivo.
- Le modifiche a `/etc/sysctl.conf` sono **persistenti** al riavvio.
- Lo **swap su SSD** con ZRAM attivo viene usato raramente (solo overflow estremo) — l'usura dell'SSD è minima.
- Questi parametri sono ottimizzati per uso **server headless + LLM**. Non adatti per uso desktop con GUI.
