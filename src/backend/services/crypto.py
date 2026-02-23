# ─── Crypto ──────────────────────────────────────────────────────────────────
_crypto_cache: dict = {}

def get_crypto_prices() -> dict:
    """Fetch BTC/ETH prezzi da CoinGecko API pubblica, con cache fallback."""
    global _crypto_cache
    data = {"btc": None, "eth": None, "error": None}
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd,eur&include_24hr_change=true"
        req = urllib.request.Request(url, headers={"User-Agent": "Vessel-Dashboard/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read())
        if "bitcoin" in raw:
            b = raw["bitcoin"]
            data["btc"] = {"usd": b.get("usd", 0), "eur": b.get("eur", 0),
                           "change_24h": round(b.get("usd_24h_change", 0), 2)}
        if "ethereum" in raw:
            e = raw["ethereum"]
            data["eth"] = {"usd": e.get("usd", 0), "eur": e.get("eur", 0),
                           "change_24h": round(e.get("usd_24h_change", 0), 2)}
        _crypto_cache = {"btc": data["btc"], "eth": data["eth"], "ts": time.time()}
    except Exception as ex:
        data["error"] = str(ex)[:100]
        if _crypto_cache:
            data["btc"] = _crypto_cache.get("btc")
            data["eth"] = _crypto_cache.get("eth")
            data["error"] = f"cached ({data['error']})"
    return data
