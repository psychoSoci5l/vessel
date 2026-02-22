if __name__ == "__main__":
    print(f"\n🐈 Vessel Dashboard")
    print(f"   → http://picoclaw.local:{PORT}")
    print(f"   → http://localhost:{PORT}")
    print(f"   Ctrl+C per fermare\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
