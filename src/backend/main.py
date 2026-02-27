if __name__ == "__main__":
    _disp_host = subprocess.run(["hostname"], capture_output=True, text=True, timeout=5).stdout.strip() or "localhost"
    https_ready = ensure_self_signed_cert()
    if https_ready:
        print(f"\n Vessel Dashboard (HTTPS)")
        print(f"   -> https://{_disp_host}:{HTTPS_PORT}")
        print(f"   -> https://localhost:{HTTPS_PORT}")
        print(f"   Certificato: {CERT_FILE}")
        print(f"   NOTA: il browser mostrera' un avviso per cert autofirmato")
        print(f"   Ctrl+C per fermare\n")
        uvicorn.run(app, host="0.0.0.0", port=HTTPS_PORT, log_level="warning",
                    ssl_keyfile=str(KEY_FILE), ssl_certfile=str(CERT_FILE))
    else:
        if HTTPS_ENABLED:
            print("   HTTPS richiesto ma certificato non disponibile, fallback HTTP")
        print(f"\n Vessel Dashboard")
        print(f"   -> http://{_disp_host}:{PORT}")
        print(f"   -> http://localhost:{PORT}")
        print(f"   Ctrl+C per fermare\n")
        uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
