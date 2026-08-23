import json
import os
import secrets
import threading
import time
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
SCOPES = os.getenv("OURA_SCOPES", "personal daily heartrate workout tag session spo2Daily").split()
TOKEN_FILE = BASE_DIR / os.getenv("OURA_TOKEN_FILE", "data/tokens.json")
STATE_FILE = BASE_DIR / "data" / "oauth_state.json"
TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

AUTH_URL = "https://cloud.ouraring.com/oauth/authorize"
TOKEN_URL = "https://api.ouraring.com/oauth/token"
API_BASE = "https://api.ouraring.com/v2/usercollection"

COLLECTIONS = {
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

DAILY_COLLECTIONS = {
    "daily_activity", "daily_sleep", "daily_readiness", "daily_stress",
    "daily_resilience", "daily_spo2", "daily_cardiovascular_age", "vO2_max",
    "sleep", "sleep_time", "workout", "session", "tag", "enhanced_tag",
    "rest_mode_period",
}
TIME_SERIES_COLLECTIONS = {"heartrate", "ring_battery_level"}
TIMESERIES_MAX_DAYS = 30
DEFAULT_MAX_RECORDS = 500

mcp = FastMCP(
    "Oura Personal Health",
    instructions=(
        "You have read-only access to the user's own Oura Ring V2 data. "
        "For broad health questions, averages, trends, comparisons, sleep debt, "
        "regularity, anomalies, or correlations, use the compact server-side "
        "analytics tools such as get_health_snapshot, get_recent_activity_and_recovery, "
        "find_metric_trends, compare_periods, calculate_sleep_debt, "
        "calculate_sleep_regularity, find_anomalies, and correlate_oura_metrics. "
        "These tools perform calculations on the server and return only small summaries. "
        "Do NOT use get_oura_data for broad questions. Use get_oura_data only when the "
        "user explicitly asks for detailed/raw records or a collection not covered by "
        "an analytics endpoint. Always keep raw requests bounded and use fields when practical."
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
    response = httpx.post(TOKEN_URL, data=data, headers={"Accept": "application/json"}, timeout=30)
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


def _request(url: str, params: dict[str, Any] | None = None) -> httpx.Response:
    token = _access_token()
    response = httpx.get(url, params=params or {}, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if response.status_code == 401:
        token = _access_token(force_refresh=True)
        response = httpx.get(url, params=params or {}, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After", "unknown")
        raise RuntimeError(f"Oura rate limit reached. Retry-After: {retry_after}")
    response.raise_for_status()
    return response


def _date_range(start_date: str | None, end_date: str | None, days: int = 7) -> tuple[str, str]:
    today = date.today()
    end = date.fromisoformat(end_date) if end_date else today
    start = date.fromisoformat(start_date) if start_date else end - timedelta(days=days - 1)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    return start.isoformat(), end.isoformat()


def _datetime_range(start_datetime: str | None, end_datetime: str | None, hours: int = 24) -> tuple[str, str]:
    end = datetime.fromisoformat(end_datetime.replace("Z", "+00:00")) if end_datetime else datetime.now(timezone.utc)
    start = datetime.fromisoformat(start_datetime.replace("Z", "+00:00")) if start_datetime else end - timedelta(hours=hours)
    if start > end:
        raise ValueError("start_datetime must not be after end_datetime")
    return start.isoformat(), end.isoformat()


def _paginate(collection: str, params: dict[str, Any], max_records: int) -> dict[str, Any]:
    """Fetch all pages using Oura's next_token cursor, bounded by max_records."""
    all_data: list[Any] = []
    next_token: str | None = params.get("next_token")
    pages = 0
    while True:
        request_params = dict(params)
        if next_token:
            request_params["next_token"] = next_token
        else:
            request_params.pop("next_token", None)
        payload = _request(f"{API_BASE}/{collection}", request_params).json()
        if collection == "personal_info":
            return {"data": payload, "pages": 1}
        page_data = payload.get("data", []) if isinstance(payload, dict) else []
        all_data.extend(page_data)
        pages += 1
        if len(all_data) >= max_records:
            return {"data": all_data[:max_records], "pages": pages, "truncated": True, "next_token": payload.get("next_token")}
        next_token = payload.get("next_token") if isinstance(payload, dict) else None
        if not next_token:
            return {"data": all_data, "pages": pages, "truncated": False}
        if pages >= 1000:
            return {"data": all_data, "pages": pages, "truncated": True, "reason": "pagination safety limit"}


def _fetch_collection(
    collection: str,
    start_date: str | None = None,
    end_date: str | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    latest: bool | None = None,
    fields: str | None = None,
    next_token: str | None = None,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if fields:
        params["fields"] = fields
    if next_token:
        params["next_token"] = next_token

    if collection in DAILY_COLLECTIONS:
        start, end = _date_range(start_date, end_date, 7)
        params.update(start_date=start, end_date=end)
    elif collection in TIME_SERIES_COLLECTIONS:
        start, end = _datetime_range(start_datetime, end_datetime, 24)
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        if end_dt - start_dt > timedelta(days=TIMESERIES_MAX_DAYS):
            raise ValueError(f"{collection} requests are limited to {TIMESERIES_MAX_DAYS} days per call. Split the requested period into smaller ranges.")
        params.update(start_datetime=start, end_datetime=end)
        if latest is not None:
            params["latest"] = str(bool(latest)).lower()
    elif collection == "ring_configuration":
        pass
    elif collection == "personal_info":
        pass

    return _paginate(collection, params, max(1, min(int(max_records), 50000)))


@mcp.custom_route("/health", methods=["GET"])
async def health(_: Request) -> JSONResponse:
    tokens = _load_tokens()
    return JSONResponse({
        "status": "ok",
        "service": "oura-personal-health",
        "api": "Oura V2",
        "mcp": "/mcp",
        "oauth_configured": _configured(),
        "authorized": bool(tokens and tokens.get("access_token")),
        "port": PORT,
        "collections": sorted(COLLECTIONS),
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
        description = request.query_params.get("error_description", "")
        return HTMLResponse(f"<h1>Oura authorization failed</h1><p>{error}</p><p>{description}</p>", status_code=400)

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
        return HTMLResponse("<h1>Oura connected</h1><p>Your local Oura service is authorized. You can close this window.</p>")
    except Exception as exc:
        return HTMLResponse(f"<h1>Oura token exchange failed</h1><pre>{type(exc).__name__}: {exc}</pre>", status_code=500)


@mcp.tool()
def get_connection_status() -> dict[str, Any]:
    """Return Oura connection status without exposing credentials or token values."""
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
def list_available_data() -> dict[str, Any]:
    """List every Oura V2 read collection exposed by this service and the parameters it accepts."""
    return {
        "collections": sorted(COLLECTIONS),
        "daily_date_range": sorted(DAILY_COLLECTIONS),
        "time_series_datetime_range": sorted(TIME_SERIES_COLLECTIONS),
        "personal_info": ["personal_info"],
        "ring_configuration": ["ring_configuration"],
        "time_series_max_days": TIMESERIES_MAX_DAYS,
        "notes": [
            "Oura pagination is followed automatically.",
            "Use fields for sparse responses when you know the required fields.",
            "Use max_records to prevent excessively large model context payloads.",
            "Prefer compact analytics tools for questions about averages, trends, comparisons, and correlations.",
        ],
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
def get_oura_data(
    data_type: str,
    start_date: str | None = None,
    end_date: str | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    latest: bool | None = None,
    fields: str | None = None,
    next_token: str | None = None,
    max_records: int = 500,
) -> dict[str, Any]:
    """Advanced raw Oura collection access. Use only for explicit detailed-data requests; prefer analytics tools for summaries."""
    if data_type not in COLLECTIONS:
        raise ValueError(f"Unsupported data_type. Available: {', '.join(sorted(COLLECTIONS))}")
    result = _fetch_collection(
        COLLECTIONS[data_type], start_date, end_date, start_datetime, end_datetime,
        latest, fields, next_token, max_records,
    )
    result["data_type"] = data_type
    return result


@mcp.tool()
def disconnect_oura() -> str:
    """Delete locally stored OAuth tokens and pending state. This does not revoke access at Oura."""
    TOKEN_FILE.unlink(missing_ok=True)
    STATE_FILE.unlink(missing_ok=True)
    return "Local Oura tokens removed. Re-authorize to reconnect."


def main() -> None:
    if not ENV_FILE.exists() or not _configured():
        print(f"Oura configuration is missing or incomplete: {ENV_FILE}")
        print("Run start-oura.ps1 to create/open the configuration file, then restart the service.")
        raise SystemExit(2)
    app = mcp.streamable_http_app()
    print(f"Oura Personal Health MCP: http://{HOST}:{PORT}/mcp")
    print(f"Health check: http://{HOST}:{PORT}/health")
    print(f"OAuth start: http://{HOST}:{PORT}/oauth/start")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
