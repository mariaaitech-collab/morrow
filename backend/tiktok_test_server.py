"""Standalone TikTok connection test server (no database / no auth required).

Run:
    .venv\\Scripts\\python.exe -m uvicorn tiktok_test_server:app --port 8765

Then open http://localhost:8765/
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from config import TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REDIRECT_URI
from tiktok_client import TikTokError, tiktok

app = FastAPI(title="BrandAura TikTok Connection Test", version="1.0.0")


@app.get("/api/tiktok/status")
async def status():
    report = await tiktok.check_connection()
    report["env"] = {
        "TIKTOK_CLIENT_KEY": bool(TIKTOK_CLIENT_KEY),
        "TIKTOK_CLIENT_SECRET": bool(TIKTOK_CLIENT_SECRET),
        "TIKTOK_REDIRECT_URI": TIKTOK_REDIRECT_URI,
    }
    return report


@app.get("/api/tiktok/authorize-url")
async def authorize_url(state: str = "brandora-test"):
    if not tiktok.is_configured():
        return {"error": "TikTok credentials are not configured in .env"}
    # TikTok mandates PKCE. Keep the verifier so /exchange can complete the
    # flow (this standalone server is single-user, so memory is fine).
    url, verifier = tiktok.pkce_authorize_url(state=state)
    _verifiers[state] = verifier
    return {"authorize_url": url, "state": state}


_verifiers: dict[str, str] = {}


@app.post("/api/tiktok/exchange")
async def exchange(code: str, state: str = "brandora-test"):
    verifier = _verifiers.pop(state, "")
    if not verifier:
        return {"error": "Unknown state. Call /api/tiktok/authorize-url first."}
    try:
        return await tiktok.exchange_code(code, code_verifier=verifier)
    except TikTokError as exc:
        return {"error": str(exc), "status_code": exc.status_code, "payload": exc.payload}


@app.get("/api/tiktok/user-info")
async def user_info(access_token: str):
    try:
        return await tiktok.user_info(access_token)
    except TikTokError as exc:
        return {"error": str(exc), "status_code": exc.status_code, "payload": exc.payload}


@app.get("/", response_class=HTMLResponse)
async def index():
    report = await tiktok.check_connection()
    configured = report["configured"]
    reachable = report["api_host_reachable"]
    badge = "OK" if report["ok"] else "FAIL"
    badge_color = "#00B894" if report["ok"] else "#e74c3c"
    authorize_link = (
        f'<a href="/api/tiktok/authorize-url" target="_blank">Get authorize URL</a>'
        if configured
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BrandAura - TikTok Connection Test</title>
<style>
  body {{ margin:0; padding:40px 20px; background:#0a1e2b; color:#eaf5f5;
         font-family:'Segoe UI',Arial,sans-serif; }}
  .card {{ max-width:720px; margin:0 auto; background:#0f2d3d; border:1px solid rgba(255,255,255,.1);
           border-radius:20px; padding:34px 38px; box-shadow:0 30px 80px rgba(0,0,0,.4); }}
  h1 {{ margin:0 0 6px; font-size:24px; }}
  p.sub {{ margin:0 0 26px; color:#9db8c2; font-size:14px; }}
  table {{ width:100%; border-collapse:collapse; font-size:14px; }}
  td {{ padding:11px 0; border-bottom:1px solid rgba(255,255,255,.07); vertical-align:top; }}
  td.k {{ color:#6a8a99; width:230px; }}
  code {{ background:rgba(255,255,255,.06); padding:2px 7px; border-radius:6px; font-size:13px; }}
  .badge {{ display:inline-block; background:{badge_color}; color:#fff; font-weight:700;
            padding:4px 14px; border-radius:999px; font-size:13px; letter-spacing:.04em; }}
  a {{ color:#00B894; }}
</style>
</head>
<body>
  <div class="card">
    <h1>TikTok API connection <span class="badge">{badge}</span></h1>
    <p class="sub">BrandAura backend - live check against open.tiktokapis.com</p>
    <table>
      <tr><td class="k">TIKTOK_CLIENT_KEY loaded</td><td>{configured}</td></tr>
      <tr><td class="k">Client key (masked)</td><td><code>{report['client_key_masked'] or '-'}</code></td></tr>
      <tr><td class="k">TIKTOK_CLIENT_SECRET loaded</td><td>{bool(TIKTOK_CLIENT_SECRET)}</td></tr>
      <tr><td class="k">Redirect URI</td><td><code>{TIKTOK_REDIRECT_URI}</code></td></tr>
      <tr><td class="k">Scopes</td><td><code>{report['scopes']}</code></td></tr>
      <tr><td class="k">API host reachable</td><td>{reachable} (HTTP {report['http_status']}, {report['latency_ms']} ms)</td></tr>
      <tr><td class="k">Detail</td><td>{report['detail']}</td></tr>
    </table>
    <p style="margin-top:26px">{authorize_link} &nbsp;|&nbsp;
       <a href="/docs">OpenAPI docs</a> &nbsp;|&nbsp;
       <a href="/api/tiktok/status">Status JSON</a></p>
  </div>
</body>
</html>"""
