import re
import json
from pathlib import Path

def build():
    root = Path(__file__).parent
    src = root / "src"
    
    print("Inizio la build di Vessel Dashboard...")

    # 1. FRONTEND
    print(" Compilando il frontend (HTML/CSS/JS)...")
    html_template = (src / "frontend" / "index.html").read_text("utf-8")
    
    # login_html fallback
    login_path = src / "frontend" / "login.html"
    login_html = login_path.read_text("utf-8") if login_path.exists() else ""
    
    css_content = ""
    for css_file in sorted((src / "frontend" / "css").glob("*.css")):
        css_content += f"\n/* --- {css_file.name} --- */\n"
        css_content += css_file.read_text("utf-8")
        
    js_content = ""
    for js_file in sorted((src / "frontend" / "js" / "core").glob("*.js")) + sorted((src / "frontend" / "js" / "widgets").glob("*.js")):
        js_content += f"\n// --- {js_file.name} --- \n"
        js_content += js_file.read_text("utf-8")
        
    html_template = re.sub(r'<!--\s*\{INJECT_CSS\}\s*-->', lambda _: css_content, html_template)
    html_template = re.sub(r'<!--\s*\{INJECT_JS\}\s*-->', lambda _: js_content, html_template)

    frontend_py = '# ─── FRONTEND (Auto-Generato) ───────────────────────────────────────────────\n'
    frontend_py += f'HTML = {json.dumps(html_template, ensure_ascii=False)}\n'
    frontend_py += f'LOGIN_HTML = {json.dumps(login_html, ensure_ascii=False)}\n\n'
    frontend_py += '# Inject variables that were previously in the HTML f-string\n'
    frontend_py += 'HTML = HTML.replace("{VESSEL_ICON}", VESSEL_ICON) if "VESSEL_ICON" in globals() else HTML.replace("{VESSEL_ICON}", "")\n'
    frontend_py += 'HTML = HTML.replace("{VESSEL_ICON_192}", VESSEL_ICON_192) if "VESSEL_ICON_192" in globals() else HTML.replace("{VESSEL_ICON_192}", "")\n'
    frontend_py += 'LOGIN_HTML = LOGIN_HTML.replace("{VESSEL_ICON}", VESSEL_ICON) if "VESSEL_ICON" in globals() else LOGIN_HTML.replace("{VESSEL_ICON}", "")\n'
    frontend_py += 'LOGIN_HTML = LOGIN_HTML.replace("{VESSEL_ICON_192}", VESSEL_ICON_192) if "VESSEL_ICON_192" in globals() else LOGIN_HTML.replace("{VESSEL_ICON_192}", "")\n'

    # 2. BACKEND
    print(" Compilando il backend Python...")
    
    backend_files = [
        "imports.py",
        "config.py",
        "providers.py",
        "services.py",
        "routes.py",
        "main.py"
    ]
    
    backend_content = ""
    for b_file in backend_files:
        path = src / "backend" / b_file
        if path.exists():
            content = path.read_text("utf-8")
            content = re.sub(r'^from src\.backend.*?import.*$', '', content, flags=re.MULTILINE)
            backend_content += f"\n# --- src/backend/{b_file} ---\n{content}\n"
            
            # Iniettiamo il frontend dopo config.py così le costanti (es VESSEL_ICON) sono disponibili
            if b_file == "config.py":
                backend_content += f"\n{frontend_py}\n"
    
    out_file = root / "nanobot_dashboard_v2.py"
    out_file.write_text(backend_content, "utf-8")
    
    print(f" Build completata! File generato: {out_file.name} ({len(backend_content)} bytes)")

if __name__ == "__main__":
    build()
