import asyncio
import json
import os
import secrets
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import uvicorn
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / "oura.env"
load_dotenv(ENV_FILE, override=True)

HOST = os.getenv("OURA_HOST", "127.0.0.1")
PORT = int(os.getenv("OURA_PORT", "8765"))
CLIENT_ID = os.getenv("OURA_CLIENT_ID", "").strip()
CLIENT_SECRET = os.getenv("OURA_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.getenv("OURA_REDIRECT_URI", f"http://127.0.0.1:{PORT}/oauth/callback").strip()
SCOPES = os.getenv("OURA_SCOPES", "personal daily heartrate workout tag session spo2").split()
TOKEN_FILE = BASE_DIR / os.getenv("OURA_TOKEN_FILE", "data/tokens.json")
STATE_FILE = BASE_DIR / "data" / "oauth_state.json"
TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

AUTH_URL = "https://cloud.ouraring.com/oauth/authorize"
TOKEN_URL = "https://api.ouraring.com/oauth/token"
API_BASE = "https://api.ouraring.com/v2/usercollection"

# Current Oura V2 collection endpoints useful for personal analysis.
ENDPOINTS = {
    "personal_info": "personal_info",
    "daily_activity": "daily_activity",
    "daily_sleep": "daily_sleep",
    "daily_readiness": "daily_readiness",
    "daily_stress": "daily_stress",
    "daily_resilience": "daily_resilience",
    "daily_spo2": "daily_spo2",
    "daily_cardiovascular_age": "daily_cardiovascular_age",
    "vO2_max": "vO2_max",
    "sleep": "sleep",
    "sleep_time": "sleep_time",
    "heartrate": "heartrate",
    "workout": "workout",
    "session": "session",
    "tag": "tag",
    "enhanced_tag": "enhanced_tag",
    "rest_mode_period": "rest_mode_period",
    "ring_configuration": "ring_configuration",
    "ring_battery_level": "ring_battery_level",
}

DAILY_ENDPOINTS = [
    "daily_sleep",
    "daily_readiness",
    "daily_activity",
    "daily_stress",
    "daily_resilience",
    "daily_spo2",
    "daily_cardiovascular_age",
    "vO2_max",
]

mcp = FastMCP(
    "Oura Personal Health",
    instructions=(
        "Use these tools to retrieve the user's own Oura Ring data for personal analysis. "
        "Prefer get_health_snapshot for broad recent trend analysis, then use get_oura_data "
        "for focused or detailed data. Data comes directly from the user's authorized Oura account."
    ),
    json_response=True,
)

_state_lock = threading.Lock()


def _configured() -> bool:
    return bool(CLIENT_ID and CLIENT_SECRET and REDIRECT_URI)


def _load_tokens() -> dict[str, Any] | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_tokens(tokens: dict[str, Any]) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(tokens, indent=2), encoding="utf-8")
    tmp.replace(TOKEN_FILE)


def _save_state(state: str) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"state": state, "created": time.time()}), encoding="utf-8")


def _consume_state(state: str) -> bool:
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        STATE_FILE.unlink(missing_ok=True)
        if time.time() - float(payload.get("created", 0)) > 600:
            return False
        return secrets.compare_digest(str(payload.get("state", "")), state)
    except Exception:
        return False


def _token_request(data: dict[str, str]) -> dict[str, Any]:
    response = httpx.post(
        TOKEN_URL,
        data=data,
        headers={"Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _refresh_tokens(tokens: dict[str, Any]) -> str:
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("No Oura refresh token is available. Re-authorize the application.")

    refreshed = _token_request({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    refreshed["obtained_at"] = time.time()
    _save_tokens(refreshed)
    return str(refreshed["access_token"])


def _access_token(force_refresh: bool = False) -> str:
    tokens = _load_tokens()
    if not tokens or not tokens.get("access_token"):
        raise RuntimeError("Oura is not connected. Open /oauth/start or call authorize_oura first.")

    expires_at = float(tokens.get("obtained_at", 0)) + float(tokens.get("expires_in", 0))
    if force_refresh or expires_at - time.time() < 90:
        with _state_lock:
            latest = _load_tokens() or tokens
            latest_expires = float(latest.get("obtained_at", 0)) + float(latest.get("expires_in", 0))
            if force_refresh or latest_expires - time.time() < 90:
                return _refresh_tokens(latest)
            return str(latest["access_token"])
    return str(tokens["access_token"])


def _api_get(collection: str, params: dict[str, Any] | None = None) -> Any:
    token = _access_token()
    url = f"{API_BASE}/{collection}"
    response = httpx.get(url, params=params or {}, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if response.status_code == 401:
        token = _access_token(force_refresh=True)
        response = httpx.get(url, params=params or {}, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        raise RuntimeError(f"Oura rate limit reached. Retry-After: {retry_after}")
    response.raise_for_status()
    return response.json()


def _date_range(start_date: str | None, end_date: str | None, days: int = 7) -> tuple[str, str]:
    today = date.today()
    end = date.fromisoformat(end_date) if end_date else today
    start = date.fromisoformat(start_date) if start_date else end - timedelta(days=days - 1)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    return start.isoformat(), end.isoformat()


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    return JSONResponse({
        "status": "ok",
        "service": "oura-personal-health",
        "mcp": "/mcp",
        "oauth_configured": _configured(),
        "authorized": bool(_load_tokens()),
        "port": PORT,
    })


@mcp.custom_route("/oauth/start", methods=["GET"])
async def oauth_start(_: Request) -> RedirectResponse:
    if not _configured():
        return RedirectResponse("/health", status_code=307)
    state = secrets.token_urlsafe(32)
    _save_state(state)
    query = urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
    })
    return RedirectResponse(f"{AUTH_URL}?{query}", status_code=302)


@mcp.custom_route("/oauth/callback", methods=["GET"])
async def oauth_callback(request: Request) -> HTMLResponse:
    error = request.query_params.get("error")
    if error:
        return HTMLResponse(f"<h1>Oura authorization failed</h1><p>{error}</p>", status_code=400)

    code = request.query_params.get("code")
    state = request.query_params.get("state", "")
    if not code or not state or not _consume_state(state):
        return HTMLResponse("<h1>Invalid OAuth callback</h1><p>Missing or invalid authorization state.</p>", status_code=400)

    try:
        tokens = _token_request({
            "grant_type": "authorization_code",
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
        })
        tokens["obtained_at"] = time.time()
        _save_tokens(tokens)
        return HTMLResponse("<h1>Oura connected</h1><p>You can close this window. Your local Oura service is now authorized.</p>")
    except Exception as exc:
        return HTMLResponse(f"<h1>Oura token exchange failed</h1><pre>{type(exc).__name__}: {exc}</pre>", status_code=500)


@mcp.tool()
def get_connection_status() -> dict[str, Any]:
    """Return local Oura connection status without exposing credentials or tokens."""
    tokens = _load_tokens()
    expires_at = None
    if tokens:
        expires_at = float(tokens.get("obtained_at", 0)) + float(tokens.get("expires_in", 0))
    return {
        "configured": _configured(),
        "authorized": bool(tokens and tokens.get("access_token")),
        "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat() if expires_at else None,
        "redirect_uri": REDIRECT_URI,
        "scopes_configured": SCOPES,
        "mcp_endpoint": f"http://{HOST}:{PORT}/mcp",
    }


@mcp.tool()
def authorize_oura() -> str:
    """Create an Oura OAuth authorization URL. Open it in a browser to connect the account."""
    if not _configured():
        return "Oura credentials are not configured. Fill in oura.env first and restart the service."
    state = secrets.token_urlsafe(32)
    _save_state(state)
    query = urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
    })
    return f"{AUTH_URL}?{query}"


@mcp.tool()
def get_personal_info() -> dict[str, Any]:
    """Get the authenticated Oura user's personal profile information."""
    return _api_get(ENDPOINTS["personal_info"])


@mcp.tool()
def get_oura_data(
    data_type: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Get Oura V2 data for a supported collection. Use ISO dates for start_date/end_date."""
    if data_type not in ENDPOINTS:
        raise ValueError(f"Unsupported data_type. Available: {', '.join(sorted(ENDPOINTS))}")

    collection = ENDPOINTS[data_type]
    params: dict[str, Any] = {}
    if data_type != "personal_info" and start_date is not None:
        params["start_date"] = start_date
    if data_type != "personal_info" and end_date is not None:
        params["end_date"] = end_date

    # Oura time-series endpoints are safest in bounded windows. Keep the tool useful
    # while avoiding accidental enormous responses from an LLM request.
    if data_type == "heartrate" and start_date is None and end_date is None:
        start, end = _date_range(None, None, days=7)
        params.update(start_date=start, end_date=end)

    return {"data_type": data_type, "result": _api_get(collection, params)}


@mcp.tool()
def get_health_snapshot(days: int = 7) -> dict[str, Any]:
    """Get a compact multi-metric snapshot for recent health trend analysis."""
    days = max(1, min(int(days), 90))
    start, end = _date_range(None, None, days=days)
    results: dict[str, Any] = {"start_date": start, "end_date": end, "data": {}, "errors": {}}

    def fetch(name: str) -> tuple[str, Any]:
        try:
            return name, _api_get(ENDPOINTS[name], {"start_date": start, "end_date": end})
        except Exception as exc:
            return name, {"error": f"{type(exc).__name__}: {exc}"}

    with ThreadPoolExecutor(max_workers=len(DAILY_ENDPOINTS)) as executor:
        futures = [executor.submit(fetch, name) for name in DAILY_ENDPOINTS]
        for future in as_completed(futures):
            name, payload = future.result()
            if isinstance(payload, dict) and "error" in payload:
                results["errors"][name] = payload["error"]
            else:
                results["data"][name] = payload
    return results


@mcp.tool()
def get_recent_activity_and_recovery(days: int = 14) -> dict[str, Any]:
    """Fetch recent daily activity, readiness, sleep, stress, resilience, and workouts for correlation analysis."""
    days = max(1, min(int(days), 90))
    start, end = _date_range(None, None, days=days)
    names = ["daily_activity", "daily_sleep", "daily_readiness", "daily_stress", "daily_resilience", "workout"]
    output: dict[str, Any] = {"start_date": start, "end_date": end, "data": {}, "errors": {}}
    for name in names:
        try:
            output["data"][name] = _api_get(ENDPOINTS[name], {"start_date": start, "end_date": end})
        except Exception as exc:
            output["errors"][name] = f"{type(exc).__name__}: {exc}"
    return output


@mcp.tool()
def disconnect_oura() -> str:
    """Delete the locally stored Oura OAuth tokens. The Oura authorization itself can be revoked separately."""
    TOKEN_FILE.unlink(missing_ok=True)
    STATE_FILE.unlink(missing_ok=True)
    return "Local Oura tokens removed. The service is no longer authorized until you connect again."


def main() -> None:
    if not ENV_FILE.exists() or not _configured():
        print(f"Oura configuration is missing or incomplete: {ENV_FILE}")
        print("Run start-oura.ps1 to create/open the configuration file, then restart.")
        raise SystemExit(2)

    app = mcp.streamable_http_app()
    print(f"Oura Personal Health MCP: http://{HOST}:{PORT}/mcp")
    print(f"Health check: http://{HOST}:{PORT}/health")
    print(f"OAuth start: http://{HOST}:{PORT}/oauth/start")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
