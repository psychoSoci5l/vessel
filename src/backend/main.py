if __name__ == "__main__":
    https_ready = ensure_self_signed_cert()
    if https_ready:
        print(f"\n🐈 Vessel Dashboard (HTTPS)")
        print(f"   → https://picoclaw.local:{HTTPS_PORT}")
        print(f"   → https://localhost:{HTTPS_PORT}")
        print(f"   Certificato: {CERT_FILE}")
        print(f"   NOTA: il browser mostrerà un avviso per cert autofirmato")
        print(f"   Ctrl+C per fermare\n")
        uvicorn.run(app, host="0.0.0.0", port=HTTPS_PORT, log_level="warning",
                    ssl_keyfile=str(KEY_FILE), ssl_certfile=str(CERT_FILE))
    else:
        if HTTPS_ENABLED:
            print("   ⚠ HTTPS richiesto ma certificato non disponibile, fallback HTTP")
        print(f"\n🐈 Vessel Dashboard")
        print(f"   → http://picoclaw.local:{PORT}")
        print(f"   → http://localhost:{PORT}")
        print(f"   Ctrl+C per fermare\n")
        uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
